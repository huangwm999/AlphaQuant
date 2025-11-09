#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略决策模块 V4 - 基于MACD Signal线V型/倒V型转折 + 布林带中轨过滤
这是一个不依赖LLM的、纯粹基于技术指标的策略。
增加了布林带中轨穿越判断，避免在价格穿越中轨时产生错误信号。
"""

from datetime import datetime

class StrategyAnalyzer:
    """
    策略分析器类 V4 - 基于MACD Signal线的V型/倒V型转折 + 布林带中轨过滤。

    决策逻辑:
    - 买入信号 (BUY): 
      1. MACD Signal线形成V型底部（谷），即 P-3 > P-2 < P-1
      2. 价格未在向上穿越中轨（避免前一个价格低于中轨而当前高于中轨，或前一个和当前都高于中轨）
    - 卖出信号 (SELL): 
      1. MACD Signal线形成倒V型顶部（峰），即 P-3 < P-2 > P-1
      2. 价格未在向下穿越中轨（避免前一个价格高于中轨而当前低于中轨，或前一个和当前都低于中轨）
    - 持有信号 (HOLD): 其他所有情况。
    """
    
    def __init__(self, deepseek_client=None):
        """
        初始化策略分析器。
        
        Args:
            deepseek_client: 为了保持接口兼容性而保留，但在此版本中未使用。
        """
        # V4版本不使用deepseek_client，但保留参数以兼容接口
        print("🤖 初始化策略决策模块 V4 (基于MACD转折 + 布林带中轨过滤)")
    
    def analyze_market_strategy(self, price_data, signal_history, max_retries=2):
        """
        根据MACD柱状图的V/倒V转折 + 布林带中轨过滤分析市场并生成交易信号。
        
        Args:
            price_data (dict): 包含完整K线数据（DataFrame）的市场数据。
            signal_history (list): 历史信号记录（此策略中未使用）。
            max_retries (int): 为了接口兼容性保留，但未使用。
            
        Returns:
            dict: 包含交易决策的字典。
        """
        try:
            df = price_data.get('full_data')
            if df is None or len(df) < 4:
                return self._create_signal('HOLD', 'LOW', 'K线数据不足（需要至少4根K线）')

            # 获取最近四个周期的MACD Signal线值
            # 检查P-3, P-2, P-1是否形成V/倒V型，在当前P-0时刻触发信号
            signal_prev_3 = df['macd_signal'].iloc[-4]  # P-3 (i-3)
            signal_prev_2 = df['macd_signal'].iloc[-3]  # P-2 (i-2) <- V型的谷底或倒V的峰顶
            signal_prev_1 = df['macd_signal'].iloc[-2]  # P-1 (i-1)
            signal_current = df['macd_signal'].iloc[-1]  # P-0 (当前, i) <- 此时触发信号

            # 获取布林带中轨和价格信息
            current_price = price_data['price']
            prev_price = df['close'].iloc[-2]  # P-1的价格
            current_bb_middle = df['bb_middle'].iloc[-1]  # 当前中轨
            prev_bb_middle = df['bb_middle'].iloc[-2]  # 前一个中轨
            
            reason = f"MACD Signal线趋势: P-3={signal_prev_3:.4f}, P-2={signal_prev_2:.4f}, P-1={signal_prev_1:.4f}, P-0={signal_current:.4f}."
            reason += f" 价格: 当前={current_price:.2f}, 前一个={prev_price:.2f}; 中轨: 当前={current_bb_middle:.2f}, 前一个={prev_bb_middle:.2f}."

            # V型反转（买入信号）: P-3 > P-2 < P-1
            if signal_prev_3 > signal_prev_2 and signal_prev_2 < signal_prev_1:
                # 检查布林带中轨过滤条件：买入时避免向上穿越中轨
                # 条件1: 前一个价格低于中轨，当前价格高于中轨（正在向上穿越）
                # 条件2: 前一个和当前都高于中轨（已经在中轨上方）
                if (prev_price < prev_bb_middle and current_price > current_bb_middle):
                    reason += " MACD Signal线形成V型底部，但价格正在向上穿越中轨，过滤买入信号。"
                    return self._create_signal('HOLD', 'MEDIUM', reason, current_price)
                elif (prev_price > prev_bb_middle and current_price > current_bb_middle):
                    reason += " MACD Signal线形成V型底部，但价格已在中轨上方，过滤买入信号。"
                    return self._create_signal('HOLD', 'MEDIUM', reason, current_price)
                else:
                    reason += " MACD Signal线形成V型底部，价格位置合适，看涨。"
                    return self._create_signal('BUY', 'HIGH', reason, current_price)

            # 倒V型反转（卖出信号）: P-3 < P-2 > P-1
            elif signal_prev_3 < signal_prev_2 and signal_prev_2 > signal_prev_1:
                # 检查布林带中轨过滤条件：卖出时避免向下穿越中轨
                # 条件1: 前一个价格高于中轨，当前价格低于中轨（正在向下穿越）
                # 条件2: 前一个和当前都低于中轨（已经在中轨下方）
                if (prev_price > prev_bb_middle and current_price < current_bb_middle):
                    reason += " MACD Signal线形成倒V型顶部，但价格正在向下穿越中轨，过滤卖出信号。"
                    return self._create_signal('HOLD', 'MEDIUM', reason, current_price)
                elif (prev_price < prev_bb_middle and current_price < current_bb_middle):
                    reason += " MACD Signal线形成倒V型顶部，但价格已在中轨下方，过滤卖出信号。"
                    return self._create_signal('HOLD', 'MEDIUM', reason, current_price)
                else:
                    reason += " MACD Signal线形成倒V型顶部，价格位置合适，看跌。"
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
        
        说明：V4策略不负责计算止损/止盈价格，统一返回None，
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
            "strategy_version": "v4_macd_turn_bb_filter"
        }
