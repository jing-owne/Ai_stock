"""
统一日志工厂

用法：
    from src.common.logger import get_logger

    logger = get_logger("EmailSender")    # → "AInvest.EmailSender"
    logger = get_logger("BondReminder")   # → "AInvest.BondReminder"
"""
import logging


_DEFAULT_PREFIX = "AInvest"


def get_logger(name: str, prefix: str = _DEFAULT_PREFIX) -> logging.Logger:
    """
    获取带统一前缀的 logger

    Args:
        name: 模块/组件名称，如 "EmailSender", "DataFetcher"
        prefix: 前缀，默认 "AInvest"

    Returns:
        logging.Logger 实例
    """
    return logging.getLogger(f"{prefix}.{name}")


def setup_root_logger(level: int = logging.INFO, fmt: str = None) -> None:
    """
    初始化根日志配置（通常在 CLI/脚本入口调用一次）

    Args:
        level: 日志级别
        fmt: 格式字符串，默认包含时间戳+级别+消息
    """
    fmt = fmt or '%(asctime)s [%(levelname)s] %(message)s'
    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt='%H:%M:%S',
    )
