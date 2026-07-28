"""
回测 / 跟踪 数据模型 (v2.8)

设计目标（用户需求）：
  1. 每次策略执行后，把推荐的 15~25 只标的 + 邮件发送时价格 追加记录
  2. 计算次日 / N 日收益（按实测买卖价格，含涨跌停限制：涨停不可买、跌停不可卖）
  3. 100w 资金分配仓位，最大化收益（快进快出 / 长期持有 两种风格）
  4. 连续观察 5~10 天，对比 新策略(4聚合) / 旧策略(10原子) 的可信度
  5. 结构化输出便于展示策略收益率
"""

from dataclasses import dataclass, field, asdict, fields
from typing import List, Optional, Dict, Any
from enum import Enum


class StrategyMode(str, Enum):
    """策略模式：新(4聚合) / 旧(10原子)"""
    NEW = "new"
    OLD = "old"
    UNKNOWN = "unknown"

    @classmethod
    def from_label(cls, label: str) -> "StrategyMode":
        if not label:
            return cls.UNKNOWN
        s = str(label).lower()
        if s == cls.NEW.value:
            return cls.NEW
        if s == cls.OLD.value:
            return cls.OLD
        if "新策略" in s or "聚合" in s:
            return cls.NEW
        if "旧策略" in s or "原子" in s:
            return cls.OLD
        return cls.UNKNOWN


class HoldStyle(str, Enum):
    """持有风格"""
    FAST = "fast"   # 快进快出：次日卖出
    LONG = "long"   # 长期持有：N 日卖出
    T3 = "t3"
    T5 = "t5"
    T10 = "t10"
    STOP = "stop"
    TRAILING = "trailing"


class RunType(str, Enum):
    """记录来源类型"""
    LIVE = "live"
    REPLAY = "replay"
    DEBUG = "debug"


class TradingSession(str, Enum):
    """A股交易时段分类"""
    REGULAR = "regular"
    PRE_MARKET = "pre_market"
    LUNCH_BREAK = "lunch_break"
    AFTER_CLOSE = "after_close"
    NON_TRADING_DAY = "non_trading_day"
    CALL_AUCTION = "call_auction"


@dataclass
class RecommendationRecord:
    """一次策略执行推荐的标的（邮件发送时记录，追加式）"""
    date: str                       # 推荐(发送)日期 YYYY-MM-DD
    mode: str                       # new / old
    symbol: str
    name: str
    send_price: float               # 发送时价格（邮件发送时快照 close）
    score: float
    rank: int                       # 本次推荐中的排名
    hit_strategies: List[str] = field(default_factory=list)
    source_track: str = ""
    amount: float = 0.0             # 发送时成交额(元)
    hold_style: str = "fast"        # fast / long
    run_id: str = ""                # 单次执行ID，同一批推荐共享
    run_time: str = ""              # 执行/邮件发送时间 ISO-like 字符串
    run_type: str = RunType.LIVE.value
    trading_session: str = TradingSession.REGULAR.value
    is_countable: bool = True
    exclude_reason: str = ""
    strategy_name: str = "composite"
    signals: List[str] = field(default_factory=list)
    limit_status_at_recommend: str = "unknown"
    can_buy_at_recommend: bool = True
    email_subject: str = ""
    email_sent: Optional[bool] = None
    report_path: str = ""
    md_attachment_path: str = ""
    overlap: bool = False
    tags: List[str] = field(default_factory=list)     # 标签记录(模式/排名档/涨跌停/命中策略/信号/共识票)

    # ── 观测结果（由 returns 计算后回填，持久化供报告使用）──
    observed_days: int = 0          # 已观测天数 (D+1..)
    returns: Dict[int, float] = field(default_factory=dict)   # hold_day -> return_pct
    trade_return: Optional[float] = None     # 模拟交易收益%(含涨跌停约束)
    trade_executed: bool = True              # 是否实际可建仓(涨停买不到=False)
    max_return: Optional[float] = None       # 观测窗口最大浮盈%
    max_drawdown: Optional[float] = None     # 观测窗口最大浮亏/回撤%
    exit_day: Optional[int] = None           # 模拟交易退出日(D+n)
    exit_reason: str = ""                    # time_exit / stop_loss / take_profit / trailing_stop
    stop_loss_hit: bool = False
    take_profit_hit: bool = False
    trailing_stop_hit: bool = False
    notes: str = ""
    return_since_buy: Optional[float] = None   # 自买入价(发送价)至今最新涨跌幅%，由收益计算回填

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RecommendationRecord":
        data = dict(d)
        # JSON 会把 int key 转成 str，这里读回时恢复，避免 r.returns.get(1) 失效。
        if isinstance(data.get("returns"), dict):
            fixed_returns = {}
            for k, v in data["returns"].items():
                try:
                    fixed_returns[int(k)] = v
                except (TypeError, ValueError):
                    fixed_returns[k] = v
            data["returns"] = fixed_returns
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})
