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

from technical_analysis import calculate_technical_indicators, get_sentiment_indicators, calculate_integrated_trading_score
from strategy_decision import StrategyInterface
from deepseekok3 import exchange, TRADE_CONFIG, deepseek_client


def fetch_historical(exchange: ccxt.Exchange, symbol: str, timeframe: str, since: int, limit: int = 1000):
    """按since获取K线（UTC毫秒），并转换为上海时区"""
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)
    return df

def fetch_recent(exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int):
    """按数量获取最近N根K线（与技术指标分析一致），并转换为上海时区"""
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)
    return df

def interval_to_minutes(interval: str) -> int:
    """将'3m','15m','1h','4h','1d'等周期转换为分钟数"""
    interval = interval.strip().lower()
    if interval.endswith('m'):
        return int(interval[:-1])
    if interval.endswith('h'):
        return int(interval[:-1]) * 60
    if interval.endswith('d'):
        return int(interval[:-1]) * 60 * 24
    # 默认按分钟处理
    return max(int(''.join(ch for ch in interval if ch.isdigit()) or '3'), 1)


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
    # 与技术指标分析对齐：直接按数量取最近N根，而不是用since
    minutes = interval_to_minutes(interval)
    per_day = int(24 * 60 / minutes)
    candles_needed = days * per_day + 10  # +10 余量

    df = fetch_recent(exchange, symbol, interval, limit=candles_needed)
    if df.empty:
        return { 'error': '无法获取历史数据' }

    # 计算技术指标
    df = calculate_technical_indicators(df)

    # 初始化策略接口
    strategy = StrategyInterface(deepseek_client)

    labels_full = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M').tolist()
    labels_hm = df['timestamp'].dt.strftime('%H:%M').tolist()
    prices = df['close'].tolist()
    decisions = []  # 1 buy, -1 sell, 0 hold
    trades = []     # 每次信号记录
    equity_curve = []

    # 交易参数
    fee_rate = 0.0005  # 0.05%
    fixed_usd = 100.0
    first_price = float(df['close'].iloc[0])
    fixed_qty = fixed_usd / first_price  # 固定BTC数量（根据首根K线价格确定）

    # 仓位状态
    position_side = None  # None / 'long' / 'short'
    entry_price = 0.0
    entry_fee = 0.0
    cumulative_pnl = 0.0          # 净盈亏 (扣除手续费)
    gross_pnl_total = 0.0         # 毛盈亏 (未扣手续费)
    total_fees = 0.0              # 手续费累计
    win_trades = 0
    closed_trades = 0

    def order_fee(price: float, qty: float) -> float:
        return price * qty * fee_rate

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
        ts = labels_full[i]
        current_price = price_data['price']

        if signal == 'BUY':
            if position_side is None:
                action_flag = 1
                # 开多
                entry_price = current_price
                entry_fee = order_fee(current_price, fixed_qty)
                total_fees += entry_fee
                position_side = 'long'
                trades.append({
                    'timestamp': ts,
                    'action': 'OPEN_LONG',
                    'qty': round(fixed_qty, 6),
                    'entry_price': round(entry_price, 2),
                    'fee_entry': round(entry_fee, 4),
                    'pnl': None,
                    'reason': reason
                })
            elif position_side == 'short':
                action_flag = 1  # 方向翻转：空 -> 多，记为 BUY
                # 先平空
                exit_fee = order_fee(current_price, fixed_qty)
                total_fees += exit_fee
                pnl_gross = (entry_price - current_price) * fixed_qty
                pnl_net = pnl_gross - (entry_fee + exit_fee)
                gross_pnl_total += pnl_gross
                cumulative_pnl += pnl_net
                closed_trades += 1
                if pnl_net > 0:
                    win_trades += 1
                trades.append({
                    'timestamp': ts,
                    'action': 'CLOSE_SHORT',
                    'qty': round(fixed_qty, 6),
                    'entry_price': round(entry_price, 2),
                    'close_price': round(current_price, 2),
                    'fee_entry': round(entry_fee, 4),
                    'fee_exit': round(exit_fee, 4),
                    'pnl': round(pnl_net, 2),
                    'reason': reason
                })
                # 再开多
                entry_price = current_price
                entry_fee = order_fee(current_price, fixed_qty)
                total_fees += entry_fee
                position_side = 'long'
                trades.append({
                    'timestamp': ts,
                    'action': 'OPEN_LONG',
                    'qty': round(fixed_qty, 6),
                    'entry_price': round(entry_price, 2),
                    'fee_entry': round(entry_fee, 4),
                    'pnl': None,
                    'reason': reason
                })
            else:
                # 已经是long，重复BUY信号 -> 不增仓，决策记为 HOLD
                action_flag = 0
        elif signal == 'SELL':
            if position_side is None:
                action_flag = -1
                # 开空
                entry_price = current_price
                entry_fee = order_fee(current_price, fixed_qty)
                total_fees += entry_fee
                position_side = 'short'
                trades.append({
                    'timestamp': ts,
                    'action': 'OPEN_SHORT',
                    'qty': round(fixed_qty, 6),
                    'entry_price': round(entry_price, 2),
                    'fee_entry': round(entry_fee, 4),
                    'pnl': None,
                    'reason': reason
                })
            elif position_side == 'long':
                action_flag = -1  # 方向翻转：多 -> 空，记为 SELL
                # 先平多
                exit_fee = order_fee(current_price, fixed_qty)
                total_fees += exit_fee
                pnl_gross = (current_price - entry_price) * fixed_qty
                pnl_net = pnl_gross - (entry_fee + exit_fee)
                gross_pnl_total += pnl_gross
                cumulative_pnl += pnl_net
                closed_trades += 1
                if pnl_net > 0:
                    win_trades += 1
                trades.append({
                    'timestamp': ts,
                    'action': 'CLOSE_LONG',
                    'qty': round(fixed_qty, 6),
                    'entry_price': round(entry_price, 2),
                    'close_price': round(current_price, 2),
                    'fee_entry': round(entry_fee, 4),
                    'fee_exit': round(exit_fee, 4),
                    'pnl': round(pnl_net, 2),
                    'reason': reason
                })
                # 再开空
                entry_price = current_price
                entry_fee = order_fee(current_price, fixed_qty)
                total_fees += entry_fee
                position_side = 'short'
                trades.append({
                    'timestamp': ts,
                    'action': 'OPEN_SHORT',
                    'qty': round(fixed_qty, 6),
                    'entry_price': round(entry_price, 2),
                    'fee_entry': round(entry_fee, 4),
                    'pnl': None,
                    'reason': reason
                })
            else:
                # 已经是short，重复SELL信号 -> 不增仓，决策记为 HOLD
                action_flag = 0
        else:
            action_flag = 0

        decisions.append(action_flag)
        equity_curve.append(round(cumulative_pnl, 2))

    # 收尾：最后一根后如果还有持仓，按最后价格平仓
    if position_side is not None:
        last_price = float(df['close'].iloc[-1])
        ts_last = labels_full[-1]
        exit_fee = order_fee(last_price, fixed_qty)
        total_fees += exit_fee
        if position_side == 'long':
            pnl_gross = (last_price - entry_price) * fixed_qty
            close_action = 'CLOSE_LONG'
        else:
            pnl_gross = (entry_price - last_price) * fixed_qty
            close_action = 'CLOSE_SHORT'
        pnl_net = pnl_gross - (entry_fee + exit_fee)
        gross_pnl_total += pnl_gross
        cumulative_pnl += pnl_net
        closed_trades += 1
        if pnl_net > 0:
            win_trades += 1
        trades.append({
            'timestamp': ts_last,
            'action': close_action,
            'qty': round(fixed_qty, 6),
            'entry_price': round(entry_price, 2),
            'close_price': round(last_price, 2),
            'fee_entry': round(entry_fee, 4),
            'fee_exit': round(exit_fee, 4),
            'pnl': round(pnl_net, 2),
            'reason': 'FINAL_CLOSE'
        })
        position_side = None

    total_trades = len(trades)
    win_rate = (win_trades / closed_trades * 100) if closed_trades > 0 else 0.0
    avg_pnl_net = (cumulative_pnl / closed_trades) if closed_trades > 0 else 0.0
    avg_pnl_gross = (gross_pnl_total / closed_trades) if closed_trades > 0 else 0.0

    summary = {
        'days': days,
        'interval': interval,
        'data_points': len(df),
        'total_signals': total_trades,
        'closed_trades': closed_trades,
        'win_rate': round(win_rate, 2),
        'gross_pnl_total': round(gross_pnl_total, 2),
        'total_fees': round(total_fees, 2),
        'net_pnl_total': round(cumulative_pnl, 2),
        'avg_pnl_gross': round(avg_pnl_gross, 2),
        'avg_pnl_net': round(avg_pnl_net, 2),
        # 兼容旧字段名（用于前端已存在的显示逻辑）
        'total_pnl': round(cumulative_pnl, 2),
        'avg_pnl_per_trade': round(avg_pnl_net, 2)
    }

    # 计算 scores 以与技术图保持一致（使用当前情绪）
    try:
        sentiment_data = get_sentiment_indicators()
    except Exception:
        sentiment_data = None

    scores = []
    if sentiment_data is not None:
        for i in range(len(df)):
            try:
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
                sc = calculate_integrated_trading_score(
                    current_price=df['close'].iloc[i],
                    technical_data=technical_data,
                    sentiment_data=sentiment_data
                )
                scores.append(sc)
            except Exception:
                scores.append(0)
        df['score'] = scores
    else:
        df['score'] = 0

    # 组装与技术指标分析相同结构的 chart 数据
    klines_df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
    klines_df['timestamp'] = klines_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')

    chart = {
        'klines': klines_df.to_dict('records'),
        'indicators': {
            'sma5': df['sma_5'].fillna(0).tolist(),
            'sma20': df['sma_20'].fillna(0).tolist(),
            'sma50': df['sma_50'].fillna(0).tolist(),
            'ema12': df['ema_12'].fillna(0).tolist(),
            'ema26': df['ema_26'].fillna(0).tolist(),
            'macd': df['macd'].fillna(0).tolist(),
            'macd_signal': df['macd_signal'].fillna(0).tolist(),
            'macd_histogram': df['macd_histogram'].fillna(0).tolist(),
            'rsi': df['rsi'].fillna(50).tolist(),
            'bb_upper': df['bb_upper'].bfill().ffill().tolist(),
            'bb_middle': df['bb_middle'].bfill().ffill().tolist(),
            'bb_lower': df['bb_lower'].bfill().ffill().tolist(),
            'scores': (df['score'].fillna(0).tolist() if 'score' in df.columns else [0]*len(df)),
            'decisions': decisions
        },
        'labels': labels_hm
    }

    return {
        'labels': labels_full,
        'prices': prices,
        'decisions': decisions,
        'equity_curve': equity_curve,
        'trades': trades,
        'summary': summary,
        'chart': chart
    }


if __name__ == '__main__':
    result = run_backtest(days=2, interval='3m')
    print('回测统计:', result.get('summary'))
    print('信号数:', len(result.get('trades', [])))
