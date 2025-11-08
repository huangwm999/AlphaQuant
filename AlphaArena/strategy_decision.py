#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略决策接口模块
提供统一的策略分析接口，当前使用 v2 (MACD V/倒V 转折) 实现。
切换策略版本只需修改下方导入。
"""

# 导入当前启用的策略实现 (v2 基于MACD转折)
from strategy_decision_v2 import StrategyAnalyzer

class StrategyInterface:
    """策略决策接口类 - 封装当前启用的策略实现。

    当前版本: v2 (MACD柱状图V型/倒V型转折)。
    切换实现: 修改文件顶部的导入为 v1 / v3 等其他版本即可。
    """
    
    def __init__(self, deepseek_client):
        """
        初始化策略接口。
        
        Args:
            deepseek_client: DeepSeek AI客户端。
        """
    # 实例化当前策略版本的分析器
        self._strategy_analyzer = StrategyAnalyzer(deepseek_client)
    
    def analyze_market_strategy(self, price_data, signal_history, max_retries=2):
        """
        分析市场策略的外部接口。
        
    此方法将参数传递给当前策略实现（v2）。
        """
        return self._strategy_analyzer.analyze_market_strategy(
            price_data=price_data,
            signal_history=signal_history,
            max_retries=max_retries
        )
