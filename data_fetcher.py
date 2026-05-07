# -*- coding: utf-8 -*-
"""
数据获取模块 - 获取股票行情、新闻、每日一言
优化版: 并发请求 + AkShare第三层备用
"""

import requests
import json
import time
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import *

# 设置请求头
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Referer': 'https://www.eastmoney.com/',
}


def get_headers():
    """获取随机化的请求头"""
    headers = HEADERS.copy()
    headers['User-Agent'] = random.choice([
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ])
    return headers


class StockDataFetcher:
    """股票数据获取器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_headers())
        # 禁用系统代理（避免127.0.0.1:8892代理不可用导致请求失败）
        self.session.trust_env = False
        self.session.proxies = {'http': None, 'https': None}

    def fetch_all_stocks(self):
        """
        获取全市场股票列表（排除688）
        三层降级: 东方财富 → 新浪财经 → AkShare
        """
        print("📡 正在获取全市场股票数据...")

        stocks = []
        source = None

        # 第一层：东方财富（并发分页）
        try:
            stocks = self._fetch_eastmoney_all()
            if stocks:
                source = '东方财富'
        except Exception as e:
            print(f"⚠️ 东方财富接口失败: {e}")

        # 第二层：新浪财经
        if not stocks:
            try:
                stocks = self._fetch_sina_stocks()
                if stocks:
                    source = '新浪财经'
            except Exception as e:
                print(f"⚠️ 新浪接口失败: {e}")

        # 第三层：AkShare（首次导入，慢但可靠）
        if not stocks:
            stocks = self._fetch_akshare_all()
            if stocks:
                source = 'AkShare'

        print(f"✅ 共获取 {len(stocks)} 只股票 (来源: {source or '无数据'})")
        return stocks

    def _fetch_akshare_all(self):
        """使用AkShare作为第三层备用数据源"""
        import warnings
        warnings.filterwarnings('ignore')
        stocks = []
        try:
            import akshare as ak
            print("   🔄 启用AkShare第三层备用...")
            # 使用 AkShare 的东财全市场接口封装
            try:
                df_em = ak.stock_zh_a_spot_em()
                if df_em is not None and not df_em.empty:
                    for _, row in df_em.iterrows():
                        code = str(row.get('代码', ''))
                        if code.startswith('688') or code.startswith('8'):
                            continue
                        stocks.append({
                            'code': code,
                            'name': row.get('名称', ''),
                            'price': float(row.get('最新价', 0) or 0),
                            'change_pct': float(row.get('涨跌幅', 0) or 0),
                            'volume': int(row.get('成交量', 0) or 0),
                            'turnover': float(row.get('成交额', 0) or 0),
                            'amplitude': float(row.get('振幅', 0) or 0),
                            'high': float(row.get('最高', 0) or 0),
                            'low': float(row.get('最低', 0) or 0),
                            'open': float(row.get('今开', 0) or 0),
                            'close': float(row.get('昨收', 0) or 0),
                            'turnover_rate': float(row.get('换手率', 0) or 0),
                            'pe': float(row.get('市盈率-动态', 0) or 0),
                            'pb': float(row.get('市净率', 0) or 0),
                            'market_cap': float(row.get('总市值', 0) or 0),
                            'float_cap': float(row.get('流通市值', 0) or 0),
                            'industry': row.get('行业', '') or '',
                        })
                    print(f"   ✅ AkShare获取: {len(stocks)}只")
            except Exception as ak_err:
                print(f"   ⚠️ AkShare东方财富接口失败: {ak_err}")
        except ImportError:
            print("   ⚠️ AkShare未安装，无法使用第三层备用")
        return stocks

    def _fetch_eastmoney_all(self):
        """使用东方财富全市场接口（并发分页优化）"""
        stocks = []
        url = "https://push2.eastmoney.com/api/qt/clist/get"

        fields = "f2,f3,f4,f5,f6,f7,f8,f9,f12,f14,f15,f16,f17,f18,f20,f21,f23,f100"
        base_params = {
            "pz": 100, "po": 1, "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2, "invt": 2, "fid": "f3",
            "fields": fields,
        }

        def _fetch_page(fs, pn):
            """并发抓取单页"""
            params = base_params.copy()
            params['fs'] = fs
            params['pn'] = pn
            try:
                resp = self.session.get(url, params=params, timeout=15)
                resp.encoding = 'utf-8'
                data = resp.json()
                items = []
                if data.get('data') and data['data'].get('diff'):
                    for item in data['data']['diff']:
                        code = str(item.get('f12', ''))
                        if code.startswith('688'):
                            continue
                        items.append({
                            'code': code,
                            'name': item.get('f14', ''),
                            'price': item.get('f2', 0) or 0,
                            'change_pct': item.get('f3', 0) or 0,
                            'volume': item.get('f5', 0) or 0,
                            'turnover': item.get('f6', 0) or 0,
                            'amplitude': item.get('f7', 0) or 0,
                            'high': item.get('f15', 0) or 0,
                            'low': item.get('f16', 0) or 0,
                            'open': item.get('f17', 0) or 0,
                            'close': item.get('f18', 0) or 0,
                            'turnover_rate': item.get('f8', 0) or 0,
                            'pe': item.get('f9', 0) or 0,
                            'pb': item.get('f23', 0) or 0,
                            'market_cap': item.get('f20', 0) or 0,
                            'float_cap': item.get('f21', 0) or 0,
                            'industry': item.get('f100', ''),
                        })
                return items
            except Exception as e:
                print(f"      ⚠️ 第{pn}页失败: {e}")
                return []

        # 获取所有A股（包括沪深）
        for market_desc, fs_param in [
            ("上海A股", "m:1+t:2,m:1+t:23"),
            ("深圳主板", "m:0+t:6,m:0+t:80"),
            ("创业板", "m:0+t:80"),
        ]:
            try:
                # 先获取总数，确定分页数
                params = base_params.copy()
                params['fs'] = fs_param
                params['pn'] = 1
                resp = self.session.get(url, params=params, timeout=15)
                resp.encoding = 'utf-8'
                data = resp.json()

                if not (data.get('data') and data['data'].get('diff')):
                    print(f"   ⚠️ {market_desc}接口返回异常，跳过")
                    continue

                total = data['data'].get('total', 0)
                pages = (total + 99) // 100 if total > 0 else 1

                # 解析第一页数据（已获取）
                page_stocks = []
                for item in data['data']['diff']:
                    code = str(item.get('f12', ''))
                    if code.startswith('688'):
                        continue
                    page_stocks.append({
                        'code': code,
                        'name': item.get('f14', ''),
                        'price': item.get('f2', 0) or 0,
                        'change_pct': item.get('f3', 0) or 0,
                        'volume': item.get('f5', 0) or 0,
                        'turnover': item.get('f6', 0) or 0,
                        'amplitude': item.get('f7', 0) or 0,
                        'high': item.get('f15', 0) or 0,
                        'low': item.get('f16', 0) or 0,
                        'open': item.get('f17', 0) or 0,
                        'close': item.get('f18', 0) or 0,
                        'turnover_rate': item.get('f8', 0) or 0,
                        'pe': item.get('f9', 0) or 0,
                        'pb': item.get('f23', 0) or 0,
                        'market_cap': item.get('f20', 0) or 0,
                        'float_cap': item.get('f21', 0) or 0,
                        'industry': item.get('f100', ''),
                    })
                stocks.extend(page_stocks)

                # 从第2页开始并发（最多10个线程）
                if pages > 1:
                    remaining = list(range(2, pages + 1))
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        futures = {executor.submit(_fetch_page, fs_param, pn): pn for pn in remaining}
                        for future in as_completed(futures):
                            stocks.extend(future.result())
                            time.sleep(0.05)  # 礼貌延迟，避免被限流

                print(f"   ✅ 获取{market_desc}: {len(page_stocks) + (pages-1)*100}只(共{total}只)")

            except Exception as e:
                print(f"   ⚠️ 获取{market_desc}失败: {e}")

        return stocks

    def _fetch_sina_stocks(self):
        """使用新浪财经接口获取股票列表"""
        stocks = []

        # 新浪股票列表接口
        url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"

        for page in range(1, 10):  # 最多9页
            params = {
                "page": str(page),
                "num": "80",
                "sort": "symbol",
                "asc": "1",
                "node": "hs_a",  #沪深A股
                "symbol": "",
                "_s_r_a": "page"
            }

            try:
                resp = self.session.get(url, params=params, timeout=10)
                resp.encoding = 'gbk'

                # 解析为字典列表
                text = resp.text
                if text.startswith('var'):
                    text = text[text.index('=') + 1:].strip()

                data = json.loads(text)

                if not data:
                    break

                for item in data:
                    code = str(item.get('symbol', '')).replace('sh', '').replace('sz', '')

                    # 过滤688开头
                    if code.startswith('688'):
                        continue

                    stocks.append({
                        'code': code,
                        'name': item.get('name', ''),
                        'price': float(item.get('trade', 0) or 0),
                        'change_pct': float(item.get('pricechange', 0) or 0),
                        'volume': int(item.get('volume', 0) or 0),
                        'turnover': float(item.get('amount', 0) or 0),
                        'amplitude': float(item.get('amplitude', 0) or 0),
                        'high': float(item.get('high', 0) or 0),
                        'low': float(item.get('low', 0) or 0),
                        'open': float(item.get('open', 0) or 0),
                        'close': float(item.get('settlement', 0) or 0),
                        'turnover_rate': float(item.get('turnoverratio', 0) or 0),
                        'pe': float(item.get('perationprice', 0) or 0),
                        'pb': float(item.get('pb', 0) or 0),
                        'market_cap': float(item.get('mktcap', 0) or 0),
                        'float_cap': float(item.get('nmc', 0) or 0),
                    })

                if len(data) < 80:
                    break

            except Exception as e:
                print(f"   ⚠️ 获取第{page}页失败: {e}")
                break

            time.sleep(0.3)

        return stocks

    def fetch_realtime_quote(self, codes):
        """
        获取实时行情（单个或少量股票）
        参考: go-stock 实时行情获取
        """
        if not codes:
            return []

        quotes = []
        # 分批获取，每批最多50个
        batch_size = 50

        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            symbols = ','.join([f'{"sh" if c.startswith(("6", "5")) else "sz"}{c}' for c in batch])

            try:
                url = f"https://hq.sinajs.cn/list={symbols}"
                resp = self.session.get(url, timeout=10)
                resp.encoding = 'gbk'

                lines = resp.text.strip().split('\n')
                for line in lines:
                    if '=' not in line:
                        continue

                    content = line.split('=')[1].strip('";\n\r ')
                    if not content:
                        continue

                    parts = content.split(',')
                    if len(parts) >= 32:
                        code = line.split('=')[0].split('_')[-1]
                        quotes.append({
                            'code': code[2:] if code.startswith(('sh', 'sz')) else code,
                            'name': parts[0],
                            'open': float(parts[1]) if parts[1] else 0,
                            'close': float(parts[2]) if parts[2] else 0,
                            'price': float(parts[3]) if parts[3] else 0,
                            'high': float(parts[4]) if parts[4] else 0,
                            'low': float(parts[5]) if parts[5] else 0,
                            'volume': int(parts[8]) if parts[8] else 0,  # 成交量(手)
                            'turnover': float(parts[9]) if parts[9] else 0,  # 成交额
                            'time': f"{parts[30]} {parts[31]}" if len(parts) > 31 else "",
                        })

            except Exception as e:
                print(f"  ⚠️ 获取实时行情失败: {e}")

            time.sleep(0.05)  # 减少延迟加快获取

    def calculate_indicators(self, stock):
        """
        计算技术指标
        参考: myhhub/stock 技术指标计算
        """
        indicators = {}

        try:
            price = float(stock.get('price', 0))
            close = float(stock.get('close', 0)) or price
            high = float(stock.get('high', 0))
            low = float(stock.get('low', 0))
            volume = float(stock.get('volume', 0))

            # 量比
            indicators['volume_ratio'] = volume / 100  # 简化计算

            # 涨幅
            if close > 0:
                indicators['change_pct'] = ((price - close) / close) * 100
            else:
                indicators['change_pct'] = 0

            # 振幅
            if close > 0:
                indicators['amplitude'] = ((high - low) / close) * 100
            else:
                indicators['amplitude'] = 0

            # 上涨动力指数（简化版）
            indicators['momentum'] = indicators['change_pct'] * (volume / 1000000) if volume else 0

            # 位置评分（价格在日内区间的位置）
            if high > low:
                position = (price - low) / (high - low) * 100
                indicators['position_score'] = position
            else:
                indicators['position_score'] = 50

        except Exception as e:
            print(f"  ⚠️ 计算指标失败: {e}")

        return indicators


class NewsFetcher:
    """财经新闻获取器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_headers())
        # 禁用系统代理
        self.session.trust_env = False
        self.session.proxies = {'http': None, 'https': None}

        # 保留的关键词（股票、油价、黄金白银等财经资讯）
        # 注意：期货已移至 exclude_keywords，如需单独展示期货资讯可调整
        self.include_keywords = [
            '股票', 'A股', '沪指', '深指', '创业板', '科创板', '大盘', '指数', '上证', '深证',
            '油价', '原油', '石油', '黄金', '白银', '贵金属', '大宗商品',
            '股市', '涨停', '跌停', '牛市', '熊市', '利好', '利空', '分红', '业绩', '年报', '季报',
            '央行', '货币政策', '降息', '加息', '利率', '美联储', '美股', '港股',
            '北向', '外资', '北上资金', '南下资金', '主力资金', '游资', '机构',
            '房地产', '楼市', '房价', '券商', '基金', 'ETF', 'ETF基金',
            '茅台', '宁德', '比亚迪', '锂电池', '光伏', '半导体', '芯片', 'AI', '人工智能',
            '人民币', '美元', '汇率', '外汇', '美债', '国债', '债券', '转债',
            'IPO', '上市', '新股', '打新', '退市', 'ST股',
        ]

        # 需要排除的关键词（国外打仗、谈判等不相关内容；期货资讯）
        self.exclude_keywords = [
            '战争', '打仗', '冲突', '军事', '武器', '导弹', '坦克', '士兵', '伤亡',
            '制裁', '谈判', '停火', '和谈', '协议', '外交', '峰会', 'G20', 'G7',
            '美国', '欧洲', '俄罗斯', '乌克兰', '中东', '以色列', '伊朗', '朝鲜',
            '特朗普', '拜登', '泽连斯基', '普京', '内塔尼亚胡', '大选', '竞选',
            '疫情', '病毒', '疫苗', '猴痘',
            '期货',  # 排除期货相关资讯（期货品种走势与A股股票关联度低）
        ]

    def _is_valid_news(self, title):
        """判断新闻是否符合条件"""
        title_lower = title.lower()

        # 排除包含敏感关键词的新闻
        for keyword in self.exclude_keywords:
            if keyword in title:
                return False

        # 检查是否包含保留关键词
        for keyword in self.include_keywords:
            if keyword in title:
                return True

        return False

    def _get_news_with_filter(self, title):
        """过滤并分类新闻"""
        title_lower = title.lower()

        # 分类标签
        if any(kw in title for kw in ['黄金', '白银', '贵金属', '原油', '油价', '石油']):
            return '大宗商品'
        elif any(kw in title for kw in ['沪指', '深指', '上证', '深证', '创业板', '科创板', '大盘', '指数']):
            return '大盘指数'
        elif any(kw in title for kw in ['涨停', '跌停', '牛', '熊市']):
            return '市场情绪'
        elif any(kw in title for kw in ['央行', '降息', '加息', '利率', '美联储', '美股']):
            return '宏观政策'
        elif any(kw in title for kw in ['北向', '外资', '主力资金']):
            return '资金面'
        elif any(kw in title for kw in ['业绩', '年报', '季报', '分红']):
            return '公司业绩'
        else:
            return '市场资讯'

    def fetch_market_news(self):
        """
        获取市场情绪数据（并发优化 + AkShare第三层）
        过滤后保留股票、油价、黄金白银等财经资讯
        """
        print("📰 正在获取市场新闻（并发模式）...")

        news_items = []

        def _fetch_em_news():
            """东方财富快讯"""
            items = []
            try:
                url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
                params = {
                    "sr": "-1", "page_size": 50, "page_index": 1,
                    "ann_type": "ALL,SH,SHNET,SHSTAR,SZ,SZCN,SZCY,SZSB,BJ",
                    "client_source": "web",
                }
                resp = self.session.get(url, params=params, timeout=15)
                data = resp.json()
                if data.get('data'):
                    for item in data['data']['list']:
                        title = item.get('title', '')
                        if self._is_valid_news(title):
                            items.append({
                                'title': title,
                                'time': item.get('notice_date', ''),
                                'source': '东方财富',
                                'url': f"https://data.eastmoney.com/notices/detail/{item.get('art_code', '')}.html",
                                'category': self._get_news_with_filter(title),
                            })
                print(f"   ✅ 东方财富新闻: {len(items)}条")
            except Exception as e:
                print(f"   ⚠️ 东方财富新闻失败: {e}")
            return items

        def _fetch_sina_news():
            """新浪财经快讯"""
            items = []
            try:
                url = "https://feed.mix.sina.com.cn/api/roll/get"
                params = {
                    "pageid": 153, "lid": 2516, "k": "", "num": 20, "page": 1, "r": 0.5,
                }
                resp = self.session.get(url, params=params, timeout=10)
                data = resp.json()
                if data.get('result'):
                    for item in data['result'].get('data', []):
                        title = item.get('title', '')
                        if self._is_valid_news(title):
                            items.append({
                                'title': title,
                                'time': item.get('ctime', ''),
                                'source': '新浪财经',
                                'url': item.get('url', ''),
                                'category': self._get_news_with_filter(title),
                            })
                print(f"   ✅ 新浪财经新闻: {len(items)}条")
            except Exception as e:
                print(f"   ⚠️ 新浪财经新闻失败: {e}")
            return items

        def _fetch_yicai_news():
            """同花顺快讯（替换已失效的第一财经API）"""
            items = []
            try:
                # 同花顺快讯接口
                url = "https://news.10jqka.com.cn/tapp/news/push/stock/"
                params = {
                    "page": 1,
                    "tag": "",
                    "track": "website",
                    "pageSize": 20,
                }
                resp = self.session.get(url, params=params, timeout=10)
                resp.encoding = 'utf-8'
                data = resp.json()
                if data.get('data'):
                    for item in data['data'].get('list', []):
                        title = item.get('title', '')
                        if self._is_valid_news(title):
                            items.append({
                                'title': title,
                                'time': item.get('time', ''),
                                'source': '同花顺',
                                'url': item.get('url', '') or '',
                                'category': self._get_news_with_filter(title),
                            })
                print(f"   ✅ 同花顺快讯: {len(items)}条")
            except Exception as e:
                print(f"   ⚠️ 同花顺快讯失败: {e}")
            return items

        # 并发获取4个来源
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(_fetch_em_news),
                executor.submit(_fetch_sina_news),
                executor.submit(_fetch_yicai_news),
                executor.submit(self._fetch_jin10_news),
            ]
            for future in as_completed(futures):
                news_items.extend(future.result())

        # 去重
        seen = set()
        unique_news = []
        for news in news_items:
            if news['title'] not in seen:
                seen.add(news['title'])
                unique_news.append(news)

        print(f"✅ 获取到 {len(unique_news)} 条财经新闻（已过滤）")
        return unique_news[:10]

    def _fetch_jin10_news(self):
        """
        获取金十数据快讯
        接口: https://flash-api.jin10.com/get_flash_list
        注意：使用独立的 requests.get 而非 self.session，避免会话复用导致的header冲突
        """
        news_items = []
        max_retries = 2

        # 金十数据API配置
        jin10_headers = {
            'accept': 'application/json, text/plain, */*',
            'x-app-id': 'bVBF4FyRTn5NJF5n',
            'x-version': '1.0.0',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.jin10.com/',
        }

        for attempt in range(max_retries):
            try:
                url = "https://flash-api.jin10.com/get_flash_list"
                params = {
                    'channel': '-8200',
                    'vip': '1'
                }

                # 使用独立请求而非 session，避免会话header污染
                resp = requests.get(url, params=params, headers=jin10_headers, timeout=10, verify=False)
                data = resp.json()

                if data.get('status') == 200 and data.get('data'):
                    for item in data['data']:
                        time_str = item.get('time', '')
                        content = item.get('data', {}).get('content', '')
                        source = item.get('data', {}).get('source', '') or '金十数据'

                        # 跳过内容为空或太短的
                        if not content or len(content) < 10:
                            continue

                        # 应用关键词过滤
                        if not self._is_valid_news(content):
                            continue

                        # 获取分类标签
                        category = self._get_news_with_filter(content)

                        news_items.append({
                            'title': content[:100] + '...' if len(content) > 100 else content,
                            'time': time_str,
                            'source': source,
                            'url': '',
                            'category': category,
                        })

                        # 最多获取10条
                        if len(news_items) >= 10:
                            break

                    print(f"✅ 获取金十数据 {len(news_items)} 条")
                    break
                elif data.get('status') == 401 or data.get('status') == 403:
                    print(f"  ⚠️ 金十API认证失败（状态码:{data.get('status')}），可能需要更新AppId")

            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                print(f"  ⚠️ 金十API获取失败: {e}")

        return news_items


class DailyQuoteFetcher:
    """每日一言获取器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_headers())
        # 禁用系统代理
        self.session.trust_env = False
        self.session.proxies = {'http': None, 'https': None}

    def fetch_quote(self):
        """获取每日一言（从Hitokoto API随机获取）"""
        # Hitokoto API - 一言开源项目
        HITOKOTO_API = "https://v1.hitokoto.cn/?c=d&c=i&c=k&encode=json"
        
        # 备用写死的语录库
        fallback_quotes = [
            "别人贪婪时恐惧，别人恐惧时贪婪。 —— 巴菲特",
            "投资的第一原则是永远不要亏钱，第二原则是记住第一原则。 —— 巴菲特",
            "模糊的正确胜过精确的错误。 —— 巴菲特",
            "赚大钱的诀窍不在于买进卖出，而在于等待。 —— 利弗莫尔",
            "反过来想，永远要反过来想。 —— 查理·芒格",
            "止损永远是对的，套牢永远是错的。 —— 交易铁律",
            "计划你的交易，交易你的计划。 —— 交易箴言",
            "让利润奔跑，把亏损截断。 —— 趋势交易法则",
        ]

        try:
            resp = self.session.get(HITOKOTO_API, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                hitokoto = data.get('hitokoto', '')
                from_who = data.get('from_who', '')
                from_source = data.get('from', '')
                
                # 组合语录
                if hitokoto:
                    if from_who:
                        return f"{hitokoto} —— {from_who}"
                    elif from_source:
                        return f"{hitokoto} —— {from_source}"
                    else:
                        return hitokoto
        except Exception as e:
            print(f"   Hitokoto API失败: {e}")
        
        # API失败时返回随机备用语录
        import random
        return random.choice(fallback_quotes)


class MoneyFlowFetcher:
    """资金流向获取器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_headers())
        # 禁用系统代理
        self.session.trust_env = False
        self.session.proxies = {'http': None, 'https': None}
    
    def get_sector_money_flow(self, min_days=5, max_change=15):
        """
        获取板块连续净流入数据
        返回: 板块列表（名称、近5天流入、近20天流入）
        """
        print("\n💰 正在获取板块资金流向...")
        
        sectors = []
        
        try:
            # 东方财富板块资金流向接口
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": 1,
                "pz": 100,
                "po": 1,
                "np": 1,
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": 2,
                "invt": 2,
                "fid": "f62",  # 主力净流入排序
                "fs": "m:90+t:2+f:!50",  # 行业板块
                "fields": "f12,f14,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f124,f128,f136,f140",
            }
            
            resp = self.session.get(url, params=params, timeout=15)
            data = resp.json()
            
            if data.get('data') and data['data'].get('diff'):
                for item in data['data']['diff']:
                    name = item.get('f14', '')
                    # 近5日主力净流入(万元)
                    inflow_5d = item.get('f62', 0) or 0
                    # 近5日涨幅
                    change_5d = item.get('f140', 0) or 0
                    
                    if inflow_5d > 0 and abs(change_5d) <= max_change:  # 净流入且涨幅不超15%
                        sectors.append({
                            'name': name,
                            'inflow_5d': inflow_5d,  # 万元
                            'inflow_5d_str': self._format_amount(inflow_5d * 10000),  # 转换为元
                            'change_5d': change_5d,
                        })
            
            # 按5日净流入排序
            sectors.sort(key=lambda x: x['inflow_5d'], reverse=True)
            
            print(f"✅ 获取到 {len(sectors)} 个净流入板块")
            
        except Exception as e:
            print(f"⚠️ 获取板块资金流向失败: {e}")
        
        return sectors[:15]  # 最多返回15个板块
    
    def _format_amount(self, amount):
        """格式化金额"""
        if abs(amount) >= 100000000:  # 亿
            return f"{amount/100000000:.2f}亿"
        elif abs(amount) >= 10000:  # 万
            return f"{amount/10000:.2f}万"
        else:
            return f"{amount:.0f}元"

    def get_stock_money_flow(self, code):
        """
        获取个股资金流向（近5日）
        返回: 每日净流入金额列表
        """
        try:
            # 判断市场
            if code.startswith(('6', '5')):
                market = 'sh'
            else:
                market = 'sz'

            # 东方财富资金流向接口
            url = "https://push2his.eastmoney.com/api/qt/stock/fflow/kline/get"
            params = {
                "lmt": 0,
                "klt": 101,  # 日K
                "secid": f"1.{code}" if market == 'sh' else f"0.{code}",
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
                "ut": "b2884a393a59ad64002292a3e90d46a5",
            }

            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()

            if data.get('data') and data['data'].get('klines'):
                klines = data['data']['klines']
                flow_data = []
                for line in klines[-7:]:  # 取最近7天
                    parts = line.split(',')
                    if len(parts) >= 6:
                        flow_data.append({
                            'date': parts[0],
                            'main_net': float(parts[1]) if parts[1] else 0,  # 主力净流入
                            'super_net': float(parts[2]) if parts[2] else 0,  # 超大单净流入
                            'big_net': float(parts[3]) if parts[3] else 0,  # 大单净流入
                            'mid_net': float(parts[4]) if parts[4] else 0,  # 中单净流入
                            'small_net': float(parts[5]) if parts[5] else 0,  # 小单净流入
                        })
                return flow_data
        except Exception as e:
            pass

        return []

    def get_continuous_inflow_stocks(self, stocks, min_days=5, min_ratio=0.6, max_change=15):
        """
        筛选连续净流入股票
        参数:
            stocks: 股票列表
            min_days: 最少连续净流入天数（默认5天）
            min_ratio: 7天内净流入天数比例（默认0.6，即60%）
            max_change: 最大累计涨幅（默认15%）
        返回: 连续净流入股票列表
        """
        print(f"\n💰 正在筛选连续净流入股票...")

        inflow_stocks = []
        checked = 0

        for stock in stocks:
            code = stock.get('code', '')
            name = stock.get('name', '')

            # 排除688和北交所
            if code.startswith('688') or code.startswith('8'):
                continue

            checked += 1
            if checked % 100 == 0:
                print(f"   已检查 {checked} 只股票...")

            # 获取资金流向
            flow_data = self.get_stock_money_flow(code)
            if not flow_data or len(flow_data) < 5:
                time.sleep(0.1)
                continue

            # 计算净流入天数
            net_inflow_days = 0
            total_net_inflow = 0
            for day in flow_data:
                net = day['main_net']  # 使用主力净流入
                if net > 0:  # 净流入
                    net_inflow_days += 1
                    total_net_inflow += net

            # 判断是否符合条件
            total_days = len(flow_data)
            inflow_ratio = net_inflow_days / total_days if total_days > 0 else 0

            # 涨幅限制（从stock获取）
            change_pct = abs(stock.get('change_pct', 0))

            # 条件判断：连续5天 或 7天有60%以上净流入
            if (net_inflow_days >= min_days or inflow_ratio >= min_ratio) and change_pct <= max_change:
                inflow_stocks.append({
                    'code': code,
                    'name': name,
                    'price': stock.get('price', 0),
                    'change_pct': stock.get('change_pct', 0),
                    'net_inflow_days': net_inflow_days,
                    'total_days': total_days,
                    'total_net_inflow': total_net_inflow,  # 单位：元
                    'inflow_ratio': inflow_ratio,
                })

            time.sleep(0.03)  # 减少延迟加快获取

        # 按净流入天数和金额排序
        inflow_stocks.sort(key=lambda x: (x['net_inflow_days'], x['total_net_inflow']), reverse=True)

        print(f"✅ 筛选完成，找到 {len(inflow_stocks)} 只连续净流入股票")
        return inflow_stocks[:20]  # 最多返回20只


# 单元测试
if __name__ == "__main__":
    print("=" * 60)
    print("数据获取模块测试")
    print("=" * 60)

    # 测试股票数据
    fetcher = StockDataFetcher()
    stocks = fetcher.fetch_all_stocks()
    print(f"\n获取到 {len(stocks)} 只股票")

    if stocks:
        print("\n示例股票:")
        for s in stocks[:3]:
            print(f"  {s['code']} {s['name']} 价格:{s['price']} 涨幅:{s['change_pct']}%")

    # 测试新闻
    news_fetcher = NewsFetcher()
    news = news_fetcher.fetch_market_news()
    print(f"\n获取到 {len(news)} 条新闻")

    # 测试每日一言
    quote_fetcher = DailyQuoteFetcher()
    quote = quote_fetcher.fetch_quote()
    print(f"\n每日一言: {quote}")

    # 测试打新日历
    print("\n" + "="*50)
    ipo_fetcher = IPOFetcher()
    ipo_data = ipo_fetcher.fetch_ipo_calendar()
    print(f"\n获取到 {len(ipo_data.get('stocks', []))} 只新股")
    print(f"获取到 {len(ipo_data.get('bonds', []))} 只可转债")


class IPOFetcher:
    """打新日历获取器 - 包含新股申购和可转债"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_headers())
        # 禁用系统代理
        self.session.trust_env = False
        self.session.proxies = {'http': None, 'https': None}
        self._akshare_available = False
        self._try_import_akshare()

    def _try_import_akshare(self):
        """尝试导入AkShare"""
        try:
            import akshare as ak
            self.ak = ak
            self._akshare_available = True
        except ImportError:
            print("  ⚠️ AkShare未安装，将使用备用接口")
            self._akshare_available = False

    def fetch_ipo_calendar(self):
        """
        获取打新日历（新股申购 + 可转债）
        数据来源：同花顺(AkShare) + 东方财富
        """
        result = {
            'stocks': [],   # 新股
            'bonds': []     # 可转债
        }

        # 1. 获取新股申购日历
        result['stocks'] = self._fetch_new_stocks()

        # 2. 获取可转债申购日历
        result['bonds'] = self._fetch_convertible_bonds()

        return result

    def _fetch_new_stocks(self):
        """获取新股申购数据（只获取今天及之后的）"""
        import warnings
        warnings.filterwarnings('ignore')

        stocks = []
        today = datetime.now()
        today_str = today.strftime('%Y-%m-%d')
        today_short = today.strftime('%m-%d')  # 04-09格式

        def parse_date(date_str):
            """解析日期字符串，返回datetime对象"""
            if not date_str or date_str == '-' or '摇号' in date_str:
                return None
            try:
                # 处理 04-14 周二 格式
                if ' 周' in date_str:
                    date_part = date_str.split(' 周')[0]
                    year = datetime.now().year
                    return datetime.strptime(f"{year}-{date_part}", '%Y-%m-%d')
                # 处理 2026-04-08 格式
                elif '-' in date_str and len(date_str) >= 10:
                    return datetime.strptime(date_str[:10], '%Y-%m-%d')
                else:
                    return None
            except:
                return None

        try:
            if self._akshare_available:
                # 使用AkShare同花顺接口
                df = self.ak.stock_ipo_ths()
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        apply_date = str(row.get('申购日期', ''))
                        parsed = parse_date(apply_date)

                        # 只保留今天及之后
                        if parsed and parsed >= today:
                            price = row.get('发行价格', '-')
                            stocks.append({
                                'name': row.get('股票简称', ''),
                                'code': row.get('股票代码', ''),
                                '申购代码': row.get('申购代码', ''),
                                '发行价': f"{float(price):.2f}" if price != '-' and price else '-',
                                '申购上限': f"{row.get('顶格申购需配市值（万元）', '-')}万" if row.get('顶格申购需配市值（万元）', '-') != '-' else '-',
                                '申购日期': apply_date,
                                '上市日期': str(row.get('上市日期', '-')),
                                '发行PE': str(row.get('发行市盈率', '-')),
                                '中签率': str(row.get('中签率（%）', '-')),
                            })
                            if len(stocks) >= 10:
                                break
            else:
                # 备用：东方财富接口（可能已失效）
                stocks = self._fetch_new_stocks_em()

        except Exception as e:
            print(f"  ⚠️ 获取新股数据失败: {e}")

        return stocks

    def _fetch_new_stocks_em(self):
        """东方财富备用接口"""
        stocks = []
        today = datetime.now().strftime('%Y-%m-%d')

        try:
            url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
            params = {
                "sortColumns": "PUBLIC_START_DATE",
                "sortTypes": "1",
                "pageSize": 20,
                "pageNumber": 1,
                "reportName": "RPT_APPOINTMENT_LIST",
                "columns": "ALL",
                "type": "RPT_APPOINTMENT_LIST",
            }
            resp = self.session.get(url, params=params, timeout=15)
            data = resp.json()

            if data.get('result') and data['result'].get('data'):
                for item in data['result']['data']:
                    apply_date = item.get('PUBLIC_START_DATE', '')
                    if apply_date and apply_date >= today:
                        stocks.append({
                            'name': item.get('SECURITY_NAME_ABBR', ''),
                            'code': item.get('SECURITY_CODE', ''),
                            '申购代码': item.get('APPOINT_CODE', ''),
                            '发行价': f"{item.get('OFFER_PRICE', 0):.2f}" if item.get('OFFER_PRICE') else '-',
                            '申购上限': f"{item.get('UPSTAKE_LIMIT', 0):.2f}万" if item.get('UPSTAKE_LIMIT') else '-',
                            '申购日期': apply_date,
                            '上市日期': item.get('LISTING_DATE', ''),
                            '发行PE': item.get('ISSUE_PE', '-'),
                            '中签率': item.get('DRAWAL_RATE', '-'),
                        })
                        if len(stocks) >= 10:
                            break

        except Exception as e:
            print(f"  ⚠️ 东方财富新股接口失败: {e}")

        return stocks

    def _fetch_convertible_bonds(self):
        """获取可转债申购数据（只获取今天及之后的）"""
        import warnings
        warnings.filterwarnings('ignore')

        bonds = []
        today = datetime.now().strftime('%Y-%m-%d')

        try:
            if self._akshare_available:
                # 使用AkShare同花顺接口
                df = self.ak.bond_zh_cov_info_ths()
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        apply_date = str(row.get('申购日期', ''))
                        # 只保留今天及之后
                        if apply_date and apply_date != '-' and apply_date != 'NaT':
                            try:
                                # 转换为datetime比较
                                apply_dt = datetime.strptime(apply_date, '%Y-%m-%d')
                                today_dt = datetime.strptime(today, '%Y-%m-%d')
                                if apply_dt >= today_dt:
                                    bonds.append({
                                        'name': row.get('债券简称', ''),
                                        'code': row.get('债券代码', ''),
                                        '正股': row.get('正股简称', ''),
                                        '正股代码': row.get('正股代码', ''),
                                        '申购日期': apply_date,
                                        '上市日期': str(row.get('上市日期', '-')),
                                        '中签率': str(row.get('中签率', '-')),
                                    })
                                    if len(bonds) >= 10:
                                        break
                            except:
                                pass
            else:
                # 备用东方财富接口
                bonds = self._fetch_convertible_bonds_em()

        except Exception as e:
            print(f"  ⚠️ 获取可转债数据失败: {e}")

        return bonds

    def _fetch_convertible_bonds_em(self):
        """东方财富可转债备用接口"""
        bonds = []
        today = datetime.now().strftime('%Y-%m-%d')

        try:
            url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
            params = {
                "sortColumns": "PUBLIC_START_DATE",
                "sortTypes": "1",
                "pageSize": 20,
                "pageNumber": 1,
                "reportName": "RPT_BOND_CB_LIST",
                "columns": "ALL",
                "type": "RPT_BOND_CB_LIST",
            }
            resp = self.session.get(url, params=params, timeout=15)
            data = resp.json()

            if data.get('result') and data['result'].get('data'):
                for item in data['result']['data']:
                    apply_date = item.get('PUBLIC_START_DATE', '')
                    if apply_date and apply_date >= today:
                        bonds.append({
                            'name': item.get('SECURITY_NAME_ABBR', ''),
                            'code': item.get('BOND_CODE', ''),
                            '正股': item.get('STOCK_NAME_ABBR', ''),
                            '正股代码': item.get('STOCK_CODE', ''),
                            '申购日期': apply_date,
                            '上市日期': item.get('LISTING_DATE', ''),
                            '中签率': item.get('DRAWAL_RATE', '-'),
                        })
                        if len(bonds) >= 10:
                            break

        except Exception as e:
            print(f"  ⚠️ 东方财富可转债接口失败: {e}")

        return bonds


class MultiSourceStockFetcher:
    """多数据源股票获取器 - 整合腾讯、同花顺、雪球数据"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_headers())
        # 禁用系统代理
        self.session.trust_env = False
        self.session.proxies = {'http': None, 'https': None}

    def fetch_from_tencent(self, codes):
        """从腾讯行情获取数据"""
        stocks = []

        try:
            # 腾讯行情接口
            symbols = ','.join([f'{"sh" if c.startswith(("6", "5")) else "sz"}{c}' for c in codes])
            url = f"https://qt.gtimg.cn/q={symbols}"

            resp = self.session.get(url, timeout=10)
            resp.encoding = 'gbk'

            lines = resp.text.strip().split('\n')
            for line in lines:
                if '=' not in line or 'var qt=' in line:
                    continue

                content = line.split('=')[1].strip('";\n\r ')
                if not content:
                    continue

                parts = content.split('~')
                if len(parts) >= 50:
                    code = parts[2] if len(parts) > 2 else ''
                    stocks.append({
                        'code': code,
                        'name': parts[1] if len(parts) > 1 else '',
                        'price': float(parts[3]) if parts[3] else 0,
                        'change_pct': float(parts[32]) if parts[32] else 0,
                        'volume': int(parts[6]) if parts[6] else 0,
                        'source': '腾讯'
                    })

        except Exception as e:
            print(f"  ⚠️ 腾讯行情获取失败: {e}")

        return stocks

    def fetch_from_ths(self, codes):
        """从同花顺获取数据"""
        stocks = []

        try:
            # 同花顺行情接口
            url = "https://d.10jqka.com.cn/v6/line/hs_"

            for code in codes[:100]:  # 限制数量
                try:
                    market = 'sh' if code.startswith(('6', '5')) else 'sz'
                    resp = self.session.get(f"{url}{market}{code}/01/last20.js", timeout=5)
                    resp.encoding = 'utf-8'

                    # 解析返回数据
                    text = resp.text
                    if text and len(text) > 50:
                        stocks.append({
                            'code': code,
                            'source': '同花顺',
                            'data': text[:100]
                        })
                except:
                    pass

                time.sleep(0.05)

        except Exception as e:
            print(f"  ⚠️ 同花顺行情获取失败: {e}")

        return stocks

    def fetch_from_xueqiu(self, codes):
        """从雪球获取数据"""
        stocks = []

        try:
            # 雪球行情接口（需要cookie）
            url = "https://stock.xueqiu.com/v5/stock/realtime/quotec.json"
            symbols = ','.join([f'SH{c}' if c.startswith(('6', '5')) else f'SZ{c}' for c in codes[:50]])

            params = {'symbol': symbols}

            # 雪球需要特殊的cookie
            headers = get_headers()
            headers['Referer'] = 'https://xueqiu.com/'
            headers['Cookie'] = 'xq_a_token=placeholder'  # 简化处理

            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            data = resp.json()

            if data.get('data') and data['data'].get('items'):
                for item in data['data']['items']:
                    quote = item.get('quote', {})
                    stocks.append({
                        'code': quote.get('symbol', '').replace('SH', '').replace('SZ', ''),
                        'name': quote.get('name', ''),
                        'price': quote.get('current', 0),
                        'change_pct': quote.get('percent', 0),
                        'source': '雪球'
                    })

        except Exception as e:
            print(f"  ⚠️ 雪球行情获取失败: {e}")

        return stocks
