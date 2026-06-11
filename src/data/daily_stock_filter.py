"""
每日标的预过滤缓存模块 v2.6.5

功能：
1. 每日首次运行时，从腾讯行情接口获取全部A股，应用预过滤器
2. 使用东方财富全市场代码列表交叉验证，排除无效代码
3. 过滤条件：股价>120、ST、688科创板、8开头北交所、停牌(量=0)、退市、股价<3
4. 过滤后的代码写入 JSON 缓存，当天后续任务直接读取
5. 缓存文件按日期命名：cache/daily_codes_YYYY-MM-DD.json

双源验证策略：
- 腾讯 qt.gtimg.cn：实时行情（价格、涨跌幅）
- 东方财富 clist API：全市场有效代码列表
- 仅保留两源均确认有效的代码，写入缓存

预期效果：
- 全市场约5000+个代码扫描 → 经双源验证 + 过滤 → 约2500-3500只进入缓存
- 后续扫描批次从300+批减少到~50-70批
- 无效代码大幅减少，数据质量提升
"""
import json
import logging
import os
import time
from datetime import datetime
from typing import List, Set, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("AInvest.DailyFilter")

# 腾讯行情接口
TENCENT_QUOTE_URL = "http://qt.gtimg.cn/q="

# 东方财富全市场代码列表接口
EASTMONEY_CODE_LIST_URL = (
    "https://push2.eastmoney.com/api/qt/clist/get"
    "?pn=1&pz=6000&po=1&np=1&fltt=2&fid=f3"
    "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
    "&fields=f2,f3,f12,f14"
)

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

        return {
            "code": code,
            "name": name,
            "close": round(close, 2),
            "change_pct": round(pct, 2),
        }
    except (ValueError, IndexError):
        return None


def _get_eastmoney_valid_codes() -> Set[str]:
    """
    从东方财富全市场列表获取有效A股代码

    使用东财 clist API 一次性获取全市场代码列表，
    用于交叉验证腾讯接口返回的代码是否真实有效。

    Returns:
        有效标的6位代码集合，如 {"600519", "000858", "300750", ...}
    """
    try:
        logger.info("[交叉验证] 获取东方财富全市场代码列表...")
        t0 = time.time()
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://quote.eastmoney.com/",
        })
        resp = session.get(EASTMONEY_CODE_LIST_URL, timeout=30, verify=False)
        session.close()

        if resp.status_code != 200:
            logger.warning(f"[交叉验证] 东财接口返回非200: {resp.status_code}")
            return set()

        data = resp.json()
        if not data or not data.get("data"):
            logger.warning("[交叉验证] 东财接口无数据")
            return set()

        items = data["data"].get("diff", [])
        valid_codes = set()
        for item in items:
            code = item.get("f12", "")
            if code and len(code) == 6:
                valid_codes.add(code)

        elapsed = time.time() - t0
        logger.info(f"[交叉验证] 东财有效代码: {len(valid_codes)}只, 耗时: {elapsed:.1f}秒")
        return valid_codes
    except Exception as e:
        logger.warning(f"[交叉验证] 获取东财代码列表失败: {e}，跳过交叉验证")
        return set()


def get_daily_filtered_codes(cache_dir: str = None, force_refresh: bool = False) -> List[str]:
    """
    获取当天预过滤后的代码列表（双源交叉验证）

    流程：
    1. 如果当天缓存文件存在且不强制刷新 → 直接返回缓存
    2. 获取东方财富全市场有效代码列表（辅助验证）
    3. 从腾讯接口获取全部A股 → 应用预过滤
    4. 与东财代码列表交叉验证 → 仅保留双源均确认的代码
    5. 写入缓存 → 返回

    Args:
        cache_dir: 缓存目录路径
        force_refresh: 强制刷新缓存

    Returns:
        过滤后的代码列表（如 ["sh600519", "sz000858", ...]）
    """
    if cache_dir is None:
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "cache")

    os.makedirs(cache_dir, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    cache_file = os.path.join(cache_dir, f"daily_codes_{today}.json")

    # ── 检查缓存 ──
    if os.path.exists(cache_file) and not force_refresh:
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            codes = data.get("codes", [])
            logger.info(f"[每日预过滤] 从缓存加载: {len(codes)} 只标的 ({cache_file})")
            return codes
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"[每日预过滤] 缓存文件损坏，重新获取: {e}")

    # ── 首次获取：双源交叉验证 ──
    logger.info(f"[每日预过滤] 缓存不存在，开始双源交叉验证...")
    total_start = time.time()

    # 步骤1: 获取东方财富有效代码集合
    eastmoney_codes = _get_eastmoney_valid_codes()
    cross_validation_enabled = len(eastmoney_codes) > 0
    if not cross_validation_enabled:
        logger.warning("[每日预过滤] 交叉验证失败，仅使用腾讯单一数据源")

    all_codes = _generate_a_share_codes()
    logger.info(f"[每日预过滤] 扫描 {len(all_codes)} 个代码, 交叉验证: {'启用' if cross_validation_enabled else '禁用'}")

    batch_size = 50
    total_batches = (len(all_codes) + batch_size - 1) // batch_size
    filtered_codes = []
    filtered_details = []
    failed_batches = 0
    total_scanned = 0
    cross_validated = 0
    cross_filtered = 0
    filtered_count = {
        "high_price": 0, "low_price": 0, "prefix": 0,
        "st_delisted": 0, "zero_volume": 0, "abnormal_pct": 0,
        "invalid": 0, "cross_check_fail": 0
    }

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.qq.com/",
    })

    for i in range(0, len(all_codes), batch_size):
        batch = all_codes[i:i + batch_size]
        batch_num = i // batch_size + 1

        try:
            url = f"{TENCENT_QUOTE_URL}{','.join(batch)}"
            resp = session.get(url, timeout=15)
            resp.raise_for_status()

            lines = resp.text.strip().split(';')
            for line in lines:
                total_scanned += 1
                result = _parse_tencent_filter(line)
                if result:
                    code = result["code"]

                    # ── 东财交叉验证 ──
                    if cross_validation_enabled:
                        if code not in eastmoney_codes:
                            filtered_count["cross_check_fail"] += 1
                            cross_filtered += 1
                            continue
                        cross_validated += 1

                    filtered_codes.append(f"{'sh' if code.startswith('6') else 'sz'}{code}")
                    filtered_details.append(result)
                # 统计被过滤的原因（简化版，仅从代码特征判断）
                elif line.strip():
                    parts = line.split('~')
                    if len(parts) >= 4:
                        code = parts[2] if len(parts) > 2 else ""
                        name = parts[1] if len(parts) > 1 else ""
                        close_str = parts[3] if len(parts) > 3 else "0"
                        try:
                            close = float(close_str)
                            if close > FILTER_RULES["max_price"]:
                                filtered_count["high_price"] += 1
                            elif 0 < close < FILTER_RULES["min_price"]:
                                filtered_count["low_price"] += 1
                            elif any(code.startswith(p) for p in FILTER_RULES["exclude_prefixes"]):
                                filtered_count["prefix"] += 1
                            elif any(kw in name for kw in FILTER_RULES["exclude_name_kw"]):
                                filtered_count["st_delisted"] += 1
                            elif close <= 0:
                                filtered_count["zero_volume"] += 1
                        except ValueError:
                            filtered_count["invalid"] += 1

            if batch_num % 50 == 0 or batch_num == total_batches:
                elapsed = time.time() - total_start
                logger.info(
                    f"[每日预过滤] 进度: {batch_num}/{total_batches}, "
                    f"已通过: {len(filtered_codes)}只, "
                    f"耗时: {elapsed:.1f}秒"
                )

        except Exception as e:
            failed_batches += 1
            if failed_batches <= 3:
                logger.warning(f"[每日预过滤] 批次{batch_num}失败: {e}")

        time.sleep(0.03)

    session.close()

    total_elapsed = time.time() - total_start

    # ── 写入缓存 ──
    cache_data = {
        "date": today,
        "source": "tencent+eastmoney" if cross_validation_enabled else "tencent_only",
        "total_scanned": total_scanned,
        "total_filtered": len(filtered_codes),
        "cross_validated": cross_validated,
        "cross_filtered": cross_filtered,
        "filtered_count": filtered_count,
        "elapsed_seconds": round(total_elapsed, 2),
        "codes": filtered_codes,
        "details": filtered_details,
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
    获取当天缓存的标的详情（名称、价格、涨跌幅等）

    Returns:
        标的详情列表
    """
    if cache_dir is None:
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "cache")

    today = datetime.now().strftime("%Y-%m-%d")
    cache_file = os.path.join(cache_dir, f"daily_codes_{today}.json")

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("details", [])
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
