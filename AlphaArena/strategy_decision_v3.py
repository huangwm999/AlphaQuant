#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略决策模块 V3 - 混合策略：布林带下轨突破买入 + MACD倒V卖出
这是一个不依赖LLM的、混合技术指标策略。
"""

from datetime import datetime

class StrategyAnalyzer:
    """
    策略分析器类 V3 - 混合策略。

    决策逻辑:
    - 买入信号 (BUY): 
      1. 前一根K线收盘价 >= 布林带下轨，当前K线收盘价 < 布林带下轨（向下突破下轨）
      2. MACD前3个点呈下降趋势，即 P-3 > P-2 > P-1
    - 卖出信号 (SELL): 
      1. MACD柱状图形成倒V型顶部（峰），即 P-3 < P-2 > P-1
      2. 同时前10个点在布林带中的平均位置 > 0.6（表示价格位于上部区域）
    - 持有信号 (HOLD): 其他所有情况。
    
    策略理论：
    - 买入：价格突破布林带下轨 + MACD持续下降，表示超卖且下跌动能强，基于均值回归预期反弹
    - 卖出：MACD柱状图倒V型 + 价格持续在布林带上部，表示上涨动能衰减且价格已高，趋势可能反转
    """
    
    def __init__(self, deepseek_client=None):
        """
        初始化策略分析器。
        
        Args:
            deepseek_client: 为了保持接口兼容性而保留，但在此版本中未使用。
        """
        # V3版本不使用deepseek_client，但保留参数以兼容接口
        print("🤖 初始化策略决策模块 V3 (布林带下轨买入 + MACD倒V卖出)")
    
    def analyze_market_strategy(self, price_data, signal_history, max_retries=2):
        """
        根据布林带下轨突破（买入）和MACD倒V型+布林带位置（卖出）分析市场并生成交易信号。
        
        Args:
            price_data (dict): 包含完整K线数据（DataFrame）的市场数据。
            signal_history (list): 历史信号记录（此策略中未使用）。
            max_retries (int): 为了接口兼容性保留，但未使用。
            
        Returns:
            dict: 包含交易决策的字典。
        """
        try:
            df = price_data.get('full_data')
            if df is None or len(df) < 13:
                return self._create_signal('HOLD', 'LOW', 'K线数据不足（需要至少13根K线）')

            # 获取当前和前一根K线的收盘价和布林带值
            close_current = df['close'].iloc[-1]
            close_prev = df['close'].iloc[-2]
            
            bb_lower_current = df['bb_lower'].iloc[-1]
            bb_lower_prev = df['bb_lower'].iloc[-2]
            bb_middle_current = df['bb_middle'].iloc[-1]

            # 获取最近四个周期的MACD柱状图值（用于检测倒V和下降趋势）
            hist_prev_3 = df['macd_histogram'].iloc[-4]  # P-3
            hist_prev_2 = df['macd_histogram'].iloc[-3]  # P-2
            hist_prev = df['macd_histogram'].iloc[-2]     # P-1
            # 注意：不使用当前柱 hist_current，避免look-ahead bias

            # 计算前10个点（不包括当前点）在布林带中的位置平均值
            # bb_position 定义：(close - bb_lower) / (bb_upper - bb_lower)
            # 值越接近1表示越靠近上轨，越接近0表示越靠近下轨
            bb_positions = df['bb_position'].iloc[-11:-1]  # 前10个点
            avg_bb_position = bb_positions.mean()

            current_price = price_data['price']
            
            # 买入信号：前一根高于或等于下轨，当前根跌破下轨 + MACD前3个点呈下降趋势
            # MACD下降趋势：P-3 > P-2 > P-1
            if (close_prev >= bb_lower_prev and close_current < bb_lower_current
                and hist_prev_3 > hist_prev_2 and hist_prev_2 > hist_prev):
                reason = f"价格: 前={close_prev:.2f}, 当前={close_current:.2f}; "
                reason += f"布林带下轨: 前={bb_lower_prev:.2f}, 当前={bb_lower_current:.2f}. "
                reason += f"MACD柱状图: P-3={hist_prev_3:.4f} > P-2={hist_prev_2:.4f} > P-1={hist_prev:.4f} (下降趋势). "
                reason += "价格向下突破布林带下轨且MACD呈下降趋势，预期反弹。"
                return self._create_signal('BUY', 'HIGH', reason, current_price, bb_middle_current)

            # 卖出信号：MACD柱状图形成倒V型 + 前10个点平均位置在上部区域（>0.6）
            # bb_position > 0.6 表示价格接近布林带上半部分
            elif (hist_prev_3 < hist_prev_2 and hist_prev_2 > hist_prev 
                  and avg_bb_position > 0.6):
                reason = f"MACD柱状图: P-3={hist_prev_3:.4f}, P-2={hist_prev_2:.4f}, P-1={hist_prev:.4f}. "
                reason += f"前10个点布林带平均位置={avg_bb_position:.3f} (>0.6表示靠近上轨). "
                reason += "MACD柱状图形成倒V型顶部且价格位于布林带上部，上涨动能衰减，看跌。"
                return self._create_signal('SELL', 'HIGH', reason, current_price)
            
            # 其他情况，持有
            else:
                reason = f"价格={close_current:.2f}, 布林带下轨={bb_lower_current:.2f}; "
                reason += f"MACD: P-3={hist_prev_3:.4f}, P-2={hist_prev_2:.4f}, P-1={hist_prev:.4f}; "
                reason += f"前10点布林带平均位置={avg_bb_position:.3f}. "
                reason += "未出现买入或卖出信号。"
                return self._create_signal('HOLD', 'MEDIUM', reason, current_price)

        except Exception as e:
            print(f"❌ V3策略分析失败: {e}")
            return self._create_signal('HOLD', 'LOW', f"策略分析异常: {e}", price_data.get('price', 0))

    def _create_signal(self, signal, confidence, reason, price=0, target_price=None):
        """
        创建一个标准格式的信号字典。
        
        Args:
            signal: 交易信号 (BUY/SELL/HOLD)
            confidence: 信号置信度 (HIGH/MEDIUM/LOW)
            reason: 信号原因说明
            price: 当前价格
            target_price: 目标价格（布林带中轨，用于参考）
        
        说明：V3策略不负责计算止损/止盈价格，统一返回None，
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
            "strategy_version": "v3_bb_lower_macd_sell",
            "target_price": target_price  # 可选：布林带中轨作为目标价参考
        }

