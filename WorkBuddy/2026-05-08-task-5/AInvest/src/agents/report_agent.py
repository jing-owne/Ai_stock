"""
报告生成Agent
负责生成各种格式的分析报告
"""
import os
import re
import json
import random
import logging
import urllib.request
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from pathlib import Path

from ..core.types import ScanResult, MarketAnalysis
from ..core.config import Config
from ..reports.generator import ReportGenerator
from ..reports.email_sender import EmailSender


# ============================================================
# 每日一言
# ============================================================
_LOCAL_QUOTES = [
    ("越努力，越幸运。", "佚名"),
    ("不要等待机会，而要创造机会。", "林肯"),
    ("成功不是将来才有的，而是从决定去做的那一刻起，持续累积而成。", "佚名"),
    ("每一个不曾起舞的日子，都是对生命的辜负。", "尼采"),
    ("你若盛开，清风自来。", "佚名"),
    ("把每一天当作生命的最后一天来过，总有一天你会发现自己是对的。", "乔布斯"),
    ("不要因为走得太远，而忘记为什么出发。", "纪伯伦"),
    ("真正的勇气是知道生活的真相后依然热爱生活。", "罗曼·罗兰"),
    ("所有的伟大，都源于一个勇敢的开始。", "佚名"),
    ("你的时间有限，不要浪费在重复别人的生活上。", "乔布斯"),
    ("心若没有栖息的地方，到哪里都是流浪。", "三毛"),
    ("生活不是等待风暴过去，而是学会在雨中翩翩起舞。", "佚名"),
    ("世上只有一种英雄主义，就是在认清生活真相之后依然热爱生活。", "罗曼·罗兰"),
    ("当你觉得晚了的时候，恰恰是最早的时候。", "佚名"),
    ("人生没有彩排，每一天都是现场直播。", "佚名"),
]


def _fetch_daily_quote() -> str:
    """获取每日一言，优先从 hitokoto API 拉取，失败时降级到本地备用句库"""
    try:
        req = urllib.request.Request(
            "https://v1.hitokoto.cn/?encode=json",
            headers={"User-Agent": "Mozilla/5.0 AInvest/1.0"}
        )
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode("utf-8"))
            text = data.get("hitokoto", "")
            source = data.get("from") or data.get("from_who") or ""
            if text:
                return f"「{text}」" + (f"  —— {source}" if source else "")
    except Exception:
        pass
    text, source = random.choice(_LOCAL_QUOTES)
    return f"「{text}」  —— {source}"


# ============================================================
# 财经动态（多源聚合：新浪财经 + 金十数据 + 第一财经）
# ============================================================

def _http_get(url: str, headers: Dict[str, str], timeout: int = 8) -> str:
    """通用 HTTP GET，返回原始字符串，失败抛异常"""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _news_from_sina(today_str: str) -> List[Tuple[str, str, str]]:
    """
    新浪财经滚动新闻
    返回 List[(time_hhmm, title, source_tag)]
    """
    try:
        url = (
            "https://feed.mix.sina.com.cn/api/roll/get"
            "?pageid=153&lid=2516&k=&num=30&page=1&r=0.1"
        )
        raw = _http_get(url, {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn",
        })
        items = json.loads(raw).get("result", {}).get("data", [])
        result = []
        for item in items:
            title = (item.get("title") or "").strip()
            ctime = item.get("ctime", 0)
            try:
                dt = datetime.fromtimestamp(int(ctime))
                time_str = dt.strftime("%H:%M")
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                continue
            if title and date_str == today_str:
                result.append((time_str, title, "新浪"))
        return result
    except Exception:
        return []


def _news_from_jin10(today_str: str) -> List[Tuple[str, str, str]]:
    """
    金十数据 Flash 快讯（flash-api.jin10.com A股/财经分类）
    channel=-8200, classify=[29]
    过滤今日、中文条目，去除HTML标签
    返回 List[(time_hhmm, content, source_tag)]
    """
    try:
        import urllib.parse
        url = "https://flash-api.jin10.com/get_flash_list?channel=-8200&vip=1&classify=%5B29%5D"
        raw = _http_get(url, {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "sec-ch-ua-platform": '"Windows"',
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"
            ),
            "x-app-id": "bVBF4FyRTn5NJF5n",
            "x-version": "1.0.0",
        })
        data = json.loads(raw)
        # 新接口返回格式：{"status": 200, "message": "OK", "data": [...]}
        # data 字段直接是列表
        items = []
        if isinstance(data, dict):
            raw_data = data.get("data", [])
            if isinstance(raw_data, list):
                items = raw_data
            elif isinstance(raw_data, dict):
                items = raw_data.get("items") or raw_data.get("data") or []
        elif isinstance(data, list):
            items = data

        result = []
        for item in items:
            # 时间字段可能是 created_at 或 time
            time_raw = item.get("created_at") or item.get("time", "")
            # 内容字段
            if isinstance(item.get("data"), dict):
                content = (item["data"].get("content") or "").strip()
                title = (item["data"].get("title") or "").strip()
            else:
                content = (item.get("content") or "").strip()
                title = (item.get("title") or "").strip()
            text = title or content
            if not text:
                continue
            # 清理 HTML 标签
            text = re.sub(r"<[^>]+>", "", text).strip()
            if not text:
                continue
            # 优化金十条目显示：若形如【标题】金十数据...，则仅取方括号内标题
            bracket_match = re.match(r"^【(.+?)】", text)
            if bracket_match:
                text = bracket_match.group(1).strip()
            # 若超过60字则截断（避免长摘要占版）
            if len(text) > 60:
                text = text[:58] + "…"
            # 解析时间
            try:
                # 支持 "2026-05-11 10:32:06" 和 "2026-05-11T10:32:06+08:00"
                time_clean = time_raw[:19].replace("T", " ")
                dt = datetime.strptime(time_clean, "%Y-%m-%d %H:%M:%S")
                time_str = dt.strftime("%H:%M")
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                continue
            if date_str != today_str:
                continue
            # 跳过纯英文条目
            chinese_chars = len(re.findall(r"[\u4e00-\u9fa5]", text))
            if chinese_chars < 3:
                continue
            # 跳过图示类图片条目
            if "金十图示" in text or "金十图解" in text:
                continue
            result.append((time_str, text, "金十"))
        return result
    except Exception:
        return []


def _news_from_yicai(today_str: str) -> List[Tuple[str, str, str]]:
    """
    第一财经快讯（yicai.com brieflist API）
    返回 List[(time_hhmm, title, source_tag)]
    """
    try:
        url = "https://www.yicai.com/api/ajax/getbrieflist?page=1&pagesize=20&id=0"
        raw = _http_get(url, {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9",
            "referer": "https://www.yicai.com/brief/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
            ),
            "x-requested-with": "XMLHttpRequest",
        })
        items = json.loads(raw)
        result = []
        for item in items:
            create_date = item.get("CreateDate", "")
            title = (item.get("LiveTitle") or item.get("NewsTitle") or "").strip()
            if not title:
                continue
            try:
                dt = datetime.strptime(create_date[:19], "%Y-%m-%dT%H:%M:%S")
                time_str = dt.strftime("%H:%M")
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                continue
            if date_str != today_str:
                continue
            result.append((time_str, title, "一财"))
        return result
    except Exception:
        return []


def _is_relevant_news(title: str) -> bool:
    """
    过滤新闻：保留股票、财经、公司相关；过滤国际政治、战事等无关内容
    返回 True 表示保留，False 表示过滤掉
    """
    # 过滤关键词（国际政治/战事/外交/体育/娱乐/美股等）
    _filter_keywords = [
        # 国际/外交/美股
        "美伊", "美股", "道琼斯", "纳斯达克", "标普500",
        "伊朗", "以色列", "俄罗斯", "乌克兰", "朝鲜", "朝鲜半岛",
        "美联储", "鲍威尔", "耶伦",
        "白宫", "拜登", "特朗普", "欧盟", "北约", "联合国",
        "巴以", "加沙", "哈马斯", "胡塞", "中东", "叙利亚",
        "印巴", "印度", "巴基斯坦", "缅甸", "阿富汗",
        # 体育/娱乐
        "奥运", "世界杯", "NBA", "足球", "篮球", "演唱会", "电影",
        # 其他无关
        "地震", "台风", "洪水", "疫情",
    ]
    for kw in _filter_keywords:
        if kw in title:
            return False

    # 保留关键词（只要含有以下词之一就保留）
    _keep_keywords = [
        "股", "A股", "港股", "上证", "深证", "创业板", "科创板", "北交所",
        "基金", "ETF", "债券", "可转债", "打新", "新股",
        "公司", "企业", "集团", "股份", "科技", "银行", "保险",
        "券商", "证券", "资本", "投资", "并购", "重组", "定增",
        "财经", "金融", "经济", "货币", "利率", "通胀", "CPI", "PMI",
        "央行", "人民银行", "证监会", "交易所", "公告",
        "涨停", "跌停", "涨幅", "跌幅", "成交",
        "营收", "净利", "利润", "业绩", "财报", "分红",
        "指数", "板块", "题材", "龙头",
    ]
    for kw in _keep_keywords:
        if kw in title:
            return True

    # 默认保留（避免过度过滤）
    return True


def _fetch_market_news(num: int = 10) -> List[str]:
    """
    获取今日财经快讯（多源聚合：新浪财经 + 金十数据 + 第一财经）

    策略：
    - 三个来源并行（顺序）抓取，合并去重（按标题相似度简单去重）
    - 按时间倒序排列（最新在前）
    - 取前 num 条
    返回格式：["HH:MM [来源] 标题", ...]
    """
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 三源抓取
    sina_news = _news_from_sina(today_str)
    jin10_news = _news_from_jin10(today_str)
    yicai_news = _news_from_yicai(today_str)

    # 合并
    all_news: List[Tuple[str, str, str]] = []
    all_news.extend(sina_news)
    all_news.extend(jin10_news)
    all_news.extend(yicai_news)

    # 按时间倒序
    all_news.sort(key=lambda x: x[0], reverse=True)

    # 简单去重：标题前20字相同则视为重复，保留第一条（时间最新）
    seen_prefixes: set = set()
    deduped: List[str] = []
    for time_str, title, source in all_news:
        prefix = title[:20]
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)
        # 过滤无关新闻
        if not _is_relevant_news(title):
            continue
        # 字数限制：超过40字截断
        if len(title) > 40:
            title = title[:38] + '…'
        deduped.append(title)
        if len(deduped) >= num:
            break

    return deduped


# ============================================================
# 打新日历（新股 + 新债）
# ============================================================
def _fetch_ipo_calendar(days_ahead: int = 14) -> Dict[str, List[Dict]]:
    """
    获取未来 days_ahead 天内的新股申购日历
    数据源：东方财富 RPTA_APP_IPOAPPLY
    返回 {"ipo": [...], "bond": [...]}
    """
    result = {"ipo": [], "bond": []}
    today = datetime.now().date()
    deadline = today + timedelta(days=days_ahead)

    # ---- 新股 ----
    try:
        url = (
            "https://datacenter-web.eastmoney.com/api/data/v1/get"
            "?reportName=RPTA_APP_IPOAPPLY&columns=ALL"
            "&pageNumber=1&pageSize=30"
            "&sortTypes=-1&sortColumns=APPLY_DATE"
            "&source=WEB&client=WEB"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        items = data.get("result", {}).get("data") or []
        for item in items:
            apply_date_raw = item.get("APPLY_DATE") or ""
            apply_date = apply_date_raw[:10] if apply_date_raw else ""
            try:
                ad = datetime.strptime(apply_date, "%Y-%m-%d").date()
            except Exception:
                continue
            if ad < today or ad > deadline:
                continue
            name = item.get("SECURITY_NAME_ABBR") or item.get("SECURITY_CODE") or "未知"
            code = item.get("APPLY_CODE") or item.get("SECURITY_CODE") or "--"
            market = item.get("MARKET_TYPE_NEW") or item.get("TRADE_MARKET") or "--"
            issue_price = item.get("ISSUE_PRICE")
            price_str = f"{issue_price:.2f}元" if issue_price else "待定"
            result["ipo"].append({
                "date": apply_date,
                "name": name,
                "apply_code": code,
                "market": market,
                "price": price_str,
            })
    except Exception:
        pass

    # ---- 新债（可转债）：遍历所有页，找近期上市/发行的 ----
    try:
        all_bonds = []
        for page in range(1, 7):
            url = (
                "https://datacenter-web.eastmoney.com/api/data/v1/get"
                "?reportName=RPT_BOND_CB_LIST"
                "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,VALUE_DATE,LISTING_DATE,BOND_START_DATE,ISSUE_PRICE,RATING"
                f"&pageNumber={page}&pageSize=200&source=WEB&client=WEB"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode("utf-8"))
            items = data.get("result", {}).get("data") or []
            all_bonds.extend(items)

        # 找申购/发行日在今天~deadline范围内的
        for item in all_bonds:
            # BOND_START_DATE 是申购起始日，VALUE_DATE 是发行日，优先用前者
            date_raw = item.get("BOND_START_DATE") or item.get("VALUE_DATE") or ""
            apply_date = date_raw[:10] if date_raw else ""
            try:
                ad = datetime.strptime(apply_date, "%Y-%m-%d").date()
            except Exception:
                continue
            # 向前回看7天（可能今天还在申购中）
            if ad < today - timedelta(days=2) or ad > deadline:
                continue
            name = item.get("SECURITY_NAME_ABBR") or "--"
            code = item.get("SECURITY_CODE") or "--"
            rating = item.get("RATING") or "--"
            issue_price = item.get("ISSUE_PRICE")
            price_str = f"{issue_price:.2f}元" if issue_price else "100元"
            listing_raw = item.get("LISTING_DATE") or ""
            listing = listing_raw[:10] if listing_raw else "待定"
            result["bond"].append({
                "date": apply_date,
                "name": name,
                "code": code,
                "rating": rating,
                "price": price_str,
                "listing": listing,
            })
        # 去重（SECURITY_NAME_ABBR）并按日期排序
        seen = set()
        deduped = []
        for b in sorted(result["bond"], key=lambda x: x["date"]):
            if b["name"] not in seen:
                seen.add(b["name"])
                deduped.append(b)
        result["bond"] = deduped
    except Exception:
        pass

    return result


class ReportAgent:
    """
    报告生成Agent
    
    支持HTML、Markdown、JSON格式报告，以及邮件发送
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger("AInvest.ReportAgent")
        
        # 确保输出目录存在
        output_dir = Path(config.report.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化邮件发送器
        self.email_sender = EmailSender(config.email)
        
    def generate(
        self,
        results: List[ScanResult],
        analysis: Optional[MarketAnalysis] = None,
        format: str = "html",
        template: Optional[str] = None,
        strategy_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        生成分析报告
        
        Args:
            results: 扫描结果
            analysis: 市场分析
            format: 报告格式 (html/markdown/json)
            template: 模板名称
            strategy_context: 策略上下文（含子策略 Top 10，用于 MD 附件）
            
        Returns:
            报告文件路径
        """
        self.logger.info(f"生成{format}格式报告...")
        
        template = template or self.config.report.template
        
        # 创建报告生成器
        generator = ReportGenerator(
            template=template,
            config=self.config
        )
        
        # 生成报告
        timestamp = datetime.now().strftime("%y-%m-%d %H-%M")
        
        if format == "html":
            filename = f"scan_report_{timestamp}.html"
        elif format == "markdown":
            filename = f"scan_report_{timestamp}.md"
        elif format == "json":
            filename = f"scan_report_{timestamp}.json"
        else:
            raise ValueError(f"不支持的格式: {format}")
        
        output_path = Path(self.config.report.output_dir) / filename
        
        # 生成内容
        content = generator.generate(
            results=results,
            analysis=analysis,
            format=format,
        )
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        self.logger.info(f"报告已保存: {output_path}")
        
        return str(output_path)
    
    def generate_summary(
        self,
        results: List[ScanResult],
        market_state: Optional[str] = None,
        strategy_weights: Optional[Dict[str, float]] = None
    ) -> str:
        """
        生成丰富的文本摘要（用于邮件发送）

        模块顺序：
          ① 报告标题
          ② 每日一言
          ③ 财经动态
          ④ 打新日历（新股 & 新债）
          ⑤ 策略配置
          ⑥ 股票选择
          ⑦ 操作建议
          ⑧ 今日总结
          ⑨ 风险提示
        """
        lines = []
        today = datetime.now().strftime('%Y年%m月%d日')
        now = datetime.now().strftime('%H:%M')
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekdays[datetime.now().weekday()]

        # ── ② 每日一言 ─────────────────────────────────
        lines.append("")
        lines.append("━" * 60)
        lines.append("【每日一言】")
        lines.append("━" * 60)
        lines.append(_fetch_daily_quote())

        # ── ③ 财经动态 ─────────────────────────────────
        lines.append("")
        lines.append("━" * 60)
        lines.append("【财经动态】")
        lines.append("━" * 60)
        news_list = _fetch_market_news(num=10)
        if news_list:
            for news in news_list:
                lines.append(f"◆ {news}")
        else:
            lines.append("• 暂无今日财经快讯（数据获取失败）")

        # ── ④ 打新日历 ─────────────────────────────────
        lines.append("")
        lines.append("━" * 60)
        lines.append("【打新日历】（近14天新股 & 新债）")
        lines.append("━" * 60)
        calendar = _fetch_ipo_calendar(days_ahead=14)
        ipo_list = calendar.get("ipo", [])
        bond_list = calendar.get("bond", [])

        has_any = False
        # 新股（紧凑单行）
        for item in sorted(ipo_list, key=lambda x: x["date"]):
            lines.append(
                f"▶ [新股] {item['date']}  {item['name']}  {item['apply_code']}  {item['price']}  {item['market']}"
            )
            has_any = True
        # 新债（紧凑单行）
        for item in sorted(bond_list, key=lambda x: x["date"]):
            lines.append(
                f"▶ [新债] {item['date']}  {item['name']}  {item['code']}  {item['rating']}  {item['price']}  上市:{item['listing']}"
            )
            has_any = True
        if not has_any:
            lines.append("• 近14天暂无新股/新债申购安排")

        # ── ⑤ 策略配置 ─────────────────────────────────
        state_map = {
            "trend_up": "上涨趋势",
            "trend_down": "下跌趋势",
            "volatile": "震荡市",
        }
        state_desc = state_map.get(market_state, "震荡市") if market_state else "震荡市"
        weight_descs = {
            "volume_surge": "放量上涨",
            "turnover_rank": "成交额排名",
            "multi_factor": "多因子",
            "ai_technical": "AI技术面",
            "institution": "机构追踪",
        }
        w = strategy_weights or {}

        lines.append("")
        lines.append("━" * 60)
        lines.append("【策略配置】")
        lines.append("━" * 60)
        lines.append(f"• 市场状态：{state_desc}（系统自动判断）")
        if w:
            weight_parts = [
                f"{weight_descs.get(k, k)} {v*100:.0f}%"
                for k, v in sorted(w.items(), key=lambda x: -x[1]) if v > 0
            ]
            lines.append(f"• 策略权重：{' + '.join(weight_parts)}")
        else:
            lines.append("• 策略权重：放量上涨 25% + 成交额排名 25% + 多因子 25% + AI技术面 15% + 机构追踪 10%")

        # ── ⑥ 策略命中 Top 15 & 操作建议 ─────────────────────────────────
        lines.append("")
        lines.append("━" * 60)
        lines.append("【策略命中 Top 15 & 操作建议】")
        lines.append("━" * 60)

        if not results:
            lines.append("今日暂无符合条件的股票。")
        else:
            up_count = sum(1 for r in results if r.data and r.data.change_pct > 0)
            avg_change = (
                sum(r.data.change_pct if r.data else 0 for r in results) / len(results)
                if results else 0
            )
            total_amount = sum(r.data.amount if r.data else 0 for r in results)

            lines.append(f"• 共筛选出 {len(results)} 只优质股票  |  上涨 {up_count} 只  |  平均 {avg_change:+.2f}%  |  总成交额 {total_amount/1e8:.2f}亿")

            # Top 15 列表（统一卡片格式，无颜色边框）
            for i, result in enumerate(results[:15], 1):
                name = result.name
                symbol = result.symbol
                score = result.score

                if result.data:
                    change_pct = result.data.change_pct
                    amount = result.data.amount
                    amount_str = (
                        f"{amount/1e8:.2f}亿" if amount >= 1e8
                        else f"{amount/1e4:.0f}万"
                    )
                    change_str = f"{change_pct:+.2f}%"
                    price_str = f"{result.data.close:.2f}元"
                else:
                    amount_str = "N/A"
                    change_str = "N/A"
                    price_str = "N/A"

                sig_str = " / ".join(result.signals[:3]) if result.signals else ""
                lines.append(f"▶ {i}. {name}（{symbol}）  评分：{score:.1f}")
                lines.append(f"   涨幅：{change_str}  成交额：{amount_str}  现价：{price_str}  策略：{sig_str}")

            if len(results) > 15:
                lines.append(f"• 还有 {len(results) - 15} 只备选股票（详见附件）")

            # 操作建议（5只，合并在同一样式下）
            lines.append("")
            lines.append("◆ 操作建议（Top 5）")
            for i, result in enumerate(results[:5], 1):
                current_price = result.data.close if result.data else 0
                entry_price = current_price * 0.98
                stop_loss = current_price * 0.95
                take_profit = current_price * 1.08

                score = result.score
                sig_count = len(result.signals)
                base_win_rate = 50 + (score - 60) / 40 * 30 if score >= 60 else 50
                bonus = min(sig_count * 3, 15)
                price_bonus = (
                    min(max(result.data.change_pct, 0) * 0.5, 5)
                    if result.data else 0
                )
                win_rate = min(round(base_win_rate + bonus + price_bonus, 1), 90.0)

                lines.append(f"▶ {i}. {result.name}（{result.symbol}）  评分：{result.score:.1f}  胜率：{win_rate:.1f}%")
                lines.append(f"   买入：{entry_price:.2f}元  止损：{stop_loss:.2f}元（-5%）  止盈：{take_profit:.2f}元（+8%）")

        # ── ⑦ 今日总结 ─────────────────────────────────
        lines.append("")
        lines.append("━" * 60)
        lines.append("【今日总结】")
        lines.append("━" * 60)
        if results:
            top_stock = results[0]
            lines.append(
                f"• 本次扫描共产出 {len(results)} 只候选股，"
                f"最高评分为 {top_stock.name}（{top_stock.symbol}），"
                f"综合得分 {top_stock.score:.1f}"
            )
            up_pct = sum(1 for r in results if r.data and r.data.change_pct > 0) / len(results) * 100
            lines.append(f"• 候选股上涨比例 {up_pct:.0f}%，当前市场情绪偏{'多' if up_pct >= 60 else '空' if up_pct <= 40 else '中性'}")
            lines.append(f"• 建议重点关注评分 ≥ 75 的个股，结合盘面走势决策")
            if ipo_list:
                near = ipo_list[0]
                lines.append(f"• 近期打新提醒：{near['name']} 申购日 {near['date']}，申购代码 {near['apply_code']}")
            if bond_list:
                near_bond = bond_list[0]
                lines.append(f"• 近期新债提醒：{near_bond['name']} 申购日 {near_bond['date']}，评级 {near_bond['rating']}")
        else:
            lines.append("• 今日暂无符合条件的候选股票，建议观望等待机会")
            lines.append("• 可适当关注指数表现，把握整体市场节奏")

        lines.append("")

        return '\n'.join(lines)
    
    def send_email(
        self,
        results: List[ScanResult],
        analysis: Optional[MarketAnalysis] = None,
        strategy_name: str = "量化选股",
        format: str = "html",
        strategy_context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        生成报告并发送邮件
        """
        # 生成报告文件
        report_path = self.generate(results, analysis, format)
        
        ctx = strategy_context or {}
        
        # 同时生成Markdown版本作为附件
        md_path = None
        if format == "html":
            md_path = self.generate(
                results, analysis, "markdown",
                strategy_context=ctx
            )
        
        # 读取HTML内容
        with open(report_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # 生成摘要
        summary = self.generate_summary(
            results,
            market_state=ctx.get("market_state"),
            strategy_weights=ctx.get("weights")
        )
        
        attachments = [md_path] if md_path else []
        
        success = self.email_sender.send_report(
            results_summary=summary,
            html_content=html_content,
            strategy_name=strategy_name,
            attachments=attachments
        )
        
        if success:
            self.logger.info(f"报告已发送邮件: {report_path}")
            if md_path:
                self.logger.info(f"MD附件已发送: {md_path}")
        else:
            self.logger.error("邮件发送失败")
        
        return success
    
    def test_email(self) -> bool:
        """测试邮件配置"""
        return self.email_sender.test_connection()
