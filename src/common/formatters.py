"""
公共数值格式化工具

纯数值→文本转换，不依赖 HTML/CSS。
所有业务模块统一调用，保证金额、百分比、评分等格式一致。
"""


def format_amount(amount: float, precision: int = 2) -> str:
    """
    格式化成交额/金额

    Examples:
        format_amount(150_000_000_000) -> "1500.00亿"
        format_amount(85_000_000)       -> "8500.00万"
        format_amount(1_234_567)       -> "123.46万"
        format_amount(500_000)         -> "50.00万"
        format_amount(99_999)          -> "99999"
    """
    if amount >= 1_000_000_000_000:  # 万亿
        return f"{amount / 1_000_000_000_000:.{precision}f}万亿"
    elif amount >= 100_000_000_000:   # 百亿级仍用亿
        return f"{amount / 100_000_000:.{precision}f}亿"
    elif amount >= 1_000_000_000:     # 亿
        return f"{amount / 1_000_000_000:.{precision}f}亿"
    elif amount >= 10_000:            # 万
        return f"{amount / 10_000:.{precision}f}万"
    else:
        return f"{amount:.0f}"


def format_change(pct: float, show_sign: bool = True) -> str:
    """
    格式化涨跌幅百分比

    Examples:
        format_change(3.56)   -> "+3.56%"
        format_change(-1.23)  -> "-1.23%"
        format_change(0.0)    -> "0.00%"
        format_change(3.56, False) -> "3.56%"
    """
    sign = "+" if show_sign and pct > 0 else ""
    return f"{sign}{pct:.2f}%"


def format_score(score: float, precision: int = 1) -> str:
    """
    格式化评分

    Examples:
        format_score(85.3) -> "85.3"
        format_score(60.0) -> "60.0"
    """
    return f"{score:.{precision}f}"


def format_price(price: float, precision: int = 2) -> str:
    """
    格式化价格

    Examples:
        format_price(15.68)  -> "15.68"
        format_price(100.0)  -> "100.00"
    """
    return f"{price:.{precision}f}"


def format_count(count: int, unit: str = "") -> str:
    """
    格式化数量（带万/亿单位）

    Examples:
        format_count(3874)     -> "3874"
        format_count(150000)   -> "1.50万"
    """
    if count >= 100_000_000:
        result = f"{count / 100_000_000:.2f}亿"
    elif count >= 100_000:
        result = f"{count / 100_000:.2f}万"
    else:
        result = str(count)
    return f"{result}{unit}" if unit else result


def format_market_arrow(pct: float) -> str:
    if pct > 0.1:
        return "▲"
    elif pct < -0.1:
        return "▼"
    else:
        return "—"


def format_market_line(
    index_name: str,
    price: float,
    change_pct: float,
    arrow: str = None,
) -> str:
    """
    格式化单条市场指数信息行

    Examples:
        format_market_line("沪深300", 3621.5, 1.23)
        -> "📈 沪深300:  3621.50 (+1.23%) 🔺"
    """
    arrow = arrow or format_market_arrow(change_pct)
    return f"📈 {index_name}:  {format_price(price)} ({format_change(change_pct)}) {arrow}"
