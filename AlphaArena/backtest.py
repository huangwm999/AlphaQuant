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

def fetch_since_paginated(exchange: ccxt.Exchange, symbol: str, timeframe: str, since_ms: int, max_candles: int = 1200, page_limit: int = 200):
    """从指定since开始分页获取K线，直至达到max_candles或无更多数据。
    OKX部分周期单次limit较小，采用分页方式更稳妥。
    返回已转换为上海时区的DataFrame。
    """
    all_rows = []
    cursor = since_ms
    safety = 0
    max_iterations = max(50, (max_candles // page_limit) + 10)  # 动态计算最大迭代次数
    
    while len(all_rows) < max_candles and safety < max_iterations:
        safety += 1
        try:
            chunk = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=page_limit)
        except Exception as e:
            print(f"⚠️ 获取数据出错 (第{safety}次): {str(e)[:100]}")
            break
        if not chunk:
            break
        
        all_rows.extend(chunk)
        # 推进游标到最后一根之后，避免重复
        cursor = chunk[-1][0] + 1

        # 简单的停止条件：如果返回的数量少于page_limit，认为到尾部
        if len(chunk) < page_limit:
            break
    
    print(f"   分页获取完成: {safety} 次迭代，共 {len(all_rows)} 条原始数据")

    if not all_rows:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    # 去重并组装
    df = pd.DataFrame(all_rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
    # 仅保留自since_ms之后的数据
    df = df[df['timestamp'] >= since_ms]
    # 转换为上海时区
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)
    return df


def run_backtest(days: int = 2, interval: str = '15m', strategy_version: str = 'strategy_decision_v2', end_time: str = None) -> Dict[str, Any]:
    """
    运行回测。
    Args:
        days: 回测天数 (默认 2 天，最多支持 300 天)
        interval: K线级别 (默认 15m)
        strategy_version: 策略版本 (默认 strategy_decision_v2)
        end_time: 回测截至时间 (格式: 'YYYY-MM-DD HH:MM:SS'，默认为当前时间)
    Returns:
        dict: { labels, prices, decisions, trades, equity_curve, summary }
        注意：当回测天数超过20天时，返回数据仅包含最近20天，但统计数据基于完整回测结果
    """
    # 限制最大回测天数为300天
    days = min(days, 300)
    symbol = TRADE_CONFIG['symbol']
    # 计算两天所需根数
    minutes = interval_to_minutes(interval)
    per_day = int(24 * 60 / minutes)
    expected_candles = days * per_day

    # 解析截至时间，默认为当前时间
    if end_time:
        try:
            end_timestamp = pd.Timestamp(end_time, tz='Asia/Shanghai')
        except Exception as e:
            print(f"⚠️ 截至时间解析失败: {e}，使用当前时间")
            end_timestamp = pd.Timestamp.now(tz='Asia/Shanghai')
    else:
        end_timestamp = pd.Timestamp.now(tz='Asia/Shanghai')
    
    # 计算起始时间
    since_sh = end_timestamp - timedelta(days=days)
    since_utc = since_sh.tz_convert('UTC')
    since_ms = int(since_utc.timestamp() * 1000)
    end_utc = end_timestamp.tz_convert('UTC')
    end_ms = int(end_utc.timestamp() * 1000)

    # 优先分页抓取，确保覆盖完整时间区间
    # 注意：OKX等交易所单次抓取有限制，采用分页方式，max_candles设置为需求的1.5倍，增加安全边界
    df = fetch_since_paginated(exchange, symbol, interval, since_ms=since_ms, max_candles=int(expected_candles * 1.5), page_limit=300)
    
    # 过滤掉截至时间之后的数据
    # 注意：DataFrame中的timestamp是naive datetime（无时区），需要转换为相同类型才能比较
    if not df.empty:
        # 将带时区的end_timestamp转换为naive datetime以匹配DataFrame
        end_timestamp_naive = end_timestamp.tz_localize(None)
        df = df[df['timestamp'] <= end_timestamp_naive]
    
    # 调试信息：显示实际获取的数据情况
    print(f"📥 数据获取: 期望 {expected_candles} 根K线，实际获取 {len(df)} 根")
    print(f"   回测时间范围: {since_sh.strftime('%Y-%m-%d %H:%M:%S')} 至 {end_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    if not df.empty:
        print(f"   实际数据范围: {df['timestamp'].iloc[0]} 至 {df['timestamp'].iloc[-1]}")
    
    # 如果分页获取失败或数据严重不足，不要退化到fetch_recent（它只能获取最近数据）
    # 而是直接使用已获取的数据进行回测
    if df.empty:
        return { 'error': '无法获取历史数据' }

    # 计算技术指标
    df = calculate_technical_indicators(df)

    # 初始化策略接口（使用指定版本）
    strategy = StrategyInterface(deepseek_client, strategy_version=strategy_version)

    labels_full = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M').tolist()
    
    # 智能格式化时间标签：如果数据跨越多天，显示"月-日 时:分"，否则只显示"时:分"
    if len(df) > 0:
        first_date = df['timestamp'].iloc[0].date()
        last_date = df['timestamp'].iloc[-1].date()
        if first_date != last_date:
            # 跨天数据：显示 "月-日 时:分"
            labels_hm = df['timestamp'].dt.strftime('%m-%d %H:%M').tolist()
        else:
            # 单天数据：只显示 "时:分"
            labels_hm = df['timestamp'].dt.strftime('%H:%M').tolist()
    else:
        labels_hm = []
    
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

    # 计算第1天结束的索引位置（作为预热期）
    warmup_candles = per_day  # 第1天的K线数量
    
    # 回测逐根
    for i in range(len(df)):
        # 第1天作为预热期，不进行交易判断
        if i < warmup_candles:
            decisions.append(0)
            equity_curve.append(cumulative_pnl)
            continue
        
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
        signal_ts = labels_full[i-1]  # V型实际形成位置（P-1时刻）
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
                    'timestamp': signal_ts,  # 使用V型实际位置的时间戳
                    'execution_time': ts,    # 实际执行时间
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
        'end_time': end_timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'data_points': len(df),
        'total_signals': total_trades,
        'closed_trades': closed_trades,
        'win_rate': round(win_rate, 2),
        'gross_pnl_total': round(gross_pnl_total, 2),
        'total_fees': round(total_fees, 2),
        'net_pnl_total': round(cumulative_pnl, 2),
        'avg_pnl_gross': round(avg_pnl_gross, 2),
        'avg_pnl_net': round(avg_pnl_net, 2),
        'time_start': df['timestamp'].iloc[0].strftime('%Y-%m-%d %H:%M:%S') if len(df) else None,
        'time_end': df['timestamp'].iloc[-1].strftime('%Y-%m-%d %H:%M:%S') if len(df) else None,
        'timezone': 'Asia/Shanghai',
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

    # 数据截取逻辑：当回测天数超过20天时，仅返回最近20天的图表数据
    display_days = 20
    should_truncate = days > display_days
    
    if should_truncate:
        # 使用时间戳来精确计算截断位置
        last_timestamp = df['timestamp'].iloc[-1]
        truncate_time = last_timestamp - timedelta(days=display_days)
        
        # 调试信息
        print(f"🔍 截断调试信息：")
        print(f"   数据范围: {df['timestamp'].iloc[0]} 至 {last_timestamp}")
        print(f"   总数据点: {len(df)}")
        print(f"   截断时间点: {truncate_time}")
        
        # 直接找到截断位置（使用整数位置索引）
        truncate_start_pos = 0
        for idx in range(len(df)):
            if df['timestamp'].iloc[idx] >= truncate_time:
                truncate_start_pos = idx
                break
        
        print(f"   截断位置索引: {truncate_start_pos}")
        print(f"   截断后起始时间: {df['timestamp'].iloc[truncate_start_pos]}")
        print(f"   返回数据点数: {len(df) - truncate_start_pos}")
        
        actual_display_days = (last_timestamp - df['timestamp'].iloc[truncate_start_pos]).days
        truncate_timestamp = df['timestamp'].iloc[truncate_start_pos]
        
        # 截取最近20天的数据用于返回（使用位置切片）
        labels_display = labels_full[truncate_start_pos:]
        labels_hm_display = labels_hm[truncate_start_pos:]
        prices_display = prices[truncate_start_pos:]
        decisions_display = decisions[truncate_start_pos:]
        equity_curve_display = equity_curve[truncate_start_pos:]
        klines_display = klines_df.iloc[truncate_start_pos:].to_dict('records')
        
        # 技术指标也截取
        indicators_display = {
            'sma5': df['sma_5'].fillna(0).tolist()[truncate_start_pos:],
            'sma20': df['sma_20'].fillna(0).tolist()[truncate_start_pos:],
            'sma50': df['sma_50'].fillna(0).tolist()[truncate_start_pos:],
            'ema12': df['ema_12'].fillna(0).tolist()[truncate_start_pos:],
            'ema26': df['ema_26'].fillna(0).tolist()[truncate_start_pos:],
            'macd': df['macd'].fillna(0).tolist()[truncate_start_pos:],
            'macd_signal': df['macd_signal'].fillna(0).tolist()[truncate_start_pos:],
            'macd_histogram': df['macd_histogram'].fillna(0).tolist()[truncate_start_pos:],
            'rsi': df['rsi'].fillna(50).tolist()[truncate_start_pos:],
            'bb_upper': df['bb_upper'].bfill().ffill().tolist()[truncate_start_pos:],
            'bb_middle': df['bb_middle'].bfill().ffill().tolist()[truncate_start_pos:],
            'bb_lower': df['bb_lower'].bfill().ffill().tolist()[truncate_start_pos:],
            'scores': (df['score'].fillna(0).tolist()[truncate_start_pos:] if 'score' in df.columns else [0]*len(labels_display)),
            'decisions': decisions_display
        }
        
        # 筛选最近20天内发生的交易
        trades_display = [
            t for t in trades 
            if pd.to_datetime(t['timestamp']) >= truncate_timestamp
        ]
        
        print(f"📊 回测完成：完整回测 {days} 天（{df['timestamp'].iloc[0].strftime('%Y-%m-%d')} 至 {last_timestamp.strftime('%Y-%m-%d')}），"
              f"返回最近 ~{actual_display_days} 天数据（{truncate_timestamp.strftime('%Y-%m-%d %H:%M')} 开始，共 {len(labels_display)} 个数据点，{len(trades_display)}/{len(trades)} 笔交易）")
    else:
        # 不截取，返回完整数据
        labels_display = labels_full
        labels_hm_display = labels_hm
        prices_display = prices
        decisions_display = decisions
        equity_curve_display = equity_curve
        klines_display = klines_df.to_dict('records')
        trades_display = trades
        
        indicators_display = {
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
        }

    chart = {
        'klines': klines_display,
        'indicators': indicators_display,
        'labels': labels_hm_display
    }

    # 计算完整的天收益数据（不受20天限制）
    daily_pnl_map = {}
    for trade in trades:
        if trade.get('pnl') is not None:
            date = trade['timestamp'].split(' ')[0]  # 提取日期 YYYY-MM-DD
            if date not in daily_pnl_map:
                daily_pnl_map[date] = 0
            daily_pnl_map[date] += trade['pnl']
    
    # 转换为列表并排序
    daily_pnl_list = [
        {'date': date, 'pnl': round(pnl, 2)}
        for date, pnl in sorted(daily_pnl_map.items(), key=lambda x: x[0], reverse=True)
    ]

    return {
        'labels': labels_display,
        'prices': prices_display,
        'decisions': decisions_display,
        'equity_curve': equity_curve_display,
        'trades': trades_display,
        'trades_full': trades,  # 完整的交易记录（不受截断限制）
        'daily_pnl': daily_pnl_list,  # 天收益列表（完整数据）
        'summary': summary,
        'chart': chart
    }


if __name__ == '__main__':
    result = run_backtest(days=2, interval='3m')
    print('回测统计:', result.get('summary'))
    print('信号数:', len(result.get('trades', [])))
