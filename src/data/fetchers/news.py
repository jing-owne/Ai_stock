"""每日一言 + 财经新闻获取器"""
import requests
import json
import logging
import re
from typing import List, Dict

logger = logging.getLogger("AInvest.NewsFetcher")


def get_daily_quote() -> str:
    """获取每日一言（hitokoto）"""
    try:
        url = "https://v1.hitokoto.cn/?encode=json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        hitokoto = data.get('hitokoto', '投资有风险，入市需谨慎')
        source = data.get('from', '')
        if source:
            return f"{hitokoto} —— {source}"
        return hitokoto
    except Exception as e:
        logger.error(f"获取每日一言失败: {e}")
        return "投资有风险，入市需谨慎"


_KEEP_KEYWORDS = [
    '标的', '股市', 'A股', '港股', '美股', '创业板', '科创板',
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
    '净利润', '营业收入', '订单', '合同',
    '板块', '题材', '概念', '主力', '资金',
]

_FILTER_KEYWORDS = [
    '美伊', '战争', '中东',
    '俄乌', '乌克兰', '俄罗斯', '北约', '军事', '导弹', '核武器',
    '地震', '海啸', '台风', '洪水', '火灾', '爆炸', '极端天气',
    '南非', '灾难', '国家灾难',
    '娱乐', '明星', '电影', '电视剧', '综艺', '球赛', '足球', '篮球',
    '总统', '大选', '议会', '法案', '外交', '制裁',
    '韩前总理', '韩德洙', '古巴', '委内瑞拉', '以色列',
    '美军', '侦察机', '内乱',
]


def _filter_news(news_list: List[Dict], source: str = 'yicai') -> List[Dict]:
    filtered = []
    for news in news_list:
        if source == 'yicai':
            title = news.get('NewsTitle', '') or news.get('indexTitle', '')
        elif source == 'jin10':
            inner = news.get('data', {})
            if isinstance(inner, dict):
                title = inner.get('title', '') or inner.get('content', '')
                title = re.sub(r'^【[^】]+】\s*', '', title)
                if len(title) > 80:
                    title = title[:80] + '...'
            else:
                title = str(inner)
        else:
            title = str(news)
        if not title:
            continue
        if any(kw in title for kw in _FILTER_KEYWORDS):
            continue
        if any(kw in title for kw in _KEEP_KEYWORDS):
            filtered.append({'title': title, 'time': news.get('CreateDate', news.get('time', '')), 'source': source})
    return filtered[:15]


def get_yicai_news(page: int = 1, page_size: int = 20) -> List[Dict]:
    try:
        url = f"https://www.yicai.com/api/ajax/getbrieflist?page={page}&pagesize={page_size}&id=0"
        headers = {
            'accept': '*/*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': 'https://www.yicai.com/brief/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'x-requested-with': 'XMLHttpRequest'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
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
        return _filter_news(news_list, source='yicai')
    except Exception as e:
        logger.error(f"获取第一财经新闻失败: {e}")
        return []


def get_jin10_news(limit: int = 20) -> List[Dict]:
    try:
        from datetime import datetime
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
        news_list = []
        if isinstance(data, dict):
            inner = data.get('data', [])
            if isinstance(inner, list):
                news_list = inner
        return _filter_news(news_list, source='jin10')
    except Exception as e:
        logger.error(f"获取金十数据新闻失败: {e}")
        return []


def fetch_all_news() -> List[Dict]:
    news_list = []
    news_list.extend(get_yicai_news())
    news_list.extend(get_jin10_news())
    seen = set()
    unique = []
    for n in news_list:
        key = n.get('title', '')[:30]
        if key not in seen:
            seen.add(key)
            unique.append(n)
    return unique[:15]
