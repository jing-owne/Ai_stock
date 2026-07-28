"""
每日标的预过滤缓存模块 v2.6.5

功能：
1. 每日首次运行时，从腾讯行情接口获取全部A股，应用预过滤器
2. 交叉验证：东财(主) → baostock(备) → 新浪(备)，三级fallback
3. 过滤条件：股价>120、ST、688科创板、8开头北交所、停牌(量=0)、退市、股价<3
4. 过滤后的代码写入 JSON 缓存，当天后续任务直接读取
5. 缓存文件按日期命名：cache/daily_codes_YYYY-MM-DD.json
6. ⚠️ 缓存仅存储「可交易标的的标识」（code + name），【禁止】写入
   价格、当日涨幅等行情字段——这些必须每次扫描时实时拉取，
   否则会出现「缓存涨幅被邮件复用、多日内容雷同」的问题。

交叉验证策略（三级fallback）：
- 东方财富 clist API：主数据源，全市场代码列表（可能超时）
- baostock：免费开源库，提供全市场代码列表（稳定、无限制）
- 新浪行情接口：最后备用
- 仅保留交叉验证确认有效的代码，写入缓存

预期效果：
- 全市场约5000+个代码扫描 → 经交叉验证 + 过滤 → 约2500-3500只进入缓存
- 后续扫描批次从300+批减少到~50-70批
- 无效代码大幅减少，数据质量提升
"""
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Set, Optional, Dict

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("AInvest.DailyFilter")

# 腾讯行情接口
TENCENT_QUOTE_URL = "http://qt.gtimg.cn/q="

# 东方财富全市场代码列表接口（主交叉验证源）
EASTMONEY_CODE_LIST_URL = (
    "https://push2.eastmoney.com/api/qt/clist/get"
    "?pn=1&pz=6000&po=1&np=1&fltt=2&fid=f3"
    "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
    "&fields=f2,f3,f12,f14"
)

# 新浪全市场代码列表接口（备用交叉验证源）
SINA_CODE_LIST_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"

# 预过滤规则
FILTER_RULES = {
    "max_price": 120,        # 股价上限
    "min_price": 3.0,        # 股价下限
    "exclude_prefixes": ["688", "8", "9"],  # 科创板/北交所/B股
    "exclude_name_kw": ["ST", "*ST", "退市"],  # ST/退市
    "max_change_pct": 15.0,  # 过滤异常涨幅(可能数据错误)
}


def _generate_a_share_codes() -> List[str]:
    """生成沪深A股代码扫描列表（全量）"""
    ranges = [
        ("sh", 600000, 606000),
        ("sh", 601000, 604000),
        ("sh", 603000, 604000),
        ("sh", 605000, 606000),
        ("sz", 1, 5000),
        ("sz", 2001, 6000),
        ("sz", 300001, 303000),
    ]
    all_codes = []
    seen = set()
    for prefix, start, end in ranges:
        for code in range(start, end):
            code_str = str(code).zfill(6)
            if code_str not in seen:
                seen.add(code_str)
                all_codes.append(f"{prefix}{code_str}")
    return all_codes


def _parse_tencent_filter(line: str) -> Optional[dict]:
    """
    解析腾讯行情单行数据，仅提取过滤所需字段
    返回 None 表示该标的被过滤掉
    返回 dict 表示通过预过滤: {code, name, close, ...}
    """
    if not line.strip() or "v_" not in line:
        return None

    parts = line.split('~')
    if len(parts) < 50:
        return None

    try:
        code = parts[2]
        name = parts[1]
        close = float(parts[3]) if parts[3] else 0

        # ── 排除无效价格 ──
        if close <= 0:
            return None

        # ── 排除高价股（>120元）──
        if close > FILTER_RULES["max_price"]:
            return None

        # ── 排除低价股（<3元）──
        if close < FILTER_RULES["min_price"]:
            return None

        # ── 排除代码前缀 ──
        for prefix in FILTER_RULES["exclude_prefixes"]:
            if code.startswith(prefix):
                return None

        # ── 排除ST/退市 ──
        for kw in FILTER_RULES["exclude_name_kw"]:
            if kw in name:
                return None

        # ── 排除异常涨跌幅 ──
        pct = float(parts[32]) if parts[32] else 0
        if abs(pct) > FILTER_RULES["max_change_pct"]:
            return None

        # ── 排除停牌（成交额为0）──
        amount_wan = float(parts[37]) if parts[37] else 0
        if amount_wan <= 0:
            return None

        # 成交量（手）
        volume_shou = float(parts[6]) if parts[6] else 0
        if volume_shou <= 0:
            return None

        # 仅返回可交易标识信息（代码+名称），不含价格与涨幅。
        # 价格(close)与当日涨幅(change_pct)仅在过滤阶段临时使用，
        # 禁止写入缓存——所有行情数据必须实时拉取（见模块说明）。
        return {
            "code": code,
            "name": name,
        }
    except (ValueError, IndexError):
        return None


def _get_cross_validation_codes() -> Set[str]:
    """
    获取交叉验证用全市场有效代码列表（三级fallback）
    
    优先级：东财(主) → baostock(备) → 新浪(备)
    任一数据源成功即返回，全部失败返回空集合
    
    Returns:
        有效标的6位代码集合
    """
    # 步骤1: 尝试东方财富（主数据源）
    codes = _get_eastmoney_valid_codes()
    if len(codes) > 1000:
        logger.info(f"[交叉验证] 使用东财代码列表: {len(codes)}只")
        return codes
    logger.warning(f"[交叉验证] 东财代码列表不足({len(codes)}只)，尝试baostock...")
    
    # 步骤2: 尝试baostock（免费开源库）
    codes = _get_baostock_valid_codes()
    if len(codes) > 1000:
        logger.info(f"[交叉验证] 使用baostock代码列表: {len(codes)}只")
        return codes
    logger.warning(f"[交叉验证] baostock代码列表不足({len(codes) if codes else 0}只)，尝试新浪...")
    
    # 步骤3: 尝试新浪（最后备用）
    codes = _get_sina_valid_codes()
    if len(codes) > 100:
        logger.info(f"[交叉验证] 使用新浪代码列表: {len(codes)}只")
        return codes
    
    logger.warning("[交叉验证] 所有数据源均失败，跳过交叉验证")
    return set()


def _get_eastmoney_valid_codes() -> Set[str]:
    """
    从东方财富全市场列表获取有效A股代码（主交叉验证源）
    
    带重试机制，超时30秒
    """
    try:
        logger.info("[交叉验证] 获取东方财富全市场代码列表...")
        t0 = time.time()
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://quote.eastmoney.com/",
        })
        
        # 重试3次
        for attempt in range(3):
            try:
                resp = session.get(EASTMONEY_CODE_LIST_URL, timeout=30, verify=False)
                if resp.status_code != 200:
                    logger.warning(f"[交叉验证] 东财接口返回非200: {resp.status_code} (重试{attempt+1}/3)")
                    time.sleep(1.0 * (attempt + 1))
                    continue
                    
                data = resp.json()
                if not data or not data.get("data"):
                    logger.warning(f"[交叉验证] 东财接口无数据 (重试{attempt+1}/3)")
                    time.sleep(1.0 * (attempt + 1))
                    continue
                    
                items = data["data"].get("diff", [])
                valid_codes = set()
                for item in items:
                    code = item.get("f12", "")
                    if code and len(code) == 6:
                        valid_codes.add(code)
                        
                elapsed = time.time() - t0
                logger.info(f"[交叉验证] 东财有效代码: {len(valid_codes)}只, 耗时: {elapsed:.1f}秒")
                session.close()
                return valid_codes
                
            except Exception as e:
                logger.warning(f"[交叉验证] 东财接口异常(重试{attempt+1}/3): {e}")
                time.sleep(1.0 * (attempt + 1))
                
        session.close()
        return set()
        
    except Exception as e:
        logger.warning(f"[交叉验证] 获取东财代码列表失败: {e}")
        return set()


def _get_baostock_valid_codes() -> Set[str]:
    """
    从baostock获取全市场有效A股代码（备用交叉验证源）
    
    baostock是免费开源库，提供全市场代码列表
    需要安装: pip install baostock
    """
    try:
        logger.info("[交叉验证] 获取baostock全市场代码列表...")
        t0 = time.time()
        
        import baostock as bs
        from datetime import datetime
        
        # 登录baostock
        lg = bs.login()
        if lg.error_code != '0':
            logger.warning(f"[交叉验证] baostock登录失败: {lg.error_msg}")
            return set()
        
        # 获取当前日期
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 获取沪深A股全部代码
        rs = bs.query_all_stock(day=today)
        if rs.error_code != '0':
            logger.warning(f"[交叉验证] baostock查询失败: {rs.error_msg}")
            bs.logout()
            return set()
        
        valid_codes = set()
        while rs.next():
            code = rs.get_row_data()[0]  # code字段
            # baostock返回格式: sh.600519, sz.000001
            if '.' in code:
                pure_code = code.split('.')[1]
                if len(pure_code) == 6:
                    valid_codes.add(pure_code)
        
        bs.logout()
        elapsed = time.time() - t0
        logger.info(f"[交叉验证] baostock有效代码: {len(valid_codes)}只, 耗时: {elapsed:.1f}秒")
        return valid_codes
        
    except ImportError:
        logger.warning("[交叉验证] baostock未安装，跳过（pip install baostock）")
        return set()
    except Exception as e:
        logger.warning(f"[交叉验证] 获取baostock代码列表失败: {e}")
        return set()


def _get_sina_valid_codes() -> Set[str]:
    """
    从新浪财经获取全市场有效A股代码（最后备用交叉验证源）
    
    分页获取，每页100只
    """
    try:
        logger.info("[交叉验证] 获取新浪全市场代码列表...")
        t0 = time.time()
        
        valid_codes = set()
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://finance.sina.com.cn/",
        })
        
        # 分页获取全市场数据
        for page in range(1, 61):
            try:
                params = {
                    "page": page,
                    "num": 100,
                    "sort": "symbol",
                    "asc": 1,
                    "node": "hs_a",
                    "symbol": "",
                    "_s_r_a": "page"
                }
                resp = session.get(SINA_CODE_LIST_URL, params=params, timeout=10, verify=False)
                
                if resp.status_code != 200:
                    break
                    
                data = resp.json()
                if not data or not isinstance(data, list):
                    break
                    
                for item in data:
                    code = item.get("symbol", "")
                    if code and len(code) == 8:  # 新浪返回格式: sh600519
                        valid_codes.add(code[2:])  # 去掉前缀
                
                if len(data) < 100:
                    break
                    
            except Exception as e:
                logger.debug(f"[交叉验证] 新浪分页{page}失败: {e}")
                break
        
        session.close()
        elapsed = time.time() - t0
        logger.info(f"[交叉验证] 新浪有效代码: {len(valid_codes)}只, 耗时: {elapsed:.1f}秒")
        return valid_codes
        
    except Exception as e:
        logger.warning(f"[交叉验证] 获取新浪代码列表失败: {e}")
        return set()


def _add_market_prefix(code: str) -> str:
    """标的代码加交易所前缀(sh/sz),已带前缀则原样返回"""
    code = str(code).strip()
    if code.startswith(("sh", "sz")):
        return code
    return f"sh{code}" if code.startswith("6") else f"sz{code}"


def _load_holdings_universe() -> List[dict]:
    """从 strategy_config.json 读 holdings+watchlist,返回 [{code(带前缀),name}]"""
    try:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "strategy_config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        items = []
        for h in cfg.get("holdings", []):
            items.append({"code": _add_market_prefix(h.get("symbol", "")), "name": h.get("name", "")})
        for w in cfg.get("watchlist", []):
            items.append({"code": _add_market_prefix(w.get("symbol", "")), "name": w.get("name", "")})
        return items
    except Exception as e:
        logger.warning(f"[每日预过滤] 读取 strategy_config holdings 失败: {e}")
        return []


def get_daily_filtered_codes(cache_dir: str = None, force_refresh: bool = False, universe: str = "tradable") -> List[str]:
    """
    获取当天预过滤后的代码列表（双源交叉验证）

    universe:
    - "tradable"(默认): 全市场可交易标的(走三级fallback交叉验证)
    - "holdings": 持仓+自选标的(从 strategy_config.json 读,不跑全市场扫描)
    """
    if cache_dir is None:
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "cache")

    os.makedirs(cache_dir, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    cache_file = os.path.join(cache_dir, f"daily_codes_{today}.json")

    # ── holdings 模式: 持仓标的池(不走全市场) ──
    if universe == "holdings":
        # 优先读缓存 holdings 字段
        if os.path.exists(cache_file) and not force_refresh:
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                holdings_codes = [h["code"] for h in data.get("holdings", [])]
                if holdings_codes:
                    logger.info(f"[每日预过滤] holdings 模式从缓存加载: {len(holdings_codes)} 只 ({cache_file})")
                    return holdings_codes
            except Exception:
                pass
        # 缓存无 holdings, 读 strategy_config.json
        items = _load_holdings_universe()
        codes = [it["code"] for it in items]
        logger.info(f"[每日预过滤] holdings 模式从 strategy_config 加载: {len(codes)} 只")
        return codes

    # ── 检查缓存(tradable) ──
    if os.path.exists(cache_file) and not force_refresh:
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            codes = data.get("codes", [])
            logger.info(f"[每日预过滤] 从缓存加载: {len(codes)} 只标的 ({cache_file})")
            return codes
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"[每日预过滤] 缓存文件损坏，重新获取: {e}")

    # ── 首次获取：三级fallback交叉验证 ──
    logger.info(f"[每日预过滤] 缓存不存在，开始交叉验证（东财→baostock→新浪）...")
    total_start = time.time()

    # 步骤1: 获取交叉验证代码列表（东财→baostock→新浪 三级fallback）
    cross_codes = _get_cross_validation_codes()
    cross_validation_enabled = len(cross_codes) > 100
    if not cross_validation_enabled:
        logger.warning("[每日预过滤] 交叉验证完全失败，仅使用腾讯单一数据源")

    all_codes = _generate_a_share_codes()
    logger.info(f"[每日预过滤] 扫描 {len(all_codes)} 个代码, 交叉验证: {'启用' if cross_validation_enabled else '禁用'}")

    batch_size = 50
    total_batches = (len(all_codes) + batch_size - 1) // batch_size
    filtered_codes: List[str] = []
    filtered_details: List[dict] = []
    failed_batches = 0
    total_scanned = 0
    cross_validated = 0
    cross_filtered = 0
    filtered_count = {
        "high_price": 0, "low_price": 0, "prefix": 0,
        "st_delisted": 0, "zero_volume": 0, "abnormal_pct": 0,
        "invalid": 0, "cross_check_fail": 0
    }
    lock = threading.Lock()
    completed_batches = 0

    def _process_batch(batch_codes: List[str], batch_num: int):
        """处理单个批次（并发 worker）"""
        worker_session = requests.Session()
        worker_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://finance.qq.com/",
        })
        local_codes: List[str] = []
        local_details: List[dict] = []
        local_counts = {
            "high_price": 0, "low_price": 0, "prefix": 0,
            "st_delisted": 0, "zero_volume": 0, "abnormal_pct": 0,
            "invalid": 0, "cross_check_fail": 0
        }
        local_scanned = 0
        local_cross_ok = 0
        local_cross_fail = 0

        try:
            url = f"{TENCENT_QUOTE_URL}{','.join(batch_codes)}"
            resp = worker_session.get(url, timeout=15)
            worker_session.close()
            resp.raise_for_status()

            lines = resp.text.strip().split(';')
            for line in lines:
                local_scanned += 1
                result = _parse_tencent_filter(line)
                if result:
                    code = result["code"]
                    if cross_validation_enabled:
                        if code not in cross_codes:
                            local_counts["cross_check_fail"] += 1
                            local_cross_fail += 1
                            continue
                        local_cross_ok += 1
                    local_codes.append(f"{'sh' if code.startswith('6') else 'sz'}{code}")
                    local_details.append(result)
                elif line.strip():
                    parts = line.split('~')
                    if len(parts) >= 4:
                        code = parts[2] if len(parts) > 2 else ""
                        name = parts[1] if len(parts) > 1 else ""
                        close_str = parts[3] if len(parts) > 3 else "0"
                        try:
                            close = float(close_str)
                            if close > FILTER_RULES["max_price"]:
                                local_counts["high_price"] += 1
                            elif 0 < close < FILTER_RULES["min_price"]:
                                local_counts["low_price"] += 1
                            elif any(code.startswith(p) for p in FILTER_RULES["exclude_prefixes"]):
                                local_counts["prefix"] += 1
                            elif any(kw in name for kw in FILTER_RULES["exclude_name_kw"]):
                                local_counts["st_delisted"] += 1
                            elif close <= 0:
                                local_counts["zero_volume"] += 1
                        except ValueError:
                            local_counts["invalid"] += 1
        except Exception as e:
            batch_error = str(e)
            with lock:
                nonlocal failed_batches
                if failed_batches < 3:
                    logger.warning(f"[每日预过滤] 批次{batch_num}失败: {batch_error}")
                failed_batches += 1
            return

        # 合并到共享状态
        with lock:
            nonlocal total_scanned, cross_validated, cross_filtered
            filtered_codes.extend(local_codes)
            filtered_details.extend(local_details)
            for k, v in local_counts.items():
                filtered_count[k] += v
            total_scanned += local_scanned
            cross_validated += local_cross_ok
            cross_filtered += local_cross_fail

        return (batch_num, len(local_codes), {})

    # 构建批次
    batch_list = [
        (all_codes[i:i + batch_size], i // batch_size + 1)
        for i in range(0, len(all_codes), batch_size)
    ]

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {}
        for batch_codes, batch_num in batch_list:
            futures[executor.submit(_process_batch, batch_codes, batch_num)] = batch_num
            time.sleep(0.01)  # 间隔提交，避免瞬间拥堵

        for future in as_completed(futures):
            completed_batches += 1
            try:
                future.result()
            except Exception as e:
                failed_batches += 1
                batch_num = futures[future]
                if failed_batches <= 3:
                    logger.warning(f"[每日预过滤] 批次{batch_num}失败: {e}")

            if completed_batches % 50 == 0 or completed_batches == total_batches:
                elapsed = time.time() - total_start
                logger.info(
                    f"[每日预过滤] 进度: {completed_batches}/{total_batches}, "
                    f"已通过: {len(filtered_codes)}只, "
                    f"耗时: {elapsed:.1f}秒"
                )

    total_elapsed = time.time() - total_start

    # ── 写入缓存 ──
    cache_data = {
        "date": today,
        "source": "tencent+cross_validation" if cross_validation_enabled else "tencent_only",
        "total_scanned": total_scanned,
        "total_filtered": len(filtered_codes),
        "cross_validated": cross_validated,
        "cross_filtered": cross_filtered,
        "filtered_count": filtered_count,
        "elapsed_seconds": round(total_elapsed, 2),
        "codes": filtered_codes,
        "details": filtered_details,
        "holdings": _load_holdings_universe(),
    }

    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        logger.info(
            f"[每日预过滤] 缓存已写入: {cache_file} "
            f"({len(filtered_codes)}只, 耗时{total_elapsed:.1f}秒, "
            f"交叉验证通过{cross_validated}, 滤除{cross_filtered})"
        )
    except Exception as e:
        logger.error(f"[每日预过滤] 缓存写入失败: {e}")

    # ── 清理旧缓存（保留最近2天）──
    _cleanup_old_cache(cache_dir, keep_days=2)

    logger.info(
        f"[每日预过滤] 完成！扫描{total_scanned}行 → 通过{len(filtered_codes)}只 "
        f"(高价{filtered_count['high_price']}, 低价{filtered_count['low_price']}, "
        f"前缀{filtered_count['prefix']}, ST{filtered_count['st_delisted']}, "
        f"停牌{filtered_count['zero_volume']}, 异常{filtered_count['abnormal_pct']}, "
        f"交叉验证滤除{cross_filtered}), "
        f"总耗时: {total_elapsed:.1f}秒"
    )

    return filtered_codes


def get_cached_details(cache_dir: str = None) -> List[dict]:
    """
    获取当天缓存的标的标识信息（仅代码+名称）。

    注意：缓存中不再存储价格、涨跌幅等行情数据，这些必须实时拉取。
    本函数仅返回 {code, name}，避免任何调用方误用缓存中的旧涨幅。

    Returns:
        标的标识列表，每项为 {"code": ..., "name": ...}
    """
    if cache_dir is None:
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "cache")

    today = datetime.now().strftime("%Y-%m-%d")
    cache_file = os.path.join(cache_dir, f"daily_codes_{today}.json")

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 仅保留代码与名称，剔除任何残留的行情字段
            return [
                {"code": d.get("code"), "name": d.get("name")}
                for d in data.get("details", [])
            ]
        except Exception:
            pass
    return []


def _cleanup_old_cache(cache_dir: str, keep_days: int = 2):
    """清理旧缓存文件"""
    try:
        today = datetime.now()
        for fname in os.listdir(cache_dir):
            if fname.startswith("daily_codes_") and fname.endswith(".json"):
                fpath = os.path.join(cache_dir, fname)
                try:
                    date_str = fname.replace("daily_codes_", "").replace(".json", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    if (today - file_date).days > keep_days:
                        os.remove(fpath)
                        logger.info(f"[每日预过滤] 清理旧缓存: {fname}")
                except ValueError:
                    pass
    except Exception as e:
        logger.debug(f"[每日预过滤] 清理缓存异常(非关键): {e}")
