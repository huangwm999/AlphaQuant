#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
技术分析模块
从 deepseekok3.py 重构分离出来的技术分析功能
"""

import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import json
import re


def calculate_technical_indicators(df):
    """计算技术指标 - 来自第一个策略"""
    try:
        # 移动平均线
        df['sma_5'] = df['close'].rolling(window=5, min_periods=1).mean()
        df['sma_20'] = df['close'].rolling(window=20, min_periods=1).mean()
        df['sma_50'] = df['close'].rolling(window=50, min_periods=1).mean()

        # 指数移动平均线
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']

        # 相对强弱指数 (RSI)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # 布林带
        df['bb_middle'] = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # 成交量均线
        df['volume_ma'] = df['volume'].rolling(20).mean()

        return df
    except Exception as e:
        print(f"计算技术指标时发生错误: {e}")
        return df


def get_support_resistance_levels(df, lookback=20):
    """计算支撑阻力位"""
    try:
        highs = df['high'].rolling(window=lookback).max()
        lows = df['low'].rolling(window=lookback).min()
        
        current_price = df['close'].iloc[-1]
        resistance = highs.iloc[-1]
        support = lows.iloc[-1]
        
        return {
            'resistance': resistance,
            'support': support,
            'current_price': current_price,
            'distance_to_resistance': (resistance - current_price) / current_price * 100,
            'distance_to_support': (current_price - support) / current_price * 100
        }
    except Exception as e:
        print(f"计算支撑阻力位失败: {e}")
        return {
            'resistance': df['close'].iloc[-1] * 1.02,
            'support': df['close'].iloc[-1] * 0.98,
            'current_price': df['close'].iloc[-1],
            'distance_to_resistance': 2.0,
            'distance_to_support': 2.0
        }


def get_market_trend(df):
    """分析市场趋势"""
    try:
        current_price = df['close'].iloc[-1]
        sma_20 = df['sma_20'].iloc[-1]
        sma_50 = df['sma_50'].iloc[-1]
        
        # 简单趋势判断
        if current_price > sma_20 > sma_50:
            trend = "上涨趋势"
            strength = "强"
        elif current_price < sma_20 < sma_50:
            trend = "下跌趋势"
            strength = "强"
        elif current_price > sma_20:
            trend = "震荡偏多"
            strength = "中"
        elif current_price < sma_20:
            trend = "震荡偏空"
            strength = "中"
        else:
            trend = "横盘整理"
            strength = "弱"
        
        return {
            'trend': trend,
            'strength': strength,
            'current_price': current_price,
            'sma_20': sma_20,
            'sma_50': sma_50
        }
    except Exception as e:
        print(f"分析市场趋势失败: {e}")
        return {
            'trend': "数据不足",
            'strength': "未知",
            'current_price': 0,
            'sma_20': 0,
            'sma_50': 0
        }


def generate_technical_analysis_text(price_data):
    """生成技术分析文本 - 纯数据"""
    if 'technical_data' not in price_data:
        return "技术指标数据不可用"

    tech = price_data['technical_data']
    historical_klines = price_data.get('historical_klines', [])
    historical_macd_signal = price_data.get('historical_macd_signal', [])
    
    # 纯数据展示
    kline_data = []
    macd_data = []
    
    if historical_klines and historical_macd_signal:
        recent_10 = min(10, len(historical_klines))
        for i in range(-recent_10, 0):
            kline = historical_klines[i]
            macd_signal = historical_macd_signal[i]
            time_str = kline['timestamp'].strftime('%H:%M') if isinstance(kline['timestamp'], pd.Timestamp) else str(kline['timestamp'])[-8:-3]
            kline_data.append(f"{time_str}:{kline['close']:.2f}")
            macd_data.append(f"{macd_signal:.4f}")

    analysis_text = f"""
K线收盘价: {', '.join(kline_data)}
MACD信号线: {', '.join(macd_data)}
当前MACD信号线: {tech.get('macd_signal', 0):.4f}
布林带上轨: {tech.get('bb_upper', 0):.2f}
布林带中轨: {tech.get('bb_middle', 0):.2f}  
布林带下轨: {tech.get('bb_lower', 0):.2f}
布林带位置: {tech.get('bb_position', 0):.1%}
    """
    return analysis_text


def get_sentiment_indicators():
    """获取市场情绪指标"""
    try:
        # 使用Alternative.me的恐慌贪婪指数
        response = requests.get('https://api.alternative.me/fng/?limit=10', timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('data') and len(data['data']) > 0:
                latest = data['data'][0]
                
                try:
                    # 获取数据时间
                    timestamp_str = latest.get('timestamp', '')
                    
                    # 处理时间字符串
                    # 检查是否已经是时间戳格式
                    if timestamp_str.isdigit():
                        data_time = datetime.fromtimestamp(int(timestamp_str))
                    else:
                        # 尝试解析其他时间格式
                        try:
                            data_time = datetime.strptime(timestamp_str, '%Y-%m-%d')
                        except:
                            # 如果无法解析，使用当前时间减去适当的延迟
                            data_time = datetime.now() - timedelta(hours=8)
                    
                    # 检查数据新鲜度
                    time_diff = datetime.now() - data_time
                    hours_old = time_diff.total_seconds() / 3600
                    
                    if hours_old > 48:  # 如果数据超过48小时
                        print(f"⚠️ 情绪数据较旧 ({hours_old:.1f}小时前)")
                        
                    fear_greed_index = int(latest.get('value', 50))
                    fear_greed_text = latest.get('value_classification', 'Neutral')
                    
                    # 计算净情绪（-1到1之间）
                    net_sentiment = (fear_greed_index - 50) / 50  # 归一化到-1到1
                    
                    return {
                        'fear_greed_index': fear_greed_index,
                        'fear_greed_text': fear_greed_text,
                        'net_sentiment': net_sentiment,
                        'data_time': data_time.strftime('%Y-%m-%d %H:%M'),
                        'hours_old': round(hours_old, 1),
                        'source': 'Alternative.me',
                        'status': 'success'
                    }
                    
                except Exception as parse_error:
                    print(f"解析恐慌贪婪指数数据失败: {parse_error}")
        
        # 如果API失败，尝试使用backup数据源或返回中性值
        print("恐慌贪婪指数API调用失败，使用中性值")
        return {
            'fear_greed_index': 50,
            'fear_greed_text': 'Neutral (API失败)',
            'net_sentiment': 0,
            'data_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'hours_old': 0,
            'source': 'Default',
            'status': 'fallback'
        }
        
    except Exception as e:
        print(f"获取情绪指标失败: {e}")
        return {
            'fear_greed_index': 50,
            'fear_greed_text': 'Neutral (错误)',
            'net_sentiment': 0,
            'data_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'hours_old': 0,
            'source': 'Error',
            'status': 'error'
        }


def calculate_integrated_trading_score(current_price, technical_data, sentiment_data=None, position_info=None):
    """
    集成买卖判别函数 - 基于deepseekok2.py的策略
    返回综合评分(-100到100，正数看多，负数看空)
    权重分配: 技术分析60% + 市场情绪30% + 风险管理10%
    """
    try:
        score = 0
        
        # 1. 技术分析主导 (权重60%)
        tech_score = 0
        
        # 1.1 趋势分析 - 均线排列 (最高权重)
        sma_5 = technical_data.get('sma_5', current_price)
        sma_20 = technical_data.get('sma_20', current_price)
        sma_50 = technical_data.get('sma_50', current_price)
        
        # 多头排列
        if sma_5 > sma_20 > sma_50:
            if current_price > sma_5:
                tech_score += 40  # 强势上涨趋势
            else:
                tech_score += 25  # 多头排列但价格回调
        # 空头排列
        elif sma_5 < sma_20 < sma_50:
            if current_price < sma_5:
                tech_score -= 40  # 强势下跌趋势
            else:
                tech_score -= 25  # 空头排列但价格反弹
        # 震荡整理
        else:
            if current_price > sma_20:
                tech_score += 10
            elif current_price < sma_20:
                tech_score -= 10
        
        # 1.2 RSI分析 (第二优先级)
        rsi = technical_data.get('rsi', 50)
        if 30 <= rsi <= 70:  # 健康范围，不做过度调整
            if rsi > 55:
                tech_score += 8   # 偏强势
            elif rsi < 45:
                tech_score -= 8   # 偏弱势
        else:
            if rsi > 70:
                tech_score -= 12  # 超买但不过度惩罚
            elif rsi < 30:
                tech_score += 12  # 超卖机会
        
        # 1.3 MACD分析 (第三优先级)
        macd = technical_data.get('macd', 0)
        macd_signal = technical_data.get('macd_signal', 0)
        macd_histogram = technical_data.get('macd_histogram', 0)
        
        if macd > macd_signal:
            tech_score += 15 if macd_histogram > 0 else 8
        else:
            tech_score -= 15 if macd_histogram < 0 else -8
        
        # 1.4 布林带分析 (最低优先级)
        bb_position = technical_data.get('bb_position', 0.5)
        if 0.2 <= bb_position <= 0.8:  # 正常波动区间
            if bb_position > 0.6:
                tech_score += 5
            elif bb_position < 0.4:
                tech_score -= 5
        else:
            if bb_position > 0.8:
                tech_score -= 8  # 上轨附近
            elif bb_position < 0.2:
                tech_score += 8  # 下轨附近
        
        score += tech_score * 0.6
        
        # 2. 市场情绪辅助 (权重30%)
        if sentiment_data:
            net_sentiment = sentiment_data.get('net_sentiment', 0)
            sentiment_score = 0
            
            # 情绪强度分析
            if abs(net_sentiment) > 0.2:
                sentiment_score = net_sentiment * 100  # 强情绪信号
            elif abs(net_sentiment) > 0.1:
                sentiment_score = net_sentiment * 60   # 中等情绪信号
            else:
                sentiment_score = net_sentiment * 30   # 弱情绪信号
            
            # 情绪与技术的协同性检查
            tech_direction = 1 if tech_score > 0 else -1 if tech_score < 0 else 0
            sentiment_direction = 1 if sentiment_score > 0 else -1 if sentiment_score < 0 else 0
            
            if tech_direction == sentiment_direction and tech_direction != 0:
                sentiment_score *= 1.2  # 同向增强
            elif tech_direction != sentiment_direction and tech_direction != 0:
                sentiment_score *= 0.6  # 背离时降低情绪权重
            
            score += sentiment_score * 0.3
        
        # 3. 风险管理 (权重10%)
        risk_score = 0
        if position_info:
            unrealized_pnl = position_info.get('unrealized_pnl', 0)
            position_side = position_info.get('side', '')
            
            # 持仓盈亏状况调整
            if unrealized_pnl > 0:
                # 盈利时适度保守
                if position_side == 'long' and score > 20:
                    risk_score -= 5
                elif position_side == 'short' and score < -20:
                    risk_score += 5
            elif unrealized_pnl < -50:  # 较大亏损时
                # 亏损时止损优先
                if position_side == 'long' and score < -10:
                    risk_score -= 10  # 加强止损信号
                elif position_side == 'short' and score > 10:
                    risk_score += 10
        
        score += risk_score * 0.1
        
        # 确保评分在合理范围内
        score = max(-100, min(100, score))
        
        return round(score, 1)
        
    except Exception as e:
        print(f"集成决策函数错误: {e}")
        return 0