#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测模块 (轻量版)
根据当前启用的策略 (strategy_decision.py -> v2) 对过去 N 天的 3 分钟级别数据做逐根回测。
只做多头示例：
- BUY 信号：若当前无持仓，则开多，记录 entry_price
- SELL 信号：若当前有持仓，则平多，计算 pnl = (close - entry_price)
忽略手续费与滑点。收益以 USDT 计 (假设 1 合约名义价值 = 1 * price)。
返回：曲线 + 信号 + 统计
"""

from datetime import datetime, timedelta
import ccxt
import pandas as pd
from typing import Dict, Any

from technical_analysis import calculate_technical_indicators
from strategy_decision import StrategyInterface
from deepseekok3 import exchange, TRADE_CONFIG, deepseek_client


def fetch_historical(exchange: ccxt.Exchange, symbol: str, timeframe: str, since: int, limit: int = 1000):
    """安全获取K线数据，自动截断"""
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)
    return df


def run_backtest(days: int = 2, interval: str = '3m') -> Dict[str, Any]:
    """
    运行回测。
    Args:
        days: 回测天数 (默认 2 天)
        interval: K线级别 (默认 3m)
    Returns:
        dict: { labels, prices, decisions, trades, equity_curve, summary }
    """
    symbol = TRADE_CONFIG['symbol']
    end_ts = datetime.utcnow()
    start_ts = end_ts - timedelta(days=days)
    since_ms = int(start_ts.timestamp() * 1000)
    candles_needed = int(days * 24 * 60 / 3) + 10  # +10 余量

    df = fetch_historical(exchange, symbol, interval, since=since_ms, limit=candles_needed)
    if df.empty:
        return { 'error': '无法获取历史数据' }

    # 计算技术指标
    df = calculate_technical_indicators(df)

    # 初始化策略接口
    strategy = StrategyInterface(deepseek_client)

    labels = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M').tolist()
    prices = df['close'].tolist()
    decisions = []  # 1 buy, -1 sell, 0 hold
    trades = []     # 每次信号记录
    equity_curve = []

    position_open = False
    entry_price = 0.0
    cumulative_pnl = 0.0
    win_trades = 0
    closed_trades = 0

    # 回测逐根
    for i in range(len(df)):
        # 至少要有3根柱状图才能生成MACD转折判定
        if i < 3:
            decisions.append(0)
            equity_curve.append(cumulative_pnl)
            continue

        partial_df = df.iloc[:i+1].copy()  # 截止当前
        price_data = {
            'price': partial_df['close'].iloc[-1],
            'full_data': partial_df
        }
        signal_data = strategy.analyze_market_strategy(price_data, signal_history=[], max_retries=1)
        signal = signal_data['signal']

        action_flag = 0
        reason = signal_data.get('reason', '')
        ts = labels[i]
        current_price = price_data['price']

        if signal == 'BUY' and not position_open:
            position_open = True
            entry_price = current_price
            action_flag = 1
            trades.append({
                'timestamp': ts,
                'signal': 'BUY',
                'price': current_price,
                'pnl': None,
                'reason': reason
            })
        elif signal == 'SELL' and position_open:
            # 平仓
            pnl = current_price - entry_price
            cumulative_pnl += pnl
            position_open = False
            action_flag = -1
            closed_trades += 1
            if pnl > 0:
                win_trades += 1
            trades.append({
                'timestamp': ts,
                'signal': 'SELL',
                'price': current_price,
                'pnl': round(pnl, 2),
                'reason': reason
            })
        else:
            action_flag = 0

        decisions.append(action_flag)
        equity_curve.append(round(cumulative_pnl, 2))

    total_trades = len(trades)
    win_rate = (win_trades / closed_trades * 100) if closed_trades > 0 else 0.0
    avg_pnl = (cumulative_pnl / closed_trades) if closed_trades > 0 else 0.0

    summary = {
        'days': days,
        'interval': interval,
        'data_points': len(df),
        'total_signals': total_trades,
        'closed_trades': closed_trades,
        'win_rate': round(win_rate, 2),
        'total_pnl': round(cumulative_pnl, 2),
        'avg_pnl_per_trade': round(avg_pnl, 2)
    }

    return {
        'labels': labels,
        'prices': prices,
        'decisions': decisions,
        'equity_curve': equity_curve,
        'trades': trades,
        'summary': summary
    }


if __name__ == '__main__':
    result = run_backtest(days=2, interval='3m')
    print('回测统计:', result.get('summary'))
    print('信号数:', len(result.get('trades', [])))
