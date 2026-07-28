"""
推荐记录跟踪器（追加式）

存储：<项目根>/data/tracking/recommendations.jsonl
每次策略执行（邮件发送）后追加本次推荐的 15~25 只标的 + 发送时价格。
"""
import json
import logging
from pathlib import Path
from datetime import datetime, time
from typing import List, Optional, Tuple

from .models import RecommendationRecord, StrategyMode, RunType, TradingSession
from .limiter import can_buy, limit_status

logger = logging.getLogger("AInvest.Tracker")

TRACKING_DIR = Path(__file__).parent.parent.parent / "data" / "tracking"
TRACKING_FILE = TRACKING_DIR / "recommendations.jsonl"


class RecommendationTracker:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else TRACKING_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ───────────────────────────────────────────────
    # 追加记录（邮件发送钩子调用）
    # ───────────────────────────────────────────────
    def record(
        self,
        results: List,           # List[ScanResult]
        mode: str,
        send_date: Optional[str] = None,
        hold_style: str = "fast",
        max_records: int = 25,
        run_id: Optional[str] = None,
        run_time: Optional[str] = None,
        run_type: str = RunType.LIVE.value,
        strategy_name: str = "composite",
        email_subject: str = "",
        email_sent: Optional[bool] = None,
        report_path: str = "",
        md_attachment_path: str = "",
        force: bool = False,
        now: Optional[datetime] = None,
    ) -> int:
        """追加本次推荐的标的（取前 max_records 只）。返回新增条数。"""
        now = now or datetime.now()
        if send_date is None:
            send_date = now.strftime("%Y-%m-%d")
        if run_time is None:
            run_time = now.strftime("%Y-%m-%d %H:%M:%S")
        mode_value = StrategyMode.from_label(mode).value
        if run_id is None:
            run_id = f"{now.strftime('%Y%m%d_%H%M%S')}_{mode_value}"

        session, exclude_reason = classify_trading_session(now)
        try:
            normalized_run_type = RunType(run_type).value
        except ValueError:
            normalized_run_type = RunType.LIVE.value
        countable = normalized_run_type == RunType.LIVE.value and session == TradingSession.REGULAR.value

        if normalized_run_type == RunType.LIVE.value and not countable and not force:
            logger.info(
                "非交易时间推荐不入账: session=%s reason=%s run_id=%s",
                session, exclude_reason, run_id
            )
            return 0

        added = 0
        with open(self.path, "a", encoding="utf-8") as f:
            for rank, r in enumerate(results[:max_records], 1):
                price = r.data.close if r.data else 0.0
                amount = r.data.amount if r.data else 0.0
                status = limit_status(r.data) if r.data else "unknown"
                can_buy_now = can_buy(r.data) if r.data else False
                # ── 标签记录：模式 / 排名档 / 涨跌停可买性 / 命中策略 / 信号 ──
                mode_tag = {
                    StrategyMode.NEW.value: "新策略",
                    StrategyMode.OLD.value: "旧策略",
                }.get(mode_value, "未知")
                rank_tag = "头部5" if rank <= 5 else ("前10" if rank <= 10 else "后排")
                if status == "limit_up":
                    limit_tag = "涨停不可买" if not can_buy_now else "涨停"
                elif status == "limit_down":
                    limit_tag = "跌停"
                else:
                    limit_tag = "可买入"
                hit_tags = [f"命中{h}" for h in (r.metadata.get("hit_strategies", []) or [])[:3]]
                sig_tags = [f"信号{s}" for s in (getattr(r, "signals", []) or [])[:2]]
                tags = [mode_tag, rank_tag, limit_tag] + hit_tags + sig_tags
                rec = RecommendationRecord(
                    date=send_date,
                    mode=mode_value,
                    symbol=r.symbol,
                    name=r.name,
                    send_price=price,
                    score=r.score,
                    rank=rank,
                    hit_strategies=list(r.metadata.get("hit_strategies", [])),
                    source_track=r.metadata.get("source_track", ""),
                    amount=amount,
                    hold_style=hold_style,
                    run_id=run_id,
                    run_time=run_time,
                    run_type=normalized_run_type,
                    trading_session=session,
                    is_countable=countable,
                    exclude_reason="" if countable else exclude_reason or normalized_run_type,
                    strategy_name=strategy_name,
                    signals=list(getattr(r, "signals", []) or []),
                    limit_status_at_recommend=status,
                    can_buy_at_recommend=can_buy_now,
                    email_subject=email_subject,
                    email_sent=email_sent,
                    report_path=report_path,
                    md_attachment_path=md_attachment_path,
                    tags=tags,
                )
                f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
                added += 1
        logger.info(
            "已追加 %s 条推荐(mode=%s, date=%s, run_type=%s, session=%s) → %s",
            added, mode_value, send_date, normalized_run_type, session, self.path
        )
        if added:
            self.mark_overlaps(send_date=send_date, run_type=normalized_run_type)
        return added

    # ───────────────────────────────────────────────
    # 读取 / 写入
    # ───────────────────────────────────────────────
    def load_all(self) -> List[RecommendationRecord]:
        if not self.path.exists():
            return []
        recs: List[RecommendationRecord] = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(RecommendationRecord.from_dict(json.loads(line)))
                except Exception as e:
                    logger.warning(f"跳过损坏记录: {e}")
        return recs

    def pending(self, max_window: int = 10) -> List[RecommendationRecord]:
        """观测窗口未满的记录（用于增量计算收益）"""
        return [
            r for r in self.load_all()
            if r.is_countable and r.observed_days < max_window
        ]

    def save(self, recs: List[RecommendationRecord]) -> None:
        """整体重写（用于回填收益后持久化）"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")

    def mark_overlaps(
        self,
        send_date: Optional[str] = None,
        run_type: Optional[str] = None,
    ) -> int:
        """标记同一日期同一标的被新旧策略共同命中。"""
        recs = self.load_all()
        buckets = {}
        for r in recs:
            if send_date and r.date != send_date:
                continue
            if run_type and r.run_type != run_type:
                continue
            key = (r.date, r.run_type, r.symbol)
            buckets.setdefault(key, set()).add(r.mode)

        overlap_keys = {
            key for key, modes in buckets.items()
            if StrategyMode.NEW.value in modes and StrategyMode.OLD.value in modes
        }

        changed = 0
        for r in recs:
            key = (r.date, r.run_type, r.symbol)
            new_value = key in overlap_keys
            if r.overlap != new_value:
                r.overlap = new_value
                changed += 1
            # 共识票标签：新旧共同命中才打标，避免重复累积
            if new_value and "共识票" not in r.tags:
                r.tags = [t for t in r.tags if t != "共识票"] + ["共识票"]
                changed += 1
            elif not new_value and "共识票" in r.tags:
                r.tags = [t for t in r.tags if t != "共识票"]
                changed += 1
        if changed:
            self.save(recs)
            logger.info("已更新共同命中标记: %s 条", changed)
        return changed


def classify_trading_session(now: Optional[datetime] = None) -> Tuple[str, str]:
    """按A股连续竞价时间粗分交易时段。

    v1 只做本地时间 + 周末判断；节假日精确日历后续接入。
    """
    now = now or datetime.now()
    if now.weekday() >= 5:
        return TradingSession.NON_TRADING_DAY.value, "非交易日"

    t = now.time()
    if time(9, 15) <= t < time(9, 30):
        return TradingSession.CALL_AUCTION.value, "集合竞价"
    if t < time(9, 30):
        return TradingSession.PRE_MARKET.value, "非交易时间"
    if time(9, 30) <= t <= time(11, 30):
        return TradingSession.REGULAR.value, ""
    if time(11, 30) < t < time(13, 0):
        return TradingSession.LUNCH_BREAK.value, "午间休市"
    if time(13, 0) <= t <= time(15, 0):
        return TradingSession.REGULAR.value, ""
    return TradingSession.AFTER_CLOSE.value, "非交易时间"


def is_regular_trading_time(now: Optional[datetime] = None) -> bool:
    session, _ = classify_trading_session(now)
    return session == TradingSession.REGULAR.value
