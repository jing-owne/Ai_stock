"""
超时熔断工具

Windows 无 signal.alarm，使用 ThreadPoolExecutor + future.result(timeout) 实现
可中断的函数调用超时。超时后线程仍在后台运行（无法强杀），但主流程立即返回，
避免 akshare 等慢调用阻塞主流程。

主要用于包裹 akshare 的批量调用（内部走 push2.eastmoney 子域名，失败重试耗时）。
"""
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Callable, Any, Optional

logger = logging.getLogger("AInvest.TimeoutUtils")


def call_with_timeout(
    func: Callable,
    *args,
    timeout: float = 8.0,
    default: Any = None,
    label: str = "",
    **kwargs
) -> Any:
    """
    在独立线程中执行 func，超时返回 default。

    注意：超时后主流程立即返回 default，后台线程继续运行至结束（无法强杀）。
    必须用 shutdown(wait=False)，否则 `with` 块退出时会阻塞等待后台线程，
    导致超时失效。

    Args:
        func: 要调用的函数
        *args, **kwargs: func 的参数
        timeout: 超时秒数（akshare 批量调用建议 8s）
        default: 超时/异常时返回的默认值
        label: 日志标识（如 "stock_zh_a_spot_em"）

    Returns:
        func 的返回值；超时或异常返回 default
    """
    tag = label or getattr(func, "__name__", "call")
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func, *args, **kwargs)
    try:
        result = future.result(timeout=timeout)
        executor.shutdown(wait=False)
        return result
    except FutureTimeout:
        logger.warning(f"[超时熔断] {tag} 超过 {timeout}s，跳过（后台线程继续）")
        executor.shutdown(wait=False)  # 不等待，立即返回
        return default
    except Exception as e:
        logger.debug(f"[超时熔断] {tag} 异常: {e}")
        executor.shutdown(wait=False)
        return default
