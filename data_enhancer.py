"""
数据增强模块 - 北向资金与行业信息
"""
import requests
import time
from datetime import datetime, timedelta
import json
import os

# 缓存目录
CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)


class DataEnhancer:
    """数据增强器 - 获取北向资金和行业信息"""

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://quote.eastmoney.com/',
        }
        self.cache_timeout = 300  # 缓存5分钟

    def _get_cache(self, key):
        """获取缓存"""
        cache_file = os.path.join(CACHE_DIR, f"{key}.json")
        if os.path.exists(cache_file):
            mtime = os.path.getmtime(cache_file)
            if time.time() - mtime < self.cache_timeout:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        return None

    def _set_cache(self, key, data):
        """设置缓存"""
        cache_file = os.path.join(CACHE_DIR, f"{key}.json")
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    def get_north_money_data(self, stock_code):
        """
        获取个股北向资金数据
        返回: {
            'north_hold_ratio': 外资持股比例(%),
            'north_hold_change': 近5日持股变化(万股),
            'north_money_status': '增持'/'减持'/'持平',
            'is_connect_stock': 是否为沪深港通标的
        }
        """
        # 标准化股票代码
        code = stock_code.replace('.SH', '').replace('.SZ', '')
        market = '1' if code.startswith(('6', '5')) else '0'  # SH=1, SZ=0

        try:
            # 尝试东方财富接口获取北向持股数据
            url = f"http://push2his.eastmoney.com/api/qt/stock/fflow/kline/get"
            params = {
                'lmt': 5,
                'klt': 101,
                'secid': f"{market}.{code}",
                'fields1': 'f1,f2,f3,f7',
                'fields2': 'f51,f52,f53,f54,f55,f56',
            }

            resp = requests.get(url, params=params, headers=self.headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('data') and data['data'].get('klines'):
                    klines = data['data']['klines']
                    if len(klines) >= 2:
                        # 计算近5日净流入（单位是万元）
                        total = sum(float(k.split(',')[2]) for k in klines)
                        # 判断金额大小
                        if abs(total) > 10000:  # 超过1亿
                            total_wan = total / 10000
                            status = '增持' if total > 0 else '减持' if total < 0 else '持平'
                        else:
                            total_wan = total
                            status = '增持' if total > 100 else '减持' if total < -100 else '持平'
                        return {
                            'north_money_5d': round(total_wan, 2),
                            'north_money_status': status,
                            'is_connect_stock': True
                        }

            return {
                'north_money_5d': 0,
                'north_money_status': '未知',
                'is_connect_stock': False
            }
        except Exception as e:
            return {
                'north_money_5d': 0,
                'north_money_status': '获取失败',
                'is_connect_stock': False
            }

    def get_industry_info(self, stock_code):
        """
        获取个股行业/板块信息
        返回: {
            'industry': 所属行业,
            'concept': 概念板块列表,
            'policy_support': 政策支持程度
        }
        """
        code = stock_code.replace('.SH', '').replace('.SZ', '')
        market = '1' if code.startswith(('6', '5')) else '0'

        # 政策支持行业关键词
        policy_keywords = {
            '强支持': ['新能源', '半导体', '人工智能', '芯片', '高端制造', '机器人',
                     '量子计算', '生物医药', '医疗器械', '信创', '数字经济', '储能',
                     '氢能', '光伏', '风电', '新能源汽车', '智能汽车', '工业互联网', '电气设备'],
            '支持': ['5G', '数据中心', '云计算', '软件', '电子', '军工', '新材料',
                    '化工', '高端装备', '节能环保', '汽车', '通信设备', '机械', '专用设备'],
            '中性': ['银行', '保险', '证券', '房地产', '建筑', '家电', '食品饮料',
                    '纺织服装', '商贸零售', '贸易'],
        }

        # 预定义行业映射表（常用股票行业）
        stock_industry_map = {
            # 电气设备
            '600089': '电气设备', '601012': '电气设备', '002129': '电气设备',
            '600900': '电力', '600025': '电力', '600886': '电力',
            # 汽车/新能源
            '600104': '汽车', '601238': '汽车', '000625': '汽车',
            '600274': '新能源', '002594': '新能源汽车',
            # 半导体/芯片
            '600584': '半导体', '002185': '半导体', '688981': '半导体',
            '603986': '半导体', '002371': '半导体',
            # 电子/消费电子
            '000725': '电子', '601138': '电子', '002456': '电子',
            # 医药
            '600276': '医药', '000538': '医药', '002007': '医疗器械',
            '300760': '医疗器械', '688278': '生物医药',
            # 军工
            '600893': '军工', '002013': '军工', '600760': '军工',
            # 通信
            '000063': '通信设备', '600050': '通信', '601728': '通信',
            # 光伏/储能
            '601615': '新能源', '002459': '光伏', '600438': '光伏',
            # 化工
            '600309': '化工', '601216': '化工', '002064': '化工',
            # 有色金属
            '600111': '有色金属', '000878': '有色金属', '600219': '有色金属',
            '600206': '有色金属',
            # 机械设备
            '600262': '专用设备', '600582': '煤炭装备', '002483': '机械',
            # 建筑/建材
            '601668': '建筑', '600585': '建材', '000786': '建材',
        }

        # 先查预定义映射表
        if code in stock_industry_map:
            industry = stock_industry_map[code]
            policy_level = '中性'
            for level, keywords in policy_keywords.items():
                for kw in keywords:
                    if kw in industry:
                        policy_level = level
                        break
                if policy_level != '中性':
                    break
            return {
                'industry': industry,
                'policy_support': policy_level,
                'is_connect_stock': True
            }

        # 尝试从API获取
        try:
            url = "http://push2.eastmoney.com/api/qt/stock/get"
            params = {
                'secid': f"{market}.{code}",
                'fields': 'f100',
            }
            resp = requests.get(url, params=params, headers=self.headers, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('data'):
                    industry = str(data['data'].get('f100', '')).strip()
                    if industry and industry != '0' and industry != '':
                        policy_level = '中性'
                        for level, keywords in policy_keywords.items():
                            for kw in keywords:
                                if kw in industry:
                                    policy_level = level
                                    break
                            if policy_level != '中性':
                                break
                        return {
                            'industry': industry,
                            'policy_support': policy_level,
                            'is_connect_stock': True
                        }
        except:
            pass

        return {
            'industry': '未知',
            'policy_support': '中性',
            'is_connect_stock': False
        }

    def get_sector_money_flow(self):
        """
        获取行业板块资金流向
        返回: [{'name': '板块名', 'money_flow': 净流入额, 'change': 涨跌幅}]
        """
        try:
            # 东方财富板块资金流向
            url = "http://push2.eastmoney.com/api/qt/clist/get"
            params = {
                'pn': 1,
                'pz': 20,
                'po': 1,
                'np': 1,
                'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
                'fltt': 2,
                'invt': 2,
                'fid': 'f62',
                'fs': 'm:90 t:2 f:!50',  # 行业板块
                'fields': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21,f62',
            }

            resp = requests.get(url, params=params, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('data') and data['data'].get('diff'):
                    sectors = []
                    for item in data['data']['diff'][:15]:  # 取前15个
                        sectors.append({
                            'name': item.get('f14', ''),
                            'money_flow': float(item.get('f62', 0) or 0) / 10000,  # 转为亿
                            'change': float(item.get('f3', 0) or 0),
                        })
                    return sectors
            return []
        except Exception as e:
            return []

    def get_hot_sectors(self):
        """获取热门板块（涨幅前列）"""
        try:
            url = "http://push2.eastmoney.com/api/qt/clist/get"
            params = {
                'pn': 1,
                'pz': 30,
                'po': 1,
                'np': 1,
                'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',  # 按涨幅排序
                'fs': 'm:90 t:2 f:!50',
                'fields': 'f1,f2,f3,f4,f12,f14',
            }

            resp = requests.get(url, params=params, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('data') and data['data'].get('diff'):
                    hot_sectors = []
                    for item in data['data']['diff'][:10]:
                        change = float(item.get('f3', 0) or 0)
                        if change > 0:  # 只取上涨板块
                            hot_sectors.append({
                                'name': item.get('f14', ''),
                                'change': change,
                            })
                    return hot_sectors
            return []
        except Exception as e:
            return []

    def get_policy_highlights(self):
        """
        获取近期政策重点方向
        基于当前时间节点返回相关政策热点
        """
        now = datetime.now()
        month = now.month

        # 2026年政策热点（根据当前时间更新）
        policy_2026 = {
            'AI科技': ['人工智能', 'DeepSeek', '大模型', '算力基础设施', '机器人'],
            '新能源': ['新能源汽车', '储能', '光伏', '风电', '氢能'],
            '半导体': ['芯片', '半导体设备', '集成电路', '自主可控'],
            '消费升级': ['以旧换新', '消费补贴', '智能家居', '新能源汽车下乡'],
            '新基建': ['5G', '数据中心', '工业互联网', '智能交通'],
        }

        # 根据月份推荐重点关注
        seasonal = {
            '1-2': ['年报业绩', '春节消费', '一号文件(农业)'],
            '3-4': ['两会政策', '春季行情', '新基建', '科技'],
            '5-7': ['618消费', '夏季用电', '新能源'],
            '8-9': ['中报业绩', '苹果产业链', '消费电子'],
            '10-12': ['年末估值切换', '政策预期', '消费旺季'],
        }

        current_season = []
        for period, topics in seasonal.items():
            start, end = map(int, period.split('-'))
            if start <= month <= end:
                current_season = topics
                break

        return {
            'policy_2026': policy_2026,
            'seasonal_focus': current_season,
            'update_time': now.strftime('%Y-%m-%d')
        }

    def analyze_stocks_with_enhancement(self, stocks):
        """
        为股票列表增强数据（北向资金、行业、政策）
        """
        for stock in stocks:
            code = stock.get('code', '')

            # 获取北向资金数据
            north_data = self.get_north_money_data(code)
            stock['north_money_5d'] = north_data.get('north_money_5d', 0)
            stock['north_money_status'] = north_data.get('north_money_status', '未知')

            # 获取行业信息
            industry_data = self.get_industry_info(code)
            stock['industry'] = industry_data.get('industry', '未知')
            stock['policy_support'] = industry_data.get('policy_support', '未知')

            time.sleep(0.1)  # 避免请求过快

        return stocks


def get_sector_analysis_report():
    """
    获取板块分析报告
    """
    enhancer = DataEnhancer()

    # 获取热门板块
    hot_sectors = enhancer.get_hot_sectors()

    # 获取资金流入板块
    money_flow = enhancer.get_sector_money_flow()

    # 获取政策重点
    policy = enhancer.get_policy_highlights()

    return {
        'hot_sectors': hot_sectors,
        'money_flow_sectors': money_flow,
        'policy': policy,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
    }


if __name__ == "__main__":
    # 测试
    enhancer = DataEnhancer()

    # 测试个股
    print("测试个股数据增强:")
    result = enhancer.get_north_money_data("600089")
    print(f"北向资金: {result}")

    result = enhancer.get_industry_info("600089")
    print(f"行业信息: {result}")

    # 测试板块
    print("\n热门板块:")
    hot = enhancer.get_hot_sectors()
    for s in hot[:5]:
        print(f"  {s['name']}: {s['change']:+.2f}%")

    print("\n资金流入板块:")
    flow = enhancer.get_sector_money_flow()
    for s in flow[:5]:
        print(f"  {s['name']}: {s['money_flow']:+.2f}亿")
