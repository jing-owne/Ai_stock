"""打新日历获取器 — IPO + 可转债"""
import logging
from typing import List, Dict

logger = logging.getLogger("AInvest.CalendarFetcher")


def _parse_apply_date(apply_date_str: str, today):
    """解析申购日期，统一返回 (parsed_date, display_str)"""
    from datetime import datetime
    apply_date_str = apply_date_str.strip()
    if not apply_date_str or apply_date_str in ('-', 'nan', ''):
        return None, ''

    # 格式1: "2026-06-09" (完整日期)
    if apply_date_str.count('-') >= 2 and '周' not in apply_date_str:
        try:
            parsed_date = datetime.strptime(apply_date_str[:10], "%Y-%m-%d").date()
            return parsed_date, parsed_date.strftime('%m-%d')
        except (ValueError, IndexError):
            pass

    # 格式2: "06-15 周一" (含星期)
    if '-' in apply_date_str and '周' in apply_date_str:
        try:
            date_part = apply_date_str.split(' ')[0]
            parsed_date = datetime.strptime(f"{today.year}-{date_part}", "%Y-%m-%d").date()
            return parsed_date, date_part
        except (ValueError, IndexError):
            pass

    # 格式3: 纯 "06-15" (月-日)
    if '-' in apply_date_str:
        try:
            parsed_date = datetime.strptime(f"{today.year}-{apply_date_str}", "%Y-%m-%d").date()
            return parsed_date, apply_date_str
        except (ValueError, IndexError):
            pass

    return None, ''


def get_ipo_calendar(max_days: int = 7) -> List[Dict]:
    try:
        import akshare as ak
        from datetime import datetime, timedelta
        df = ak.stock_ipo_ths()
        if df is None or df.empty:
            return []
        today = datetime.now().date()
        cutoff = today + timedelta(days=max_days)
        ipo_list = []
        for _, row in df.iterrows():
            apply_date_str = str(row.get('申购日期', ''))
            parsed_date, display_date = _parse_apply_date(apply_date_str, today)
            if parsed_date is None:
                continue
            if parsed_date < today or parsed_date > cutoff:
                continue

            # 兼容新旧akshare列名：新API用「股票代码/股票简称」，旧API用「代码/标的简称」
            stock_code = str(row.get('股票代码', row.get('代码', '')))
            stock_name = str(row.get('股票简称', row.get('标的简称', '')))

            ipo_list.append({
                'stock_code': stock_code,
                'stock_name': stock_name,
                'apply_date': parsed_date.strftime('%Y-%m-%d'),  # 完整日期用于排序
                'apply_date_display': display_date,               # MM-DD 用于展示
                'apply_code': str(row.get('申购代码', '')),
                'price': _safe_str(row, '发行价格', '待定'),
                'pe': _safe_str(row, '发行市盈率', '待定'),
                'industry_pe': _safe_str(row, '行业市盈率', '-'),
                'max_shares': _safe_str(row, '申购上限（万股）', '-'),
                'market_cap_needed': _safe_str(row, '顶格申购需配市值（万元）', '-'),
            })

        # 按申购日期排序：最新在前
        ipo_list.sort(key=lambda x: x['apply_date'], reverse=True)

        logger.info(f"获取打新日历: 未来{max_days}天共{len(ipo_list)}只新股可申购")
        return ipo_list
    except ImportError:
        logger.warning("akshare未安装，无法获取打新日历")
        return []
    except Exception as e:
        logger.error(f"获取打新日历失败: {e}")
        return []


def _safe_str(row, col: str, default: str = '-') -> str:
    v = str(row.get(col, default))
    return v if v not in ('-', 'nan', '') else default


def _enrich_bond_ratings(bond_list: List[Dict]) -> None:
    import akshare as ak
    import pandas as pd
    for bond in bond_list:
        bond_code = bond.get('bond_code', '')
        if not bond_code:
            bond['rating'] = '待查'
            bond['max_shares'] = '1000手(10000张)'
            continue
        try:
            df = ak.bond_zh_cov_info(symbol=bond_code)
            if df is not None and not df.empty:
                rating = str(df.iloc[0].get('RATING', ''))
                online_aau = df.iloc[0].get('ONLINE_GENERAL_AAU', None)
                bond['rating'] = rating if rating and rating not in ('nan', 'None', '') else '待查'
                if online_aau and not pd.isna(online_aau):
                    lots = int(online_aau)
                    bond['max_shares'] = f'{lots}手({lots*10}张)'
                else:
                    bond['max_shares'] = '1000手(10000张)'
            else:
                bond['rating'] = '待查'
                bond['max_shares'] = '1000手(10000张)'
        except Exception as e:
            logger.debug(f"获取{bond_code}评级失败: {e}")
            bond['rating'] = '待查'
            bond['max_shares'] = '1000手(10000张)'


def get_bond_calendar(max_days: int = 7) -> List[Dict]:
    import akshare as ak
    import pandas as pd
    from datetime import datetime, timedelta
    import time

    today = datetime.now().date()
    cutoff = today + timedelta(days=max_days)

    # 第1源: bond_zh_cov_info_ths
    try:
        df = ak.bond_zh_cov_info_ths()
        if df is not None and not df.empty and '申购日期' in df.columns:
            bond_list = []
            for _, row in df.iterrows():
                apply_date_str = str(row.get('申购日期', ''))
                if not apply_date_str or apply_date_str in ('nan', 'NaT', '', 'None'):
                    continue
                try:
                    parsed_date = pd.to_datetime(apply_date_str).date()
                except Exception:
                    continue
                if pd.isna(parsed_date) or parsed_date < today or parsed_date > cutoff:
                    continue
                amount = str(row.get('计划发行量', '-'))
                bond_list.append({
                    'bond_name': str(row.get('债券简称', '')),
                    'bond_code': str(row.get('债券代码', '')),
                    'stock_name': str(row.get('正股简称', '')),
                    'apply_date': parsed_date.strftime('%m-%d'),
                    'apply_date_full': parsed_date.strftime('%Y-%m-%d'),
                    'apply_code': _safe_str(row, '申购代码', '-'),
                    'conv_price': _safe_str(row, '转股价格', '待定'),
                    'amount': f'{float(amount):.2f}亿' if amount.replace('.', '').isdigit() else amount,
                    'lottery_date': _safe_str(row, '中签公布日', '-'),
                    'rating': '', 'max_shares': '', 'source': '同花顺',
                })
            if bond_list:
                _enrich_bond_ratings(bond_list)
                logger.info(f"获取可转债日历(同花顺): 未来{max_days}天共{len(bond_list)}只")
                return bond_list
    except Exception as e:
        logger.debug(f"bond_zh_cov_info_ths 失败: {e}")

    # 第2源: bond_cov_comparison
    for attempt in range(2):
        try:
            time.sleep(1)
            df = ak.bond_cov_comparison()
            if df is not None and not df.empty and '申购日期' in df.columns:
                bond_list = []
                for _, row in df.iterrows():
                    apply_date_str = str(row.get('申购日期', ''))
                    if not apply_date_str or apply_date_str in ('nan', 'NaT', ''):
                        continue
                    try:
                        parsed_date = pd.to_datetime(apply_date_str, format='%Y%m%d', errors='coerce').date()
                    except Exception:
                        continue
                    if pd.isna(parsed_date) or parsed_date < today or parsed_date > cutoff:
                        continue
                    bond_list.append({
                        'bond_name': str(row.get('转债名称', '')),
                        'bond_code': str(row.get('转债代码', '')),
                        'stock_name': str(row.get('正股名称', '')),
                        'apply_date': parsed_date.strftime('%m-%d'),
                        'apply_date_full': parsed_date.strftime('%Y-%m-%d'),
                        'conv_price': _safe_str(row, '转股价', '待定'),
                        'rating': _safe_str(row, '评级', '待查'),
                        'source': '东方财富',
                    })
                if bond_list:
                    logger.info(f"获取可转债日历(东财): 未来{max_days}天共{len(bond_list)}只")
                    return bond_list
            break
        except Exception as e:
            logger.debug(f"bond_cov_comparison 第{attempt+1}次失败: {e}")

    # 第3源: stock_ipo_ths 兜底
    try:
        df3 = ak.stock_ipo_ths()
        if df3 is not None and not df3.empty:
            from datetime import datetime as dt
            bond_list = []
            for _, row in df3.iterrows():
                apply_date_str = str(row.get('申购日期', ''))
                if not apply_date_str or apply_date_str in ('-', 'nan', ''):
                    continue
                name = str(row.get('股票简称', row.get('标的简称', '')))
                if '转债' not in name and 'EB' not in name:
                    continue
                try:
                    if '-' in apply_date_str and '周' in apply_date_str:
                        date_part = apply_date_str.split(' ')[0]
                        parsed_date = dt.strptime(f'{today.year}-{date_part}', '%Y-%m-%d').date()
                    else:
                        parsed_date = dt.strptime(apply_date_str[:10], '%Y-%m-%d').date()
                except (ValueError, IndexError):
                    continue
                if parsed_date < today or parsed_date > cutoff:
                    continue
                bond_list.append({
                    'bond_name': name,
                    'bond_code': str(row.get('股票代码', row.get('代码', ''))),
                    'stock_name': name.replace('转债', '').replace('EB', ''),
                    'apply_date': parsed_date.strftime('%m-%d'),
                    'apply_date_full': parsed_date.strftime('%Y-%m-%d'),
                    'conv_price': str(row.get('发行价格', '待定')),
                    'rating': '待查', 'source': '同花顺IPO',
                })
            if bond_list:
                logger.info(f"获取可转债日历(IPO兜底): 未来{max_days}天共{len(bond_list)}只")
                return bond_list
    except Exception as e:
        logger.debug(f"stock_ipo_ths 可转债解析失败: {e}")

    logger.info(f"获取可转债日历: 未来{max_days}天共0只可转债可申购")
    return []
