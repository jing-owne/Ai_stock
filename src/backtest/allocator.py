"""
仓位分配器（100w 资金，最大化收益启发式）

candidates: [{symbol,name,buy_price,expected_return,score,executable}]
  - buy_price: 买入参考价(=发送时价格)
  - expected_return: 预期收益% (默认用模拟交易收益 trade_return)
  - executable: 是否可买(涨停=False 已排除)
  - score: 策略评分

分配方法：
  - equal : 等权
  - score : 权重 ∝ 0.7*max(预期收益,0) + 0.3*评分/100，单只封顶 max_weight(默认20%)
  - kelly : 简化凯利，权重 ∝ 预期收益/100，封顶 max_weight
  - overlap_boost : 新旧共同命中双倍权重，单只封顶可提高到25%

约束：A股整百股；单只不超过 max_weight；余钱留现金。
注：v1 为启发式"最大化"，真正均值-方差优化留待择机调优。
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger("AInvest.Allocator")


@dataclass
class Allocation:
    symbol: str
    name: str
    buy_price: float
    expected_return: float
    weight: float          # 资金占比 0-1
    amount: float          # 分配金额
    shares: int            # 股数（整百）
    note: str = ""


@dataclass
class PortfolioPlan:
    capital: float
    style: str
    allocations: List[Allocation] = field(default_factory=list)
    cash_left: float = 0.0
    expected_return: float = 0.0   # 组合预期收益(%)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capital": self.capital,
            "style": self.style,
            "expected_return": round(self.expected_return, 2),
            "cash_left": round(self.cash_left, 2),
            "positions": [a.__dict__ for a in self.allocations],
        }


class PositionAllocator:
    def __init__(self, capital: float = 1_000_000, max_weight: float = 0.20, method: str = "score"):
        self.capital = capital
        self.max_weight = max_weight
        self.method = method

    def allocate(self, candidates: List[Dict[str, Any]], style: str = "fast") -> PortfolioPlan:
        valid = [c for c in candidates
                 if c.get("executable", True) and c.get("buy_price", 0) > 0]
        if not valid:
            return PortfolioPlan(capital=self.capital, style=style)

        if self.method == "equal":
            weights = {c["symbol"]: 1.0 / len(valid) for c in valid}
        elif self.method == "kelly":
            raw = {c["symbol"]: max(c.get("expected_return", 0.0) / 100.0, 0.0)
                   for c in valid}
            total = sum(raw.values()) or 1.0
            weights = {k: min(v / total, self.max_weight) for k, v in raw.items()}
            weights = self._normalize(weights)
        elif self.method == "overlap_boost":
            raw = {}
            boost_cap = max(self.max_weight, 0.25)
            for c in valid:
                er = max(c.get("expected_return", 0.0), 0.0)
                sc = c.get("score", 0.0) / 100.0
                boost = 2.0 if c.get("overlap") else 1.0
                raw[c["symbol"]] = (er * 0.7 + sc * 0.3 + 0.01) * boost
            total = sum(raw.values()) or 1.0
            weights = {
                k: min(v / total, boost_cap if self._find(valid, k).get("overlap") else self.max_weight)
                for k, v in raw.items()
            }
            weights = self._normalize(weights)
        else:  # score（默认）
            raw = {}
            for c in valid:
                er = max(c.get("expected_return", 0.0), 0.0)
                sc = c.get("score", 0.0) / 100.0
                raw[c["symbol"]] = er * 0.7 + sc * 0.3 + 0.01
            total = sum(raw.values()) or 1.0
            weights = {k: min(v / total, self.max_weight) for k, v in raw.items()}
            weights = self._normalize(weights)

        plan = PortfolioPlan(capital=self.capital, style=style)
        for c in valid:
            w = weights.get(c["symbol"], 0.0)
            amount = self.capital * w
            price = c["buy_price"]
            shares = int(amount // (price * 100)) * 100
            allocated = shares * price
            plan.allocations.append(Allocation(
                symbol=c["symbol"], name=c.get("name", ""),
                buy_price=price, expected_return=c.get("expected_return", 0.0),
                weight=round(w, 4), amount=round(allocated, 2), shares=shares,
                note="共同命中" if c.get("overlap") else "",
            ))
            plan.cash_left += (amount - allocated)
            plan.expected_return += w * c.get("expected_return", 0.0)
        plan.cash_left = round(plan.cash_left, 2)
        plan.expected_return = round(plan.expected_return, 2)
        return plan

    def _normalize(self, weights: Dict[str, float]) -> Dict[str, float]:
        total = sum(weights.values()) or 1.0
        return {k: v / total for k, v in weights.items()}

    def _find(self, candidates: List[Dict[str, Any]], symbol: str) -> Dict[str, Any]:
        for c in candidates:
            if c.get("symbol") == symbol:
                return c
        return {}
