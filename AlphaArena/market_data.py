#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
市场数据获取模块
从 deepseekok3.py 重构分离出来的数据获取功能
"""

import ccxt
import pandas as pd
from datetime import datetime, timedelta
from data_manager import DataManager

# 全局变量
data_manager = DataManager()


def get_recent_trades(limit=5):
    """获取最近的交易记录"""
    try:
        trade_history = data_manager.get_trade_history()
        if not trade_history:
            return []
        
        # 按时间倒序排列，获取最近的记录
        sorted_trades = sorted(trade_history, key=lambda x: x.get('timestamp', ''), reverse=True)
        return sorted_trades[:limit]
        
    except Exception as e:
        print(f"获取交易历史失败: {e}")
        return []


def get_recent_ai_analysis(limit=5):
    """获取最近的AI分析记录"""
    try:
        ai_history = data_manager.get_ai_analysis_history()
        if not ai_history:
            return []
        
        # 按时间倒序排列，获取最近的记录
        sorted_analysis = sorted(ai_history, key=lambda x: x.get('timestamp', ''), reverse=True)
        return sorted_analysis[:limit]
        
    except Exception as e:
        print(f"获取AI分析历史失败: {e}")
        return []


def get_btc_ohlcv_base(exchange, config):
    """共享的核心K线数据获取和技术指标计算函数"""
    try:
        # 获取K线数据
        ohlcv = exchange.fetch_ohlcv(config['symbol'], config['timeframe'],
                                     limit=config['data_points'])

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        # 将UTC时间转换为北京时间（当前系统时间）
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)

        return df
    except Exception as e:
        print(f"获取基础K线数据失败: {e}")
        return None


def get_btc_ohlcv_enhanced(exchange, config, calculate_technical_indicators, get_support_resistance_levels, get_market_trend):
    """获取增强的OHLCV数据（包含支撑阻力位和市场趋势分析）"""
    try:
        # 使用基础函数获取数据
        df = get_btc_ohlcv_base(exchange, config)
        if df is None or df.empty:
            return None
        
        # 计算技术指标
        df = calculate_technical_indicators(df)
        
        current_data = df.iloc[-1]
        previous_data = df.iloc[-2]

        # 获取技术分析数据
        trend_analysis = get_market_trend(df)
        levels_analysis = get_support_resistance_levels(df)

        # 获取历史50根K线数据和MACD信号线数据
        historical_data_count = min(50, len(df))
        historical_klines = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].tail(historical_data_count).to_dict('records')
        historical_macd_signal = df['macd_signal'].tail(historical_data_count).tolist()

        return {
            'price': current_data['close'],
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'high': current_data['high'],
            'low': current_data['low'],
            'volume': current_data['volume'],
            'timeframe': config['timeframe'],
            'price_change': ((current_data['close'] - previous_data['close']) / previous_data['close']) * 100,
            'kline_data': df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].tail(10).to_dict('records'),
            # 专注MACD信号线和布林带的技术数据
            'technical_data': {
                'macd': current_data.get('macd', 0),
                'macd_signal': current_data.get('macd_signal', 0),
                'macd_histogram': current_data.get('macd_histogram', 0),
                'bb_upper': current_data.get('bb_upper', 0),
                'bb_middle': current_data.get('bb_middle', 0),
                'bb_lower': current_data.get('bb_lower', 0),
                'bb_position': current_data.get('bb_position', 0)
            },
            # 添加历史100根K线数据和MACD信号线数据
            'historical_klines': historical_klines,
            'historical_macd_signal': historical_macd_signal,
            'trend_analysis': trend_analysis,
            'levels_analysis': levels_analysis,
            'full_data': df
        }
    except Exception as e:
        print(f"获取增强K线数据失败: {e}")
        return None


def get_current_position(exchange, config):
    """获取当前持仓情况 - OKX版本"""
    try:
        positions = exchange.fetch_positions([config['symbol']])
        
        for position in positions:
            if position['symbol'] == config['symbol']:
                contracts = float(position['contracts']) if position['contracts'] else 0
                
                if contracts > 0:
                    return {
                        'side': position['side'],
                        'size': contracts,
                        'entry_price': float(position['entryPrice']) if position['entryPrice'] else 0,
                        'unrealized_pnl': float(position['unrealizedPnl']) if position['unrealizedPnl'] else 0,
                        'percentage': float(position['percentage']) if position['percentage'] else 0,
                    }
        
        return None  # 没有持仓
        
    except Exception as e:
        print(f"获取持仓信息失败: {e}")
        return None


def get_btc_ohlcv_for_web(exchange, config, calculate_technical_indicators, get_sentiment_indicators, calculate_integrated_trading_score):
    """专门为web界面提供的K线数据和技术指标 - 用于Web API"""
    try:
        # 使用共享的基础数据获取函数
        df = get_btc_ohlcv_base(exchange, config)
        if df is None:
            return None

        # 计算技术指标
        df = calculate_technical_indicators(df)

        # 获取情绪数据
        sentiment_data = get_sentiment_indicators()

        # 计算每个点的交易决策score
        scores = []
        for i in range(len(df)):
            try:
                # 准备技术指标数据
                technical_data = {
                    'sma_5': df['sma_5'].iloc[i],
                    'sma_20': df['sma_20'].iloc[i], 
                    'sma_50': df['sma_50'].iloc[i],
                    'rsi': df['rsi'].iloc[i],
                    'macd': df['macd'].iloc[i],
                    'macd_signal': df['macd_signal'].iloc[i],
                    'macd_histogram': df['macd_histogram'].iloc[i],
                    'bb_position': df['bb_position'].iloc[i]
                }
                
                # 使用与deepseekok2.py一致的评分算法
                score = calculate_integrated_trading_score(
                    current_price=df['close'].iloc[i],
                    technical_data=technical_data,
                    sentiment_data=sentiment_data
                )
                
                scores.append(score)
                
            except Exception as e:
                print(f"计算第{i}个点的score失败: {e}")
                scores.append(0)
        
        df['score'] = scores

        return {
            'dataframe': df,
            'sentiment': sentiment_data,
            'current_price': float(df['close'].iloc[-1]),
            'timeframe': config['timeframe']
        }
        
    except Exception as e:
        print(f"获取Web端K线数据失败: {e}")
        return None