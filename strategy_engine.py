# -*- coding: utf-8 -*-
"""
选股策略引擎 - 综合多个量化仓库的选股方法论
参考: go-stock, myhhub/stock, zvt, hikyuu, northstar
"""

import time
import random
from datetime import datetime
from config import *


class StrategyEngine:
    """选股策略引擎"""

    def __init__(self, stocks_data):
        self.stocks = stocks_data
        self.results = []

    def run_all_strategies(self):
        """
        运行所有启用的策略
        返回: 各策略选出的股票及评分
        """
        print("\n🧠 开始运行选股策略...")
        print("=" * 60)

        strategy_results = {}

        # 1. go-stock AI策略
        if STRATEGY_GOSTOCK['enabled']:
            print(f"\n📌 策略1: {STRATEGY_GOSTOCK['name']}")
            strategy_results['gostock'] = self._strategy_gostock()

        # 2. myhhub 多因子策略
        if STRATEGY_MYHHUB['enabled']:
            print(f"\n📌 策略2: {STRATEGY_MYHHUB['name']}")
            strategy_results['myhhub'] = self._strategy_myhhub()

        # 3. zvt 多因子策略
        if STRATEGY_ZVT['enabled']:
            print(f"\n📌 策略3: {STRATEGY_ZVT['name']}")
            strategy_results['zvt'] = self._strategy_zvt()

        # 4. hikyuu 量化策略
        if STRATEGY_HIKYUU['enabled']:
            print(f"\n📌 策略4: {STRATEGY_HIKYUU['name']}")
            strategy_results['hikyuu'] = self._strategy_hikyuu()

        # 5. northstar 专业策略
        if STRATEGY_NORTHSTAR['enabled']:
            print(f"\n📌 策略5: {STRATEGY_NORTHSTAR['name']}")
            strategy_results['northstar'] = self._strategy_northstar()

        print("\n" + "=" * 60)
        return strategy_results

    def _strategy_gostock(self):
        """
        go-stock AI策略
        参考: 基于AI分析市场情绪、资金流向、技术形态
        """
        print("   分析维度: 技术形态 + 资金流向 + 市场情绪")

        scored_stocks = []

        for stock in self.stocks:
            score = 0
            reasons = []

            # 基本面筛选
            if stock.get('pe', 0) > 0 and stock.get('pe', 0) < 50:
                score += 20
                reasons.append("市盈率合理")

            # 技术形态评分
            change_pct = stock.get('change_pct', 0)
            turnover_rate = stock.get('turnover_rate', 0)

            # 涨幅强劲但未涨停(2%-9.5%)
            if 2 <= change_pct <= 9.5:
                score += 25
                reasons.append(f"涨幅健康({change_pct:.1f}%)")

            # 换手率适中(3%-10%)
            if 3 <= turnover_rate <= 10:
                score += 15
                reasons.append(f"换手活跃({turnover_rate:.1f}%)")

            # 量比
            if stock.get('volume_ratio', 0) >= 1.2:
                score += 15
                reasons.append("量比放大")

            # 振幅
            amplitude = stock.get('amplitude', 0)
            if 2 <= amplitude <= 10:
                score += 10
                reasons.append(f"振幅适中({amplitude:.1f}%)")

            # 位置评分（价格在日内区间高位）
            if stock.get('position_score', 50) > 60:
                score += 15
                reasons.append("价格走势强劲")

            if score >= SELECTION_CONFIG.get('strategy_min_score', 45):
                scored_stocks.append({
                    'code': stock['code'],
                    'name': stock['name'],
                    'score': score,
                    'strategy': 'go-stock AI策略',
                    'reasons': reasons
                })

        # 按评分排序
        scored_stocks.sort(key=lambda x: x['score'], reverse=True)
        print(f"   筛选出 {len(scored_stocks)} 只股票")

        # 返回更多候选股票
        return scored_stocks[:SELECTION_CONFIG.get('strategy_candidates', 15)]

    def _strategy_myhhub(self):
        """
        myhhub 多因子策略
        参考: 综合基本面+技术面+信息面多因子评分
        """
        print("   分析维度: PE + PB + ROE + 营收增长 + 量价")

        factors = STRATEGY_MYHHUB['factors']
        scored_stocks = []

        for stock in self.stocks:
            score = 0
            reasons = []
            factor_details = []

            # 市盈率因子 (权重15%)
            pe = stock.get('pe', 0)
            if pe > 0 and factors['pe_ratio']['min'] <= pe <= factors['pe_ratio']['max']:
                score += factors['pe_ratio']['weight'] * 100
                factor_details.append(f"PE={pe:.1f}")

            # 市净率因子 (权重10%)
            pb = stock.get('pb', 0)
            if pb > 0 and factors['pb_ratio']['min'] <= pb <= factors['pb_ratio']['max']:
                score += factors['pb_ratio']['weight'] * 100
                factor_details.append(f"PB={pb:.1f}")

            # 涨幅因子 (权重15%) - 2%-9.5%强劲但未涨停
            change_pct = stock.get('change_pct', 0)
            if 2 <= change_pct <= 9.5:
                score += factors['price_change']['weight'] * 100
                factor_details.append(f"涨幅={change_pct:.1f}%")

            # 换手率因子 (权重10%)
            turnover_rate = stock.get('turnover_rate', 0)
            if turnover_rate >= factors['turnover_rate']['min']:
                score += factors['turnover_rate']['weight'] * 100
                factor_details.append(f"换手={turnover_rate:.1f}%")

            # 量比因子 (权重10%)
            if stock.get('volume_ratio', 0) >= factors['volume_ratio']['min']:
                score += factors['volume_ratio']['weight'] * 100
                factor_details.append("量比≥1.2")

            # 振幅因子 (权重15%)
            amplitude = stock.get('amplitude', 0)
            if factors['amplitude']['min'] <= amplitude <= factors['amplitude']['max']:
                score += factors['amplitude']['weight'] * 100
                factor_details.append(f"振幅={amplitude:.1f}%")

            # ROE预估（用change_pct代替）
            if change_pct > 0:
                score += 10
                factor_details.append("走势正向")

            if score >= SELECTION_CONFIG.get('strategy_min_score', 45):
                scored_stocks.append({
                    'code': stock['code'],
                    'name': stock['name'],
                    'score': score,
                    'strategy': 'myhhub 多因子',
                    'reasons': factor_details
                })

        scored_stocks.sort(key=lambda x: x['score'], reverse=True)
        print(f"   筛选出 {len(scored_stocks)} 只股票")

        return scored_stocks[:SELECTION_CONFIG.get('strategy_candidates', 15)]

    def _strategy_zvt(self):
        """
        zvt 多因子策略
        参考: 中低频多因子，支持行业轮动
        """
        print("   分析维度: 估值因子 + 动量因子 + 质量因子")

        scored_stocks = []

        for stock in self.stocks:
            score = 0
            reasons = []

            # 估值因子
            pe = stock.get('pe', 0)
            pb = stock.get('pb', 0)

            if 0 < pe < 40:  # 低市盈率
                score += 20
                reasons.append(f"低PE({pe:.1f})")

            if 0 < pb < 5:  # 低市净率
                score += 15
                reasons.append(f"低PB({pb:.1f})")

            # 动量因子 - 强劲但未涨停
            change_pct = stock.get('change_pct', 0)
            if 3 <= change_pct <= 9:
                score += 25
                reasons.append(f"动量强劲({change_pct:.1f}%)")

            # 换手率（市场参与度）
            if stock.get('turnover_rate', 0) >= 3:
                score += 20
                reasons.append("高换手")

            # 成交额（市场认可度）
            turnover = stock.get('turnover', 0)
            if turnover >= FILTER_RULES['min_turnover'] * 10000:
                score += 20
                reasons.append("成交活跃")

            if score >= SELECTION_CONFIG.get('strategy_min_score', 45):
                scored_stocks.append({
                    'code': stock['code'],
                    'name': stock['name'],
                    'score': score,
                    'strategy': 'zvt 多因子',
                    'reasons': reasons
                })

        scored_stocks.sort(key=lambda x: x['score'], reverse=True)
        print(f"   筛选出 {len(scored_stocks)} 只股票")

        return scored_stocks[:SELECTION_CONFIG.get('strategy_candidates', 15)]

    def _strategy_hikyuu(self):
        """
        hikyuu 量化策略
        参考: 均值回归 + 趋势跟踪
        """
        print("   分析维度: 布林带位置 + 均线排列 + MACD")

        scored_stocks = []

        for stock in self.stocks:
            score = 0
            reasons = []

            strategies = STRATEGY_HIKYUU['strategies']

            # 均值回归策略
            if strategies['mean_reversion']['enabled']:
                # 价格位置（在布林带中轨附近或上方）
                position = stock.get('position_score', 50)
                if 40 <= position <= 80:  # 偏离不过分
                    score += 20
                    reasons.append("价格回归中轨")

            # 趋势跟踪策略
            if strategies['trend_following']['enabled']:
                change_pct = stock.get('change_pct', 0)

                # 均线多头排列（强劲但未涨停）
                if 2 <= change_pct <= 8:
                    score += 25
                    reasons.append("趋势向好")

                # 动能指标
                momentum = stock.get('momentum', 0)
                if momentum > 0:
                    score += 15
                    reasons.append("正向动能")

            # 涨幅合理性 - 强劲但未涨停
            if 3 <= change_pct <= 9:
                score += 20
                reasons.append(f"涨幅合理({change_pct:.1f}%)")

            # 换手率
            if stock.get('turnover_rate', 0) >= 2:
                score += 20
                reasons.append("流动性好")

            if score >= SELECTION_CONFIG.get('strategy_min_score', 45):
                scored_stocks.append({
                    'code': stock['code'],
                    'name': stock['name'],
                    'score': score,
                    'strategy': 'hikyuu 量化',
                    'reasons': reasons
                })

        scored_stocks.sort(key=lambda x: x['score'], reverse=True)
        print(f"   筛选出 {len(scored_stocks)} 只股票")

        return scored_stocks[:SELECTION_CONFIG.get('strategy_candidates', 15)]

    def _strategy_northstar(self):
        """
        northstar 专业策略
        参考: 技术分析 + AI辅助 + 风险管理
        """
        print("   分析维度: 技术分析 + 风险评估 + AI信号")

        scored_stocks = []

        for stock in self.stocks:
            score = 0
            reasons = []

            modules = STRATEGY_NORTHSTAR['modules']
            risk = modules['risk_management']

            # 技术分析评分
            change_pct = stock.get('change_pct', 0)
            turnover_rate = stock.get('turnover_rate', 0)

            # 涨幅在合理范围
            if 0 < change_pct <= 10:
                score += 25
                reasons.append(f"涨幅({change_pct:.1f}%)")

            # 换手率正常
            if 2 <= turnover_rate <= 15:
                score += 20
                reasons.append(f"换手({turnover_rate:.1f}%)")

            # 成交额足够
            turnover = stock.get('turnover', 0)
            if turnover >= 50000000:  # 5000万
                score += 15
                reasons.append("成交达标")

            # PE/PB合理
            pe = stock.get('pe', 0)
            pb = stock.get('pb', 0)
            if 0 < pe < 60:
                score += 20
                reasons.append(f"PE合理({pe:.1f})")

            if 0 < pb < 8:
                score += 20
                reasons.append(f"PB合理({pb:.1f})")

            if score >= SELECTION_CONFIG.get('strategy_min_score', 45):
                scored_stocks.append({
                    'code': stock['code'],
                    'name': stock['name'],
                    'score': score,
                    'strategy': 'northstar 专业',
                    'reasons': reasons
                })

        scored_stocks.sort(key=lambda x: x['score'], reverse=True)
        print(f"   筛选出 {len(scored_stocks)} 只股票")

        return scored_stocks[:SELECTION_CONFIG.get('strategy_candidates', 15)]

    def merge_and_rank(self, strategy_results):
        """
        合并多策略结果，计算综合评分
        参考: go-stock + myhhub 综合评分系统
        增加接近涨停惩罚机制
        """
        print("\n📊 合并策略结果，计算综合评分...")

        # 接近涨停惩罚配置
        near_limit_penalty = FILTER_RULES.get('near_limit_penalty', True)
        near_limit_threshold = FILTER_RULES.get('near_limit_threshold', 9.0)

        # 统计每只股票在各策略中的出现次数和评分
        stock_scores = {}

        for strategy_name, stocks in strategy_results.items():
            weight = 0.2  # 默认权重
            if strategy_name == 'gostock':
                weight = STRATEGY_GOSTOCK['weight']
            elif strategy_name == 'myhhub':
                weight = STRATEGY_MYHHUB['weight']
            elif strategy_name == 'zvt':
                weight = STRATEGY_ZVT['weight']
            elif strategy_name == 'hikyuu':
                weight = STRATEGY_HIKYUU['weight']
            elif strategy_name == 'northstar':
                weight = STRATEGY_NORTHSTAR['weight']

            for rank, stock in enumerate(stocks, 1):
                code = stock['code']
                # 排名加权（第一名100分，每降一名减5分）
                rank_score = 100 - (rank - 1) * 5
                weighted_score = rank_score * weight

                if code not in stock_scores:
                    stock_scores[code] = {
                        'code': code,
                        'name': stock['name'],
                        'total_score': 0,
                        'strategy_count': 0,
                        'strategy_names': [],
                        'all_reasons': [],
                        'details': {}
                    }

                stock_scores[code]['total_score'] += weighted_score
                stock_scores[code]['strategy_count'] += 1
                stock_scores[code]['strategy_names'].append(stock['strategy'])
                stock_scores[code]['all_reasons'].extend(stock['reasons'])
                stock_scores[code]['details'][strategy_name] = {
                    'score': rank_score,
                    'reasons': stock['reasons']
                }

        # 转换为列表并计算胜率
        final_list = []
        for code, data in stock_scores.items():
            # 策略覆盖率
            coverage = data['strategy_count'] / len([s for s in strategy_results if STRATEGY_GOSTOCK.get('enabled', True)]) * 100

            # 综合评分（考虑策略覆盖）
            final_score = data['total_score'] * (1 + coverage / 100)

            # 获取股票完整信息
            stock_info = next((s for s in self.stocks if s['code'] == code), {})
            change_pct = stock_info.get('change_pct', 0)

            # 接近涨停惩罚：涨幅>9%时降低评分
            if near_limit_penalty and change_pct > near_limit_threshold:
                penalty = 0.7  # 乘以0.7的惩罚系数
                final_score = final_score * penalty
                penalty_note = f"⚠️涨幅{change_pct:.1f}%接近涨停，评分×{penalty}"
                data['all_reasons'].append(penalty_note)
            elif change_pct >= 9.5:
                # 涨停股直接排除（虽然过滤了，但做双重保险）
                continue

            # 估算胜率（基于多策略一致性和评分）
            win_rate = min(95, 50 + final_score / 3)

            final_list.append({
                'code': code,
                'name': data['name'],
                'final_score': round(final_score, 1),
                'win_rate': round(win_rate, 1),
                'strategy_count': data['strategy_count'],
                'strategy_names': data['strategy_names'],
                'reasons': list(set(data['all_reasons']))[:5],  # 去重，最多5个原因
                'details': data['details'],
                'price': stock_info.get('price', 0),
                'change_pct': change_pct,
                'turnover_rate': stock_info.get('turnover_rate', 0),
                'pe': stock_info.get('pe', 0),
                'pb': stock_info.get('pb', 0),
            })

        # 按综合评分排序
        final_list.sort(key=lambda x: x['final_score'], reverse=True)

        # 取前N只
        top_stocks = final_list[:SELECTION_CONFIG['top_n']]

        print(f"✅ 综合评分完成，选出 {len(top_stocks)} 只优质股票")
        if near_limit_penalty:
            print(f"   涨幅>9%股票已降权（接近涨停难以买入）")

        # 应用增强的胜率评分和排序
        top_stocks = self._apply_win_rate_ranking(top_stocks, strategy_results)

        return top_stocks

    def _apply_win_rate_ranking(self, stocks, strategy_results):
        """
        应用增强的胜率评分和排序系统
        综合考虑：策略一致性、技术指标、风险评估
        """
        if not stocks:
            return stocks

        total_strategies = len([s for s in STRATEGY_GOSTOCK.keys() if isinstance(STRATEGY_GOSTOCK.get(s if isinstance(s, str) else '', {}), dict) and STRATEGY_GOSTOCK.get(s if isinstance(s, str) else '', {}).get('enabled', False)])

        # 计算每只股票的胜率因子和综合胜率
        ranked_stocks = []
        for stock in stocks:
            # 获取股票完整信息
            stock_data = next((s for s in self.stocks if s['code'] == stock['code']), stock)

            # 计算各个胜率因子
            factor_scores = self._calculate_win_rate_factors(stock, stock_data, total_strategies)

            # 计算综合胜率
            win_rate = self._calculate_composite_win_rate(factor_scores)

            # 计算综合排序分数
            ranking_score = self._calculate_ranking_score(stock, win_rate, factor_scores)

            # 找出最强策略
            strongest_strategy = ""
            max_strategy_score = 0
            if 'details' in stock:
                for strategy_name, details in stock.get('details', {}).items():
                    if details.get('score', 0) > max_strategy_score:
                        max_strategy_score = details['score']
                        strongest_strategy = strategy_name

            ranked_stocks.append({
                **stock,
                'win_rate': round(win_rate, 1),
                'win_rate_factors': factor_scores,
                'ranking_score': round(ranking_score, 1),
                'strongest_strategy': strongest_strategy,
                'risk_level': self._assess_risk_level(stock_data, factor_scores)
            })

        # 按综合排序分数排序
        ranked_stocks.sort(key=lambda x: (x['ranking_score'], x['win_rate']), reverse=True)

        # 打印胜率分布
        if ranked_stocks:
            win_rates = [s['win_rate'] for s in ranked_stocks]
            print(f"📊 胜率分布: 最高 {max(win_rates):.1f}% | 最低 {min(win_rates):.1f}% | 平均 {sum(win_rates)/len(win_rates):.1f}%")

        return ranked_stocks

    def _calculate_win_rate_factors(self, stock, stock_data, total_strategies):
        """
        计算各胜率因子得分 (0-100)
        因子包括：策略一致性、涨幅健康度、换手活跃度、量比、PE、振幅、流动性
        """
        factors = WIN_RATE_CONFIG['factors']
        factor_scores = {}

        # 1. 策略一致性因子 (0-100) - 多策略同时选中更可靠
        strategy_count = stock.get('strategy_count', 0)
        strategy_ratio = strategy_count / max(total_strategies, 1)
        if strategy_ratio >= 0.8:
            factor_scores['strategy_count'] = 100
        elif strategy_ratio >= 0.6:
            factor_scores['strategy_count'] = 85
        elif strategy_ratio >= 0.4:
            factor_scores['strategy_count'] = 70
        elif strategy_ratio >= 0.2:
            factor_scores['strategy_count'] = 50
        else:
            factor_scores['strategy_count'] = 30

        # 2. 涨幅健康度因子 (0-100) - 2%-6%最佳，6%-8%次之
        change_pct = stock_data.get('change_pct', 0)
        if 2 <= change_pct <= 6:
            factor_scores['change_pct'] = 100
        elif 6 < change_pct <= 8:
            factor_scores['change_pct'] = 90
        elif 1 <= change_pct < 2:
            factor_scores['change_pct'] = 60
        elif 8 < change_pct <= 9.5:
            factor_scores['change_pct'] = 40  # 接近涨停风险高
        else:
            factor_scores['change_pct'] = 30

        # 3. 换手活跃度因子 (0-100) - 3%-10%最佳
        turnover_rate = stock_data.get('turnover_rate', 0)
        if 3 <= turnover_rate <= 10:
            factor_scores['turnover_rate'] = 100
        elif 1 <= turnover_rate < 3:
            factor_scores['turnover_rate'] = 60
        elif 10 < turnover_rate <= 20:
            factor_scores['turnover_rate'] = 75
        else:
            factor_scores['turnover_rate'] = 40

        # 4. 量比放大因子 (0-100) - >1.5较好
        volume_ratio = stock_data.get('volume_ratio', 0)
        if volume_ratio >= 2.0:
            factor_scores['volume_ratio'] = 100
        elif volume_ratio >= 1.5:
            factor_scores['volume_ratio'] = 85
        elif volume_ratio >= 1.2:
            factor_scores['volume_ratio'] = 70
        elif volume_ratio >= 1.0:
            factor_scores['volume_ratio'] = 55
        else:
            factor_scores['volume_ratio'] = 40

        # 5. 市盈率合理因子 (0-100) - 0<PE<30最佳
        pe = stock_data.get('pe', 0)
        if 0 < pe <= 15:
            factor_scores['pe_ratio'] = 100
        elif 15 < pe <= 30:
            factor_scores['pe_ratio'] = 85
        elif 30 < pe <= 50:
            factor_scores['pe_ratio'] = 60
        else:
            factor_scores['pe_ratio'] = 40

        # 6. 振幅适中因子 (0-100) - 2%-6%最佳
        amplitude = stock_data.get('amplitude', 0)
        if 2 <= amplitude <= 6:
            factor_scores['amplitude'] = 100
        elif 6 < amplitude <= 8:
            factor_scores['amplitude'] = 85
        elif 1 <= amplitude < 2:
            factor_scores['amplitude'] = 60
        else:
            factor_scores['amplitude'] = 50

        # 7. 流动性因子 (使用成交额)
        turnover = stock_data.get('turnover', 0)
        if turnover >= 100000:  # 10亿以上
            factor_scores['market_cap'] = 100
        elif turnover >= 50000:  # 5亿以上
            factor_scores['market_cap'] = 85
        elif turnover >= 30000:  # 3亿以上
            factor_scores['market_cap'] = 70
        else:
            factor_scores['market_cap'] = 50

        return factor_scores

    def _calculate_composite_win_rate(self, factor_scores):
        """
        综合计算胜率
        基于各因子得分加权平均
        """
        factors = WIN_RATE_CONFIG['factors']
        base_rate = WIN_RATE_CONFIG['base_win_rate']
        max_rate = WIN_RATE_CONFIG['max_win_rate']

        weighted_sum = 0
        total_weight = 0
        for factor_name, weight in factors.items():
            score = factor_scores.get(factor_name, 50)  # 默认50分
            weighted_sum += score * weight
            total_weight += weight

        if total_weight > 0:
            normalized_score = weighted_sum / total_weight
            # 将0-100的分数映射到min_win_rate-max_win_rate的胜率
            min_rate = WIN_RATE_CONFIG['min_win_rate']
            win_rate = min_rate + (normalized_score / 100) * (max_rate - min_rate)
            win_rate = min(max_rate, max(min_rate, win_rate))
        else:
            win_rate = base_rate

        return win_rate

    def _calculate_ranking_score(self, stock, win_rate, factor_scores):
        """
        计算综合排序分数
        综合考虑：评分、胜率、涨幅、策略数量
        """
        sort_factors = RANKING_CONFIG['sort_factors']

        # 标准化各因子到0-100
        final_score = stock.get('final_score', 50) / 2  # 假设评分在0-200范围
        win_rate_normalized = win_rate
        change_pct = factor_scores.get('change_pct', 50)
        strategy_count_normalized = factor_scores.get('strategy_count', 30)

        ranking_score = (
            final_score * sort_factors['final_score'] +
            win_rate_normalized * sort_factors['win_rate'] +
            change_pct * sort_factors['change_pct'] +
            strategy_count_normalized * sort_factors['strategy_count']
        )

        return ranking_score

    def _assess_risk_level(self, stock_data, factor_scores):
        """
        评估股票风险等级
        返回: 低风险(绿) / 中风险(黄) / 高风险(红)
        """
        change_pct = stock_data.get('change_pct', 0)
        turnover_rate = stock_data.get('turnover_rate', 0)
        pe = stock_data.get('pe', 0)
        risk_score = 0

        # 涨幅风险
        if change_pct >= 7:
            risk_score += 2
        elif change_pct >= 6:
            risk_score += 1

        # 换手率风险
        if turnover_rate >= 15:
            risk_score += 2
        elif turnover_rate <= 1:
            risk_score += 1

        # PE风险
        if pe > 60:
            risk_score += 1
        elif pe <= 0:
            risk_score += 2

        if risk_score >= 3:
            return "高风险"
        elif risk_score >= 1:
            return "中风险"
        else:
            return "低风险"


def filter_stocks(stocks):
    """
    应用过滤规则
    参考: myhhub/stock 过滤规则
    - 过滤涨停股（涨停无法买进）
    - 过滤ST股、停牌、科创板、北交所
    - 要求涨幅1%-8%之间
    - 过滤市值小于30亿
    """
    print("\n🔍 应用过滤规则...")

    filtered = []
    limit_up_threshold = FILTER_RULES.get('limit_up_threshold', 8.0)
    change_range = FILTER_RULES.get('change_pct_range', {})

    for stock in stocks:
        code = stock.get('code', '')

        # 过滤688开头（科创板）
        if any(code.startswith(prefix) for prefix in FILTER_RULES['exclude_code_prefix']):
            continue

        # 过滤北交所（代码8开头或bj开头）
        if FILTER_RULES.get('exclude_bj', True) and (code.startswith('8') or code.startswith('bj')):
            continue

        # 过滤ST股
        if FILTER_RULES['exclude_st'] and ('ST' in stock.get('name', '') or '*ST' in stock.get('name', '')):
            continue

        # 过滤停牌
        if FILTER_RULES['exclude_suspended'] and stock.get('price', 0) == 0:
            continue

        # 过滤涨停（涨幅>=8%，涨停无法买进）
        try:
            change_pct = float(stock.get('change_pct', 0) or 0)
        except (ValueError, TypeError):
            continue  # 跳过无效数据
        
        if FILTER_RULES['exclude_limit_up'] and change_pct >= limit_up_threshold:
            continue

        # 过滤跌停
        if FILTER_RULES['exclude_limit_down'] and change_pct <= -9.9:
            continue

        # 涨幅范围过滤
        if change_range:
            min_change = float(change_range.get('min', 0))
            max_change = float(change_range.get('max', limit_up_threshold))
            if change_pct < min_change or change_pct > max_change:
                continue

        # 过滤成交额过低
        try:
            turnover = float(stock.get('turnover', 0) or 0)
            if turnover < FILTER_RULES['min_turnover'] * 10000:
                continue
        except (ValueError, TypeError):
            continue

        # 过滤PE为负（亏损）
        try:
            pe = float(stock.get('pe', 0) or 0)
            if pe < 0:
                continue
        except (ValueError, TypeError):
            pass  # PE无效时不作为过滤条件

        filtered.append(stock)

    min_change = float(change_range.get('min', 1))
    max_change = float(change_range.get('max', 8))
    print(f"   过滤后剩余 {len(filtered)} 只股票（涨幅范围: {min_change}%~{max_change}%，排除ST/科创板/北交所）")
    return filtered
