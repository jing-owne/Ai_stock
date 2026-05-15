"""
数据获取模块
获取每日一言、财经新闻等外部数据
"""
import requests
import json
import logging
import re
from typing import List, Dict, Optional, Any


logger = logging.getLogger("AInvest.DataFetcher")


class DataFetcher:
    """数据获取器"""
    
    def __init__(self):
        self.logger = logger
    
    def get_daily_quote(self) -> str:
        """
        获取每日一言（hitokoto）
        
        Returns:
            每日一言文本
        """
        try:
            url = "https://v1.hitokoto.cn/?encode=json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            hitokoto = data.get('hitokoto', '投资有风险，入市需谨慎')
            source = data.get('from', '')
            
            if source:
                return f"{hitokoto} —— {source}"
            else:
                return hitokoto
                
        except Exception as e:
            self.logger.error(f"获取每日一言失败: {e}")
            return "投资有风险，入市需谨慎"
    
    def get_yicai_news(self, page: int = 1, page_size: int = 20) -> List[Dict]:
        """
        获取第一财经新闻
        
        Args:
            page: 页码
            page_size: 每页数量
            
        Returns:
            新闻列表
        """
        try:
            url = f"https://www.yicai.com/api/ajax/getbrieflist?page={page}&pagesize={page_size}&id=0"
            
            headers = {
                'accept': '*/*',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'cache-control': 'no-cache',
                'pragma': 'no-cache',
                'referer': 'https://www.yicai.com/brief/',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'x-requested-with': 'XMLHttpRequest'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            # 第一财经直接返回 list，每项字段：
            # NewsTitle: 标题, indexTitle: 索引标题, CreateDate: 时间
            news_list = []
            if isinstance(data, list):
                news_list = data
            elif isinstance(data, dict):
                if 'data' in data:
                    inner = data['data']
                    if isinstance(inner, list):
                        news_list = inner
                    elif isinstance(inner, dict):
                        news_list = inner.get('list', [])
                else:
                    for key, val in data.items():
                        if isinstance(val, list) and len(val) > 0:
                            news_list = val
                            break
            
            return self._filter_finance_news(news_list, source='yicai')
            
        except Exception as e:
            self.logger.error(f"获取第一财经新闻失败: {e}")
            return []
    
    def get_jin10_news(self, limit: int = 20) -> List[Dict]:
        """
        获取金十数据新闻

        Args:
            limit: 获取数量

        Returns:
            新闻列表
        """
        try:
            from datetime import datetime

            # 金十2026年已废弃旧参数（classify、旧x-app-id），必须使用 max_time + 新认证头
            # 旧接口不带max_time会返回502，因此不再做探测回退
            url = "https://flash-api.jin10.com/get_flash_list"
            params = {
                'channel': '-8200',
                'max_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'vip': '1',
                'limit': str(limit),
            }
            headers = {
                'accept': '*/*',
                'x-token': '8b8c0810-85a9-4bec-8f78-016f7dc24823',
                'x-app-id': 'g93rhHb9DcDptyPb',
                'x-version': '1.0.0',
                'accept-language': 'zh-Hans-CN;q=1'
            }

            response = requests.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()

            data = response.json()
            
            # 金十数据返回格式: {"status": 200, "data": [{id, time, data: {content, title, source}, ...}]}
            news_list = []
            if isinstance(data, dict):
                inner = data.get('data', [])
                if isinstance(inner, list):
                    news_list = inner
            
            return self._filter_finance_news(news_list, source='jin10')
            
        except Exception as e:
            self.logger.error(f"获取金十数据新闻失败: {e}")
            return []
    
    def _filter_finance_news(self, news_list: List[Dict], source: str = 'yicai') -> List[Dict]:
        """
        过滤财经新闻，保留股票、财经、公司相关，过滤无关内容
        
        Args:
            news_list: 原始新闻列表
            source: 数据源（'yicai' 或 'jin10'）
            
        Returns:
            过滤后的新闻列表
        """
        # 需要保留的关键词（股票、财经、公司、产业相关）
        keep_keywords = [
            '股票', '股市', 'A股', '港股', '美股', '创业板', '科创板',
            '财经', '金融', '银行', '保险', '证券', '基金', '债券',
            '公司', '集团', '股份', '有限', '上市', 'IPO', '融资', '中标',
            '涨停', '跌停', '拉升', '下跌', '上涨', '指数', '沪深',
            '上证', '深证', '创业板指', '科创50', '北证', '沪指', '深成指',
            '财报', '业绩', '营收', '利润', '净利润', '亏损', '盈利',
            '收购', '并购', '重组', '分红', '送股', '配股',
            '新能源车', '光伏', '芯片', '半导体', '人工智能', 'AI',
            '房地产', '医药', '消费', '白酒', '家电', '汽车', '锂电',
            '央行', '降息', '降准', '利率', '汇率', '货币政策',
            '经济数据', 'GDP', 'CPI', 'PMI',
            '公告', '减持', '增持', '回购', '股权', '激励',
            '净利润', '营业收入', '中标', '订单', '合同',
            '板块', '题材', '概念', '主力', '资金',
        ]
        
        # 需要过滤的关键词（国际政治、战争、自然灾害、娱乐等）
        filter_keywords = [
            '美伊', '战争', '中东',
            '俄乌', '乌克兰', '俄罗斯', '北约', '军事', '导弹', '核武器',
            '地震', '海啸', '台风', '洪水', '火灾', '爆炸', '极端天气',
            '南非', '灾难', '国家灾难',
            '娱乐', '明星', '电影', '电视剧', '综艺', '球赛', '足球', '篮球',
            '总统', '大选', '议会', '法案', '外交', '制裁',
            '韩前总理', '韩德洙', '古巴', '委内瑞拉', '以色列',
            '美军', '侦察机', '内乱',
        ]
        
        filtered_news = []
        
        for news in news_list:
            # 根据不同数据源提取标题
            if source == 'yicai':
                # 第一财经: NewsTitle / indexTitle
                title = news.get('NewsTitle', '') or news.get('indexTitle', '')
                news_time = news.get('CreateDate', '')
            elif source == 'jin10':
                # 金十数据: data.content (嵌套在data字段中)
                inner = news.get('data', {})
                if isinstance(inner, dict):
                    title = inner.get('title', '') or inner.get('content', '')
                    # 清理金十数据内容格式（去掉【xxx】前缀中的来源标记）
                    title = re.sub(r'^【[^】]+】\s*', '', title)
                    # 截取前80个字符作为标题（金十内容通常很长）
                    if len(title) > 80:
                        title = title[:80] + '...'
                else:
                    title = str(inner)
                news_time = news.get('time', '')
            else:
                title = str(news)
                news_time = ''
            
            if not title:
                continue
            
            # 检查是否包含过滤关键词
            should_filter = any(keyword in title for keyword in filter_keywords)
            if should_filter:
                continue
            
            # 检查是否包含保留关键词（只保留明确与财经相关的内容）
            should_keep = any(keyword in title for keyword in keep_keywords)
            if should_keep:
                filtered_news.append({
                    'title': title,
                    'time': news_time,
                    'source': source
                })
        
        return filtered_news[:15]  # 最多返回15条
    
    def fetch_all_news(self) -> List[Dict]:
        """
        获取所有财经新闻（第一财经 + 金十数据）
        
        Returns:
            合并后的新闻列表
        """
        news_list = []
        
        # 获取第一财经新闻
        yicai_news = self.get_yicai_news()
        news_list.extend(yicai_news)
        
        # 获取金十数据新闻
        jin10_news = self.get_jin10_news()
        news_list.extend(jin10_news)
        
        # 去重（根据标题前30个字符，避免因截取长度不同导致重复）
        seen_titles = set()
        unique_news = []
        for news in news_list:
            title = news.get('title', '')
            title_key = title[:30]  # 用前30字符作为去重key
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_news.append(news)
        
        return unique_news[:15]  # 最多返回15条

    def get_ipo_calendar(self, max_days: int = 7) -> List[Dict]:
        """
        获取近期新股申购日历（通过akshare）

        Args:
            max_days: 最多显示未来几天的可申购新股

        Returns:
            新股申购列表，每项包含: stock_code, stock_name, apply_date,
            apply_code, price, pe, industry_pe, max_shares, market_cap_needed
        """
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
                if not apply_date_str or apply_date_str == '-' or apply_date_str == 'nan':
                    continue

                # 解析申购日期，支持 "05-13 周三" 和 "2026-05-07" 两种格式
                try:
                    if '-' in apply_date_str and '周' in apply_date_str:
                        # "05-13 周三" 格式，补全年份
                        date_part = apply_date_str.split(' ')[0]
                        parsed_date = datetime.strptime(f"{today.year}-{date_part}", "%Y-%m-%d").date()
                    else:
                        parsed_date = datetime.strptime(apply_date_str[:10], "%Y-%m-%d").date()
                except (ValueError, IndexError):
                    continue

                # 只取今天之后 max_days 天内的新股
                if parsed_date < today or parsed_date > cutoff:
                    continue

                stock_code = str(row.get('股票代码', ''))
                stock_name = str(row.get('股票简称', ''))
                apply_code = str(row.get('申购代码', ''))
                price = str(row.get('发行价格', '-'))
                pe = str(row.get('发行市盈率', '-'))
                industry_pe = str(row.get('行业市盈率', '-'))
                max_shares = str(row.get('申购上限（万股）', '-'))
                market_cap = str(row.get('顶格申购需配市值（万元）', '-'))

                ipo_list.append({
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'apply_date': apply_date_str.split(' ')[0] if ' ' in apply_date_str else apply_date_str[:10],
                    'apply_code': apply_code,
                    'price': price if price != '-' and price != 'nan' else '待定',
                    'pe': pe if pe != '-' and pe != 'nan' else '待定',
                    'industry_pe': industry_pe if industry_pe != '-' and industry_pe != 'nan' else '-',
                    'max_shares': max_shares if max_shares != 'nan' else '-',
                    'market_cap_needed': market_cap if market_cap != 'nan' else '-',
                })

            self.logger.info(f"获取打新日历: 未来{max_days}天共{len(ipo_list)}只新股可申购")
            return ipo_list

        except ImportError:
            self.logger.warning("akshare未安装，无法获取打新日历。请执行: pip install akshare")
            return []
        except Exception as e:
            self.logger.error(f"获取打新日历失败: {e}")
            return []

    def get_market_overview(self) -> Dict[str, Any]:
        """
        获取市场态势总览数据（沪深300、上证指数、成交量等）

        Returns:
            dict: {
                'csi300': {'price': float, 'change_pct': float},
                'sh_index': {'price': float, 'change_pct': float},
                'volume_ratio': float,   # 成交量比 (市场总成交额 vs 近期均值)
                'up_count': int,         # 上涨家数
                'down_count': int,       # 下跌家数
                'total_amount': float,   # 市场总成交额
            }
        """
        result = {
            'csi300': None,
            'sh_index': None,
            'sz_index': None,
            'cyb_index': None,
            'volume_ratio': None,
            'up_count': 0,
            'down_count': 0,
            'total_amount': 0,
        }
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                # 计算涨跌家数和总成交额
                up = int((df['涨跌幅'] > 0).sum()) if '涨跌幅' in df.columns else 0
                down = int((df['涨跌幅'] < 0).sum()) if '涨跌幅' in df.columns else 0
                total_amt = float(df['成交额'].sum()) if '成交额' in df.columns else 0
                result['up_count'] = up
                result['down_count'] = down
                result['total_amount'] = total_amt
            self.logger.info(f"获取市场态势: 上涨{up}家, 下跌{down}家, 总成交额{total_amt/1e12:.2f}万亿")
        except ImportError:
            self.logger.warning("akshare未安装，无法获取市场态势数据")
        except Exception as e:
            self.logger.error(f"获取市场态势失败: {e}")

        # 尝试获取主要指数数据
        try:
            import akshare as ak
            idx_df = ak.stock_zh_index_spot_em()
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
            self.logger.error(f"获取指数数据失败: {e}")

        return result
