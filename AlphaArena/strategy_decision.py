#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略决策接口模块
提供统一的策略分析接口，直接调用v1版本实现。
"""

# 从v1实现中导入具体的策略分析器类
from strategy_decision_v1 import StrategyAnalyzer

class StrategyInterface:
    """
    策略决策接口类。
    
    这是一个简单的包装器，用于调用具体的策略实现（当前为v1）。
    它的目的是提供一个稳定的接口，而将具体的、可能变动的实现细节封装在v1文件中。
    未来若有v2版本，只需修改上面的导入语句即可。
    """
    
    def __init__(self, deepseek_client):
        """
        初始化策略接口。
        
        Args:
            deepseek_client: DeepSeek AI客户端。
        """
        # 内部实例化一个v1版本的分析器
        self._strategy_analyzer = StrategyAnalyzer(deepseek_client)
    
    def analyze_market_strategy(self, price_data, generate_technical_analysis_text, 
                               get_recent_ai_analysis, get_recent_trades, signal_history, max_retries=2):
        """
        分析市场策略的外部接口。
        
        此方法将所有参数直接传递给内部的v1分析器实例来执行实际的分析工作。
        """
        return self._strategy_analyzer.analyze_market_strategy(
            price_data=price_data,
            generate_technical_analysis_text=generate_technical_analysis_text,
            get_recent_ai_analysis=get_recent_ai_analysis,
            get_recent_trades=get_recent_trades,
            signal_history=signal_history,
            max_retries=max_retries
        )
