"""市场态势获取器 — 指数 + 涨跌家数 + 成交额"""
import logging
from typing import Dict, Any

from ...common.timeout_utils import call_with_timeout

logger = logging.getLogger("AInvest.MarketFetcher")


def get_market_overview() -> Dict[str, Any]:
    result = {
        'csi300': None, 'sh_index': None, 'sz_index': None, 'cyb_index': None,
        'volume_ratio': None, 'up_count': 0, 'down_count': 0, 'total_amount': 0,
    }
    try:
        import akshare as ak
        # akshare 内部走 push2.eastmoney 子域名，失败重试耗时长，用超时熔断包裹
        df = call_with_timeout(ak.stock_zh_a_spot_em, timeout=8, default=None, label="stock_zh_a_spot_em")
        if df is not None and not df.empty:
            up = int((df['涨跌幅'] > 0).sum()) if '涨跌幅' in df.columns else 0
            down = int((df['涨跌幅'] < 0).sum()) if '涨跌幅' in df.columns else 0
            total_amt = float(df['成交额'].sum()) if '成交额' in df.columns else 0
            result['up_count'] = up
            result['down_count'] = down
            result['total_amount'] = total_amt
            logger.info(f"获取市场态势: 上涨{up}家, 下跌{down}家, 总成交额{total_amt/1e12:.2f}万亿")
        else:
            logger.warning("市场态势数据获取失败/超时，使用默认值")
    except ImportError:
        logger.warning("akshare未安装，无法获取市场态势数据")
    except Exception as e:
        logger.error(f"获取市场态势失败: {e}")

    try:
        import akshare as ak
        idx_df = call_with_timeout(ak.stock_zh_index_spot_em, timeout=8, default=None, label="stock_zh_index_spot_em")
        if idx_df is not None and not idx_df.empty:
            for idx_name, key in [('上证指数', 'sh_index'), ('深证成指', 'sz_index'),
                                   ('沪深300', 'csi300'), ('创业板指', 'cyb_index')]:
                row = idx_df[idx_df['名称'] == idx_name]
                if not row.empty:
                    r = row.iloc[0]
                    result[key] = {
                        'price': float(r.get('最新价', 0)),
                        'change_pct': float(r.get('涨跌幅', 0)),
                    }
    except Exception as e:
        logger.error(f"获取指数数据失败: {e}")

    return result
