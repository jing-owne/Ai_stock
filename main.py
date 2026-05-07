# -*- coding: utf-8 -*-
"""
AI智能选股系统主程序
综合: go-stock, myhhub/stock, zvt, hikyuu, northstar 的选股方法论
"""

import sys
import os
import time
import json
import warnings
warnings.filterwarnings('ignore')

from datetime import datetime
from config import *

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import StockDataFetcher, NewsFetcher, DailyQuoteFetcher, MoneyFlowFetcher, IPOFetcher
from strategy_engine import StrategyEngine, filter_stocks
from ai_analyzer import AIAnalyzer, generate_operation_advice
from mail_sender import MailSender

# 缓存文件路径
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "last_selection_cache.json")


class AISStockSelector:
    """AI智能选股系统"""

    def __init__(self):
        self.name = "AI智能选股"
        self.version = "1.5.0"  # 升级版本
        self.stock_fetcher = StockDataFetcher()
        self.news_fetcher = NewsFetcher()
        self.quote_fetcher = DailyQuoteFetcher()
        self.ai_analyzer = AIAnalyzer()
        self.mail_sender = MailSender()
        self.money_flow_fetcher = MoneyFlowFetcher()  # 资金流向获取器
        self.ipo_fetcher = IPOFetcher()  # 打新日历获取器
        self.strategy_results = {}  # 保存各策略筛选结果
        self.cache_data = {}  # 缓存数据
        self.cached_stocks = []  # 缓存的股票数据

    def run(self, send_email=True):
        """
        运行选股系统
        """
        start_time = datetime.now()
        print("\n" + "=" * 70)
        print(f"🚀 {self.name} v{self.version}")
        print(f"⏰ 运行时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)

        try:
            # 1. 获取每日一言
            daily_quote = self._get_daily_quote()

            # 2. 获取全市场股票数据
            stocks = self._fetch_stock_data()
            # 保存缓存
            self._save_cache(stocks)

            # 3. 获取市场新闻
            news = self._fetch_news()

            # 3.5 获取打新日历
            ipo_data = self._fetch_ipo_calendar()

            # 4. 过滤股票
            filtered_stocks = self._filter_stocks(stocks)

            # 5. 计算技术指标
            enriched_stocks = self._calculate_indicators(filtered_stocks)

            # 6. 运行多策略选股
            strategy_results = self._run_strategies(enriched_stocks)
            self.strategy_results = strategy_results  # 保存策略结果

            # 7. 合并策略结果
            top_stocks = self._merge_strategies(strategy_results, enriched_stocks)

            # 8. 生成操作建议
            stocks_with_advice = self._generate_advice(top_stocks)

            # 9. 获取连续净流入股票
            inflow_stocks = self._get_continuous_inflow_stocks(stocks)

            # 9.5 获取主力净流入字典（快速查询，只查Top50）
            inflow_map = self._get_stock_inflow_map(top_stocks, limit=50)

            # 10. AI分析
            ai_analysis = self._ai_analyze(stocks_with_advice, news)

            # 11. 生成报告（不含板块分析）
            report = self._generate_report(stocks_with_advice, ai_analysis, daily_quote, news, inflow_stocks, ipo_data)

            # 13. 保存策略选股数据到文件
            self._save_strategy_data(strategy_results, top_stocks, inflow_stocks, inflow_map)

            # 14. 发送邮件
            if send_email:
                self._send_report(report)

            # 输出报告
            print(report)

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            print(f"\n✅ 选股完成，耗时: {duration:.1f}秒")

            return stocks_with_advice

        except Exception as e:
            print(f"❌ 系统运行出错: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _get_daily_quote(self):
        """获取每日一言"""
        print("\n📝 获取每日一言...")
        quote = self.quote_fetcher.fetch_quote()
        print(f"   每日一言: {quote[:30]}...")
        return quote

    def _fetch_stock_data(self):
        """获取股票数据"""
        print("\n📡 正在获取股票数据...")
        stocks = self.stock_fetcher.fetch_all_stocks()
        print(f"   共获取 {len(stocks)} 只股票")
        return stocks

    def _fetch_news(self):
        """获取市场新闻"""
        print("\n📰 正在获取市场新闻...")
        news = self.news_fetcher.fetch_market_news()
        return news

    def _fetch_ipo_calendar(self):
        """获取打新日历"""
        print("\n📅 正在获取打新日历...")
        try:
            ipo_data = self.ipo_fetcher.fetch_ipo_calendar()
            stock_count = len(ipo_data.get('stocks', []))
            bond_count = len(ipo_data.get('bonds', []))
            print(f"   ✅ 获取到 {stock_count} 只新股, {bond_count} 只可转债")
            return ipo_data
        except Exception as e:
            print(f"   ⚠️ 获取打新日历失败: {e}")
            return {'stocks': [], 'bonds': []}

    def _filter_stocks(self, stocks):
        """过滤股票"""
        print("\n🔍 正在过滤股票...")
        filtered = filter_stocks(stocks)
        return filtered

    def _calculate_indicators(self, stocks):
        """计算技术指标"""
        print("\n📊 正在计算技术指标...")
        for stock in stocks:
            indicators = self.stock_fetcher.calculate_indicators(stock)
            stock.update(indicators)
        print(f"   计算完成")
        return stocks

    def _run_strategies(self, stocks):
        """运行选股策略"""
        print("\n🧠 正在运行选股策略...")
        engine = StrategyEngine(stocks)
        results = engine.run_all_strategies()
        return results

    def _merge_strategies(self, strategy_results, stocks):
        """合并策略结果"""
        print("\n📊 正在合并策略结果...")
        engine = StrategyEngine(stocks)
        top_stocks = engine.merge_and_rank(strategy_results)
        return top_stocks

    def _generate_advice(self, stocks):
        """生成操作建议"""
        print("\n💡 正在生成操作建议...")
        for stock in stocks:
            advice = generate_operation_advice(stock)
            stock['advice'] = advice
        return stocks

    def _ai_analyze(self, stocks, news):
        """AI分析"""
        print("\n🤖 正在进行AI分析...")
        analysis = self.ai_analyzer.analyze_stocks(stocks, news)
        return analysis

    def _get_continuous_inflow_stocks(self, stocks):
        """获取连续净流入股票"""
        # 调试模式或跳过资金流向查询
        if EMAIL_CONFIG.get('debug_mode', False):
            print("\n💰 [调试模式] 跳过连续净流入股票查询")
            return []
        if EMAIL_CONFIG.get('skip_money_flow', False):
            print("\n💰 [优化模式] 跳过连续净流入股票查询（节省约500秒）")
            return []

        try:
            inflow_stocks = self.money_flow_fetcher.get_continuous_inflow_stocks(
                stocks,
                min_days=5,  # 最少5天连续净流入
                min_ratio=0.6,  # 或7天内60%以上净流入
                max_change=15  # 累计涨幅不超过15%
            )
            return inflow_stocks
        except Exception as e:
            print(f"⚠️ 获取连续净流入股票失败: {e}")
            return []

    def _get_stock_inflow_map(self, stocks, limit=50):
        """获取股票的主力净流入字典（支持持久化）
        
        策略：
        1. 先尝试从API获取数据
        2. 获取成功则写入缓存
        3. 如果API报错/失败，则从缓存读取
        4. 提示缓存的获取时间
        
        Args:
            stocks: 股票列表
            limit: 只查询前N只（节省时间）
        Returns:
            dict: {股票代码: {name, total_net, days, cached_time}}
        """
        today = datetime.now().strftime('%Y%m%d')
        cache_file = os.path.join(CACHE_DIR, f"inflow_cache_{today}.json")
        
        # 调试模式跳过
        if EMAIL_CONFIG.get('debug_mode', False):
            print("\n💰 [调试模式] 跳过主力净流入查询")
            return {}
        
        inflow_map = {}
        api_success = False
        from_cache = False
        cache_time = None
        
        # 1. 先尝试从API获取数据
        print(f"\n💰 正在获取主力净流入数据...")
        try:
            # 只查询有涨幅的股票（减少查询量）
            stocks_to_check = [s for s in stocks if 0 <= s.get('change_pct', 0) <= 9.9][:limit]
            print(f"   需要获取: {len(stocks_to_check)}只")
            
            success_count = 0
            fail_count = 0
            
            for i, stock in enumerate(stocks_to_check):
                code = stock.get('code', '')
                name = stock.get('name', '')
                
                flow_data = self.money_flow_fetcher.get_stock_money_flow(code)
                if flow_data:
                    # 计算7日主力净流入总额
                    total_main_net = sum(day.get('main_net', 0) for day in flow_data)
                    inflow_map[code] = {
                        'name': name,
                        'total_net': total_main_net,
                        'days': len(flow_data),
                        'cached_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    success_count += 1
                else:
                    fail_count += 1
                
                if (i + 1) % 20 == 0:
                    print(f"   已获取 {i+1}/{len(stocks_to_check)} 只（成功:{success_count} 失败:{fail_count}）")
            
            # 判断是否成功
            if success_count > 0:
                api_success = True
                if fail_count > 0:
                    print(f"   📊 API获取成功{success_count}只，失败{fail_count}只（接口限制或网络问题）")
                else:
                    print(f"   ✅ API获取成功{success_count}只")
            else:
                print(f"   ⚠️ API获取失败（网络问题或接口限制）")
                
        except Exception as e:
            print(f"   ⚠️ API获取异常: {e}")
        
        # 2. 根据API结果决定下一步
        if api_success:
            # API成功，保存到缓存
            if inflow_map and len(inflow_map) > 0:
                try:
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(inflow_map, f, ensure_ascii=False, indent=2)
                    print(f"   💾 已保存到缓存: {os.path.basename(cache_file)}")
                except Exception as e:
                    print(f"   ⚠️ 保存缓存失败: {e}")
        else:
            # API失败，从缓存读取
            print(f"   🔄 API获取失败，尝试从缓存读取...")
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                        if cached_data and len(cached_data) > 0:
                            inflow_map = cached_data
                            from_cache = True
                            # 获取缓存时间（取第一条数据的cached_time）
                            first_item = next(iter(cached_data.values()), {})
                            cache_time = first_item.get('cached_time', '未知')
                            print(f"   ✅ 已从缓存加载{len(inflow_map)}只数据")
                            print(f"   ⏰ 缓存获取时间: {cache_time}")
                        else:
                            print(f"   ⚠️ 缓存数据为空")
                except Exception as e:
                    print(f"   ⚠️ 读取缓存失败: {e}")
            else:
                print(f"   ⚠️ 缓存文件不存在: {os.path.basename(cache_file)}")
        
        return inflow_map

    def _generate_report(self, stocks, ai_analysis, daily_quote, news=None, inflow_stocks=None, ipo_data=None):
        """生成选股报告"""
        report = []
        today = datetime.now().strftime('%Y年%m月%d日')

        # ==================== 每日一言（置顶） ====================
        report.append("")
        report.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        if OUTPUT_CONFIG.get('show_daily_quote') and daily_quote:
            report.append("📌 每日一言")
            report.append(f"   「{daily_quote}」")
        report.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # ==================== 报告标题 ====================
        report.append("")
        report.append("=" * 70)
        report.append("【Marcus量化选股系统】")
        report.append(f"报告日期: {today} {datetime.now().strftime('%H:%M:%S')}")
        report.append("=" * 70)

        # ==================== 策略说明 ====================
        report.append("")
        report.append("-" * 70)
        report.append("【策略说明】")
        report.append("-" * 70)
        report.append("综合5大量化策略 + 北向资金因子进行选股：")
        report.append("• go-stock AI策略 (20%): 技术形态 + 资金流向 + 市场情绪")
        report.append("• myhhub 多因子策略 (20%): PE + PB + ROE + 营收增长 + 量价")
        report.append("• zvt 多因子策略 (15%): 估值因子 + 动量因子 + 质量因子")
        report.append("• hikyuu 量化策略 (20%): 布林带 + 均线排列 + MACD")
        report.append("• northstar 专业策略 (25%): 技术分析 + 风险评估 + AI信号")
        report.append("• ⭐北向资金加分: 外资增持标的 +5~15分")
        report.append("• ⭐行业政策支持: 政策重点方向 +3~10分")
        report.append("")
        report.append("⚠️ 评分机制：涨幅>8%自动降权（接近涨停风险较高）")

        # ==================== 动态资讯 ====================
        if news:
            report.append("")
            report.append("-" * 70)
            report.append("【财经动态】")
            report.append("-" * 70)

            # 过滤并显示10条新闻
            valid_news = [n for n in news if n.get('title', '')]
            if valid_news:
                for i, item in enumerate(valid_news[:10], 1):
                    title = item.get('title', '')[:60]
                    source = item.get('source', '')
                    report.append(f"  {i}. {title}")
                    report.append(f"     来源: {source}")
            else:
                report.append("暂无相关财经资讯")

        # ==================== 打新日历 ====================
        if ipo_data:
            stocks_ipo = ipo_data.get('stocks', [])
            bonds_ipo = ipo_data.get('bonds', [])

            if stocks_ipo or bonds_ipo:
                report.append("")
                report.append("-" * 70)
                report.append("【打新日历】")
                report.append("-" * 70)

                # 新股申购
                if stocks_ipo:
                    report.append("")
                    report.append("📈 新股申购")
                    report.append("")
                    for item in stocks_ipo[:5]:
                        name = item.get('name', '')
                        code = item.get('code', '')
                        price = item.get('发行价', '-')
                        date = item.get('申购日期', '-')
                        limit = item.get('申购上限', '-')
                        report.append(f"  • {name}({code}) | 发行价:{price} | 申购日:{date}")
                        report.append(f"    申购上限:{limit}")

                # 可转债申购
                if bonds_ipo:
                    report.append("")
                    report.append("📊 可转债申购")
                    report.append("")
                    for item in bonds_ipo[:5]:
                        name = item.get('name', '')
                        code = item.get('code', '')
                        stock_name = item.get('正股', '-')
                        date = item.get('申购日期', '-')
                        report.append(f"  • {name}({code}) | 正股:{stock_name} | 申购日:{date}")

                if not stocks_ipo and not bonds_ipo:
                    report.append("暂无打新信息")

        # ==================== 连续净流入 ====================
        if inflow_stocks:
            report.append("")
            report.append("-" * 70)
            report.append("【主力连续净流入】")
            report.append("-" * 70)
            report.append("筛选条件：5日连续净流入 或 7日净流入占比≥60%，累计涨幅≤15%")

            for i, stock in enumerate(inflow_stocks[:10], 1):
                # 格式化金额（转换为亿/万）
                amount = stock['total_net_inflow']
                if abs(amount) >= 1e8:
                    amount_str = f"{amount/1e8:.2f}亿"
                else:
                    amount_str = f"{amount/1e4:.0f}万"

                report.append("")
                report.append(f"▶ {i}. {stock['name']}({stock['code']})")
                report.append(f"   连续净流入: {stock['net_inflow_days']}天 | 总流入: {amount_str}")
                report.append(f"   现价: {stock['price']:.2f} | 涨幅: {stock['change_pct']:+.2f}%")

        # ==================== 2. 股票选择 ====================
        report.append("")
        report.append("-" * 70)
        report.append("【股票选择】（按综合评分排序）")
        report.append("-" * 70)

        if not stocks:
            report.append("今日暂无符合条件的股票。")
        else:
            for i, stock in enumerate(stocks, 1):
                report.append("")
                change_pct = stock.get('change_pct', 0)
                warning = " ⚠️涨幅>8%已降权" if change_pct > 8 else ""
                # 风险等级显示
                risk_level = stock.get('risk_level', '中风险')
                risk_icon = "🟢" if risk_level == "低风险" else "🟡" if risk_level == "中风险" else "🔴"
                # 最强策略
                strongest = stock.get('strongest_strategy', '')
                strongest_label = f"({strongest})" if strongest else ""
                
                report.append(f"▶ {i}. {stock['name']}({stock['code']}) {risk_icon}{risk_level}{warning}")
                report.append(f"   综合评分: {stock.get('final_score', 0):.1f} | 胜率: {stock.get('win_rate', 0):.1f}%")
                report.append(f"   现价: {stock.get('price', 0):.2f} | 涨幅: {change_pct:+.2f}%")
                report.append(f"   换手率: {stock.get('turnover_rate', 0):.2f}% | PE: {stock.get('pe', 0):.1f} | PB: {stock.get('pb', 0):.1f}")

                # 入选理由
                reasons = stock.get('reasons', [])
                if reasons:
                    # 过滤掉降权提示（已在标题显示）
                    display_reasons = [r for r in reasons if '接近涨停' not in r]
                    report.append(f"   入选理由: {', '.join(display_reasons[:4])}")

                # 策略支持详情
                if OUTPUT_CONFIG.get('show_strategy_detail'):
                    strategies = stock.get('strategy_names', [])
                    if strategies:
                        report.append(f"   策略支持: {' + '.join(strategies)} {strongest_label}")

        # ==================== 3. AI分析与操作建议 ====================
        report.append("")
        report.append("-" * 70)
        report.append("【AI分析与操作建议】")
        report.append("-" * 70)

        # Top5操作建议（合并完整数据）
        if stocks:
            report.append("")
            top5 = stocks[:5] if len(stocks) >= 5 else stocks
            for i, stock in enumerate(top5, 1):
                advice = stock.get('advice', {})
                reasons = stock.get('reasons', [])
                display_reasons = [r for r in reasons if '接近涨停' not in r][:3]
                
                report.append("")
                report.append(f"{i}. {stock['name']}({stock['code']})")
                report.append(f"   操作: {advice.get('action', '观望')} | 建议仓位: {advice.get('position', 'N/A')}")
                report.append(f"   买入参考: {advice.get('entry', 'N/A')}")
                report.append(f"   止损位: {advice.get('stop_loss', 'N/A')}")
                report.append(f"   止盈位: {advice.get('take_profit', 'N/A')}")
                report.append(f"   综合评分: {stock.get('final_score', 0):.1f}")
                report.append(f"   预判胜率: {stock.get('win_rate', 0):.1f}%")
                report.append(f"   今日涨幅: {stock.get('change_pct', 0):+.2f}%")
                if display_reasons:
                    report.append(f"   入选理由: {', '.join(display_reasons)}")

        # AI市场分析（总体建议）
        if ai_analysis:
            report.append("")
            report.append("-" * 70)
            report.append(ai_analysis)

        # ==================== 4. 今日总结 ====================
        report.append("")
        report.append("=" * 70)
        report.append("【今日总结】")
        report.append("=" * 70)

        if stocks:
            up_count = sum(1 for s in stocks if s.get('change_pct', 0) > 0)
            avg_change = sum(s.get('change_pct', 0) for s in stocks) / len(stocks)
            avg_win_rate = sum(s.get('win_rate', 0) for s in stocks) / len(stocks)
            max_win_rate = max(s.get('win_rate', 0) for s in stocks)
            min_win_rate = min(s.get('win_rate', 0) for s in stocks)

            # 统计涨幅>8%的股票
            high_change_count = sum(1 for s in stocks if s.get('change_pct', 0) > 8)
            safe_change_count = len(stocks) - high_change_count

            # 风险等级统计
            low_risk = sum(1 for s in stocks if s.get('risk_level') == '低风险')
            mid_risk = sum(1 for s in stocks if s.get('risk_level') == '中风险')
            high_risk = sum(1 for s in stocks if s.get('risk_level') == '高风险')

            report.append(f"• 今日选出 {len(stocks)} 只优质股票")
            report.append(f"• AI精选建议关注 {min(len(stocks), 5)} 只")
            report.append(f"• 其中 {up_count} 只上涨，{len(stocks) - up_count} 只下跌/平盘")
            report.append(f"• 平均涨幅: {avg_change:+.2f}%")
            report.append(f"• 胜率区间: {min_win_rate:.1f}% ~ {max_win_rate:.1f}% | 平均: {avg_win_rate:.1f}%")
            report.append(f"• 风险等级: 🟢低风险{low_risk}只 | 🟡中风险{mid_risk}只 | 🔴高风险{high_risk}只")
            report.append(f"• 涨幅>8%股票: {high_change_count}只（已降权）| 安全区间: {safe_change_count}只")

            report.append("")
            report.append("【⚠️ 当日操作风险提示】")
            report.append("• 今日选股平均涨幅较高(+{:.1f}%)，追高风险较大".format(avg_change))
            report.append("• 涨幅>8%的股票虽经降权处理，但仍存在涨停打开风险")
            report.append("• 建议优先关注涨幅2%-8%区间的股票，兼顾强势与安全边际")
            report.append("• 建议控制仓位，单只建议仓位5%-15%")

            report.append("")
            report.append("【投资风险提示】")
            report.append("• 以上仅供参考，不构成投资建议")
            report.append("• 股市有风险，投资需谨慎")
            report.append("• 建议分散持仓，单只仓位不超过总资金的20%")
            report.append("• 必须设置止损位（建议-5%），严格执行")
            report.append("• 量化模型有局限性，请结合个人判断决策")
        else:
            report.append("• 今日未发现符合条件的股票，建议观望。")

        report.append("")
        report.append("=" * 70)

        return '\n'.join(report)

    def _send_report(self, report):
        """发送报告邮件"""
        if EMAIL_CONFIG.get('enabled', True):
            print("\n📧 正在发送邮件...")
            # 生成策略数据文件路径（使用最新的带编号文件）
            today_str = datetime.now().strftime('%Y%m%d')
            # 查找最新的文件
            latest_file = None
            max_seq = 0
            for f in os.listdir(CACHE_DIR):
                if f.startswith(f"{today_str}_策略选股数据_") and f.endswith('.txt'):
                    try:
                        seq = int(f.replace(f"{today_str}_策略选股数据_", "").replace(".txt", ""))
                        if seq > max_seq:
                            max_seq = seq
                            latest_file = f
                    except:
                        pass
            if latest_file:
                attachment_path = os.path.join(CACHE_DIR, latest_file)
            else:
                attachment_path = os.path.join(CACHE_DIR, f"{today_str}_策略选股数据.txt")
            self.mail_sender.send_selection_report(report, attachment_path=attachment_path)
        else:
            print("\n⚠️ 邮件发送未启用")

    def _save_cache(self, stocks):
        """保存数据到缓存"""
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'stocks': stocks
            }
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False)
            print(f"✅ 缓存已保存: {len(stocks)}只股票")
        except Exception as e:
            print(f"⚠️ 缓存保存失败: {e}")

    def _load_cache(self):
        """加载缓存数据"""
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    self.cached_stocks = cache_data.get('stocks', [])
                    print(f"🔧 [调试模式] 读取缓存: {len(self.cached_stocks)}只股票")
        except Exception as e:
            print(f"⚠️ 缓存读取失败: {e}")
            self.cached_stocks = []

    def _save_strategy_data(self, strategy_results, top_stocks, inflow_stocks, inflow_map=None):
        """保存策略选股数据到文件
        
        Args:
            inflow_map: 主力净流入字典 {代码: {name, total_net, days}}
        """
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            today = datetime.now().strftime('%Y%m%d')

            # 查找当天已有的文件数量，生成自增编号
            existing_files = []
            for f in os.listdir(CACHE_DIR):
                if f.startswith(f"{today}_策略选股数据") and f.endswith('.txt'):
                    existing_files.append(f)
            seq_num = len(existing_files) + 1  # 自增编号

            # 创建股票代码到涨幅的映射（从top_stocks获取）
            stock_change_map = {}
            for stock in top_stocks:
                code = stock.get('code', '')
                stock_change_map[code] = stock.get('change_pct', 0)
            
            # 策略名称映射
            strategy_names = {
                'gostock': 'go-stock_AI策略',
                'myhhub': 'myhhub_多因子',
                'zvt': 'zvt_多因子',
                'hikyuu': 'hikyuu_量化',
                'northstar': 'northstar_专业',
            }
            
            content = []
            content.append("=" * 70)
            content.append(f"Marcus量化选股系统 - 策略选股数据")
            content.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            content.append("=" * 70)
            content.append("")
            
            # 各策略筛选结果
            content.append("【各策略筛选的股票列表】")
            content.append("-" * 50)
            
            for strategy_key, stocks in strategy_results.items():
                strategy_name = strategy_names.get(strategy_key, strategy_key)
                content.append("")
                content.append(f"▶ {strategy_name} ({len(stocks)}只):")

                for i, stock in enumerate(stocks[:20], 1):  # 每策略最多20只
                    code = stock.get('code', '')
                    name = stock.get('name', '')
                    # 从映射获取涨幅
                    change_pct = stock_change_map.get(code, 0)
                    content.append(f"   {i:2d}. {name}({code}) 涨幅:{change_pct:+.2f}%")
            
            # 连续净流入板块
            if inflow_stocks:
                content.append("")
                content.append("【连续净流入板块】")
                content.append("-" * 50)
                content.append("筛选条件：5日连续净流入 或 7日净流入占比≥60%，累计涨幅≤15%")
                content.append("")
                
                for i, stock in enumerate(inflow_stocks[:10], 1):
                    code = stock.get('code', '')
                    name = stock.get('name', '')
                    net_days = stock.get('net_inflow_days', 0)
                    total_net = stock.get('total_net_inflow', 0)
                    if abs(total_net) >= 1e8:
                        amount_str = f"{total_net/1e8:.2f}亿"
                    else:
                        amount_str = f"{total_net/1e4:.0f}万"
                    
                    content.append(f"▶ {i}. {name}({code})")
                    content.append(f"   连续净流入:{net_days}天 | 总流入:{amount_str}")
            
            # 综合评分Top15
            if top_stocks:
                content.append("")
                content.append("【综合评分Top15】")
                content.append("-" * 50)
                
                for i, stock in enumerate(top_stocks[:10], 1):
                    code = stock.get('code', '')
                    name = stock.get('name', '')
                    score = stock.get('final_score', 0)
                    win_rate = stock.get('win_rate', 0)
                    change_pct = stock.get('change_pct', 0)
                    risk_level = stock.get('risk_level', '中风险')
                    risk_icon = "🟢" if risk_level == "低风险" else "🟡" if risk_level == "中风险" else "🔴"
                    
                    # 获取主力净流入信息
                    inflow_info = inflow_map.get(code) if inflow_map else None
                    if inflow_info and inflow_info.get('total_net') is not None:
                        total_net = inflow_info['total_net']
                        if abs(total_net) >= 1e8:
                            net_str = f"{total_net/1e8:.2f}亿"
                        elif abs(total_net) >= 1e4:
                            net_str = f"{total_net/1e4:.0f}万"
                        else:
                            net_str = f"{total_net:.0f}元"
                        main_inflow_str = f" 主力净流入:{net_str}"
                    else:
                        main_inflow_str = "  # 主力净流入:N/A"
                    
                    content.append(f"{i:2d}. {name}({code}) {risk_icon}")
                    content.append(f"    评分:{score:.1f} 胜率:{win_rate:.1f}% 涨幅:{change_pct:+.2f}%{main_inflow_str}")
            
            content.append("")
            content.append("=" * 70)
            content.append("文件结束")
            content.append("=" * 70)
            
            # 保存文件（带自增编号）
            filename = f"{today}_策略选股数据_{seq_num}.txt"
            filepath = os.path.join(CACHE_DIR, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(content))
            
            print(f"✅ 策略数据已保存: {filename}")
            
        except Exception as e:
            print(f"⚠️ 策略数据保存失败: {e}")


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description='AI智能选股系统')
    parser.add_argument('--no-email', action='store_true', help='不发送邮件')
    args = parser.parse_args()

    selector = AISStockSelector()
    selector.run(send_email=not args.no_email)


if __name__ == "__main__":
    # 设置UTF-8编码
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
