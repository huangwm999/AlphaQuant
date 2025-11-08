#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略决策接口模块
提供统一的策略分析接口，支持动态选择策略版本。
"""

class StrategyInterface:
    """策略决策接口类 - 支持动态选择策略版本。
    
    支持的策略版本:
    - strategy_decision_v1: 基于LLM的智能分析策略
    - strategy_decision_v2: MACD Signal线V型/倒V型转折策略
    - strategy_decision_v3: 布林带下轨突破 + MACD倒V卖出混合策略
    - strategy_decision_v4: MACD Signal线V型转折 + 布林带突破(MACD下降)
    """
    
    def __init__(self, deepseek_client, strategy_version='strategy_decision_v2'):
        """
        初始化策略接口。
        
        Args:
            deepseek_client: DeepSeek AI客户端。
            strategy_version: 策略版本 ('strategy_decision_v1', 'strategy_decision_v2', 'strategy_decision_v3', 'strategy_decision_v4')，默认 'strategy_decision_v2'
        """
        self.strategy_version = strategy_version
        self._load_strategy(deepseek_client)
    
    def _load_strategy(self, deepseek_client):
        """根据版本号动态加载策略分析器"""
        if self.strategy_version == 'strategy_decision_v1':
            from strategy_decision_v1 import StrategyAnalyzer
        elif self.strategy_version == 'strategy_decision_v3':
            from strategy_decision_v3 import StrategyAnalyzer
        elif self.strategy_version == 'strategy_decision_v4':
            from strategy_decision_v4 import StrategyAnalyzer
        else:  # 默认 strategy_decision_v2
            from strategy_decision_v2 import StrategyAnalyzer
        
        # 实例化对应版本的策略分析器
        self._strategy_analyzer = StrategyAnalyzer(deepseek_client)
        print(f"✓ 策略版本: {self.strategy_version}")
    
    def analyze_market_strategy(self, price_data, signal_history, max_retries=2):
        """
        分析市场策略的外部接口。
        
        此方法将参数传递给当前策略实现。
        """
        return self._strategy_analyzer.analyze_market_strategy(
            price_data=price_data,
            signal_history=signal_history,
            max_retries=max_retries
        )
    
    def get_strategy_info(self):
        """获取当前策略版本信息"""
        return {
            'version': self.strategy_version,
            'name': getattr(self._strategy_analyzer, '__class__.__name__', 'Unknown')
        }
