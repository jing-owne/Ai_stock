"""
数据获取模块
获取每日一言、财经新闻等外部数据
"""
import requests
import json
import logging
import re
from typing import List, Dict, Optional


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
            url = f"https://flash-api.jin10.com/get_flash_list?channel=-8200&vip=1&classify=[29]&limit={limit}"
            
            headers = {
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'x-app-id': 'bVBF4FyRTn5NJF5n',
                'x-version': '1.0.0'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
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
