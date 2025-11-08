#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略决策模块 V2 - 基于MACD柱状图V型/倒V型转折
这是一个不依赖LLM的、纯粹基于技术指标的策略。
"""

from datetime import datetime

class StrategyAnalyzer:
    """
    策略分析器类 V2 - 基于MACD柱状图的V型/倒V型转折。

    决策逻辑:
    - 买入信号 (BUY): MACD柱状图形成V型底部（谷），即趋势由跌转涨，且谷点最好在0轴以下。
    - 卖出信号 (SELL): MACD柱状图形成倒V型顶部（峰），即趋势由涨转跌，且峰点最好在0轴以上。
    - 持有信号 (HOLD): 其他所有情况。
    """
    
    def __init__(self, deepseek_client=None):
        """
        初始化策略分析器。
        
        Args:
            deepseek_client: 为了保持接口兼容性而保留，但在此版本中未使用。
        """
        # V2版本不使用deepseek_client，但保留参数以兼容接口
        print("🤖 初始化策略决策模块 V2 (基于MACD转折)")
    
    def analyze_market_strategy(self, price_data, signal_history, max_retries=2):
        """
    根据MACD柱状图的V/倒V转折分析市场并生成交易信号。
        
        Args:
            price_data (dict): 包含完整K线数据（DataFrame）的市场数据。
            signal_history (list): 历史信号记录（此策略中未使用）。
            max_retries (int): 为了接口兼容性保留，但未使用。
            
        Returns:
            dict: 包含交易决策的字典。
        """
        try:
            df = price_data.get('full_data')
            if df is None or len(df) < 3:
                return self._create_signal('HOLD', 'LOW', 'K线数据不足')

            # 获取最近三个周期的MACD柱状图值
            hist_current = df['macd_histogram'].iloc[-1]
            hist_prev = df['macd_histogram'].iloc[-2]
            hist_prev_2 = df['macd_histogram'].iloc[-3]

            current_price = price_data['price']
            reason = f"MACD柱状图趋势: P-2={hist_prev_2:.4f}, P-1={hist_prev:.4f}, P-0={hist_current:.4f}."

            # V型反转（买入信号）: P-2 > P-1 < P-0 且 P-1 < 0（谷底在0轴下方更佳）
            if hist_prev_2 > hist_prev and hist_prev < hist_current and hist_prev < 0:
                reason += " MACD柱状图形成V型底部，看涨。"
                return self._create_signal('BUY', 'HIGH', reason, current_price)

            # 倒V型反转（卖出信号）: P-2 < P-1 > P-0 且 P-1 > 0（峰顶在0轴上方更佳）
            elif hist_prev_2 < hist_prev and hist_prev > hist_current and hist_prev > 0:
                reason += " MACD柱状图形成倒V型顶部，看跌。"
                return self._create_signal('SELL', 'HIGH', reason, current_price)
            
            # 其他情况，持有
            else:
                reason += " 未出现明确的转折信号。"
                return self._create_signal('HOLD', 'MEDIUM', reason, current_price)

        except Exception as e:
            print(f"❌ V2策略分析失败: {e}")
            return self._create_signal('HOLD', 'LOW', f"策略分析异常: {e}", price_data.get('price', 0))

    def _create_signal(self, signal, confidence, reason, price=0):
        """
        创建一个标准格式的信号字典。
        
        说明：V2策略不负责计算止损/止盈价格，统一返回None，
        风险控制应由上层风控/交易执行模块决定（如ATR、账户风险敞口等）。
        """
        # 由上层风控来设置止损/止盈，这里不做任何价格计算
        stop_loss = None
        take_profit = None

        return {
            "signal": signal,
            "confidence": confidence,
            "reason": reason,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "timestamp": datetime.now().isoformat(),
            "is_fallback": False,
            "strategy_version": "v2_macd_turn"
        }
