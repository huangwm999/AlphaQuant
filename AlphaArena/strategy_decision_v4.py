#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略决策模块 V4 - MACD Signal线V型转折 + 布林带突破
这是一个不依赖LLM的、纯粹基于技术指标的策略。

V4相对V2新增：布林带下轨突破 + MACD Signal线连续快速下行的买入条件（捕捉超卖反弹）。
"""

from datetime import datetime

class StrategyAnalyzer:
    """
    策略分析器类 V4 - 基于MACD Signal线的V型/倒V型转折 + 布林带突破。

        决策逻辑:
        买入信号 (BUY):
            1. MACD Signal线形成V型底部（谷），即 P-3 > P-2 < P-1，且谷点在0轴以下（与V2一致）
            2. 价格触及/跌破布林带下轨 + MACD Signal线连续快速下行（基于自适应阈值），用于捕捉超卖后的技术性反弹
    
    卖出信号 (SELL):
      - MACD Signal线形成倒V型顶部（峰），即 P-3 < P-2 > P-1，且峰点在0轴以上
    
    持有信号 (HOLD): 其他所有情况
    """
    
    def __init__(self, deepseek_client=None):
        """
        初始化策略分析器。
        
        Args:
            deepseek_client: 为了保持接口兼容性而保留，但在此版本中未使用。
        """
        # V4版本不使用deepseek_client，但保留参数以兼容接口
        print("🤖 初始化策略决策模块 V4 (MACD转折 + 布林带突破)")
    
    def analyze_market_strategy(self, price_data, signal_history, max_retries=2):
        """
        根据MACD Signal线的V/倒V转折 + 布林带突破分析市场并生成交易信号。
        
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
            signal_prev_3 = df['macd_signal'].iloc[-4]  # P-3 (i-3)
            signal_prev_2 = df['macd_signal'].iloc[-3]  # P-2 (i-2)
            signal_prev_1 = df['macd_signal'].iloc[-2]  # P-1 (i-1)
            signal_current = df['macd_signal'].iloc[-1]  # P-0 (当前, i)

            current_price = price_data['price']
            close_current = df['close'].iloc[-1]
            bb_lower = df['bb_lower'].iloc[-1]
            
            reason = f"MACD Signal线趋势: P-3={signal_prev_3:.4f}, P-2={signal_prev_2:.4f}, P-1={signal_prev_1:.4f}, P-0={signal_current:.4f}. "

            # 买入条件1: V型反转 - P-3 > P-2 < P-1 且 P-2 < 0
            buy_v_pattern = (signal_prev_3 > signal_prev_2 and 
                            signal_prev_2 < signal_prev_1 and 
                            signal_prev_2 < 0)
            
            # 买入条件2（新增）：价格触及/跌破布林带下轨 + MACD Signal线出现连续快速下行（捕捉过度下跌后的可能反弹）
            # 逻辑：
            #   1) close_current <= bb_lower （价格进入超卖带）
            #   2) MACD Signal呈连续下降：signal_prev_2 > signal_prev_1 > signal_current
            #   3) 两段下降幅度均超过动态阈值 decline_threshold
            # 动态阈值：取当前MACD Signal线绝对值的10% 与 0.005 之间的较大者，避免过小噪声
            base_scale = abs(signal_current)
            decline_threshold = max(0.005, base_scale * 0.10)
            macd_decline_1 = signal_prev_2 - signal_prev_1  # 第一段下降幅度（正值表示下降）
            macd_decline_2 = signal_prev_1 - signal_current  # 第二段下降幅度
            buy_bollinger_macd = (
                close_current <= bb_lower and
                signal_prev_2 > signal_prev_1 > signal_current and
                macd_decline_1 >= decline_threshold and
                macd_decline_2 >= decline_threshold
            )
            # 调试信息加入 reason，方便回测与实时日志查看触发情况
            reason += (
                f"[调试] 布林下轨={bb_lower:.2f}, 收盘价={close_current:.2f}, "
                f"decline1={macd_decline_1:.5f}, decline2={macd_decline_2:.5f}, 阈值={decline_threshold:.5f}. "
            )
            
            # 满足任一买入条件
            if buy_v_pattern:
                reason += f"MACD Signal线形成V型底部，看涨。"
                return self._create_signal('BUY', 'HIGH', reason, current_price)
            
            elif buy_bollinger_macd:
                reason += (
                    f"价格触及/跌破布林带下轨 (close={close_current:.2f} <= lower={bb_lower:.2f}) 且 MACD Signal连续快速下行 "
                    f"(P-2→P-1: {macd_decline_1:.5f}, P-1→P-0: {macd_decline_2:.5f} ≥ 阈值 {decline_threshold:.5f})，捕捉潜在技术性反弹。"
                )
                return self._create_signal('BUY', 'MEDIUM', reason, current_price)

            # 卖出信号: 倒V型反转 - P-3 < P-2 > P-1 且 P-2 > 0
            elif signal_prev_3 < signal_prev_2 and signal_prev_2 > signal_prev_1 and signal_prev_2 > 0:
                reason += "MACD Signal线形成倒V型顶部，看跌。"
                return self._create_signal('SELL', 'HIGH', reason, current_price)
            
            # 其他情况，持有
            else:
                reason += "未出现明确的转折或突破信号。"
                return self._create_signal('HOLD', 'MEDIUM', reason, current_price)

        except Exception as e:
            print(f"❌ V4策略分析失败: {e}")
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
            "strategy_version": "v4_macd_bollinger"
        }
