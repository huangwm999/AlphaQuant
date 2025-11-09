#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立交易执行模块
提供统一的交易执行接口，供 deepseekok3.py 和 web_app2.py 调用
"""

import time
import ccxt
import pandas as pd
from datetime import datetime
from market_data import get_current_position
from data_manager import save_trade_record


def record_trade(action: str, side: str, size: float, ref_price: float, response: dict, signal_data: dict, extra: dict = None):
    """构造并保存一条标准化交易记录到 trades.json。
    - 时间戳采用上海时区字符串 '%Y-%m-%d %H:%M:%S'
    - 保存 signal/confidence/reason 字段，方便技术图 merge_asof 匹配
    - 兼容旧字段 price/size
    """
    try:
        ts = pd.Timestamp.now(tz='Asia/Shanghai').strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 尝试提取订单关键信息（不同交易所字段兼容）
    order_id = None
    try:
        order_id = response.get('id') or response.get('orderId') or (response.get('data') or {}).get('ordId')
    except Exception:
        order_id = None
    try:
        avg_price = response.get('average') or response.get('price') or response.get('lastFillPrice') or ref_price
    except Exception:
        avg_price = ref_price

    trade_record = {
        'timestamp': ts,
        'action': action,
        'side': side,
        'qty': round(float(size), 6),
        'ref_price': round(float(ref_price), 2),
        'fill_price': round(float(avg_price), 2) if isinstance(avg_price, (int, float)) else avg_price,
        'order_id': order_id,
        'signal': signal_data.get('signal'),
        'confidence': signal_data.get('confidence'),
        'reason': signal_data.get('reason'),
        'strategy_version': signal_data.get('strategy_version'),
        'order_raw': response
    }
    if extra:
        trade_record.update(extra)

    # 兼容旧字段命名
    trade_record['price'] = trade_record['ref_price']
    trade_record['size'] = trade_record['qty']

    save_trade_record(trade_record)
    return trade_record


def calculate_position_size(signal_data: dict, price_data: dict, trade_config: dict, current_position: dict = None):
    """智能仓位计算函数 - 简化版（固定金额，按张数下单）"""
    try:
        base_usdt = trade_config['position_management']['base_usdt_amount']
        
        # 直接使用基础金额，不应用任何倍数调整
        suggested_usdt = base_usdt
        
        # 转换为BTC数量
        btc_amount = suggested_usdt / price_data['price']
        
        # OKX合约单位：1张 = 0.01 BTC，计算需要多少张
        contract_size = 0.01  # 每张合约代表的BTC数量
        num_contracts = btc_amount / contract_size
        
        # 向下取整到整数张（不足1张则取1张）
        num_contracts = max(1, int(num_contracts))
        
        # 转换回BTC数量（用于显示）
        btc_amount = num_contracts * contract_size
        
        # 最大仓位限制（按张数）
        max_position_usdt = base_usdt * trade_config['position_management']['max_position_ratio']
        max_btc_amount = max_position_usdt / price_data['price']
        max_contracts = int(max_btc_amount / contract_size)
        
        if num_contracts > max_contracts:
            num_contracts = max_contracts
            btc_amount = num_contracts * contract_size
        
        print(f"\n📊 仓位计算:")
        print(f"   - 投入金额: ${suggested_usdt:.2f}")
        print(f"   - 理论BTC: {suggested_usdt / price_data['price']:.4f} BTC")
        print(f"   - 下单张数: {num_contracts} 张")
        print(f"   - 实际BTC: {btc_amount:.4f} BTC")
        print(f"   - 实际价值: ${btc_amount * price_data['price']:.2f}")
        
        return btc_amount
        
    except Exception as e:
        print(f"仓位计算错误: {e}")
        return 0.01  # 返回最小仓位（1张 = 0.01 BTC）


def execute_trade(exchange, trade_config: dict, signal_data: dict, price_data: dict):
    """
    执行交易 - 统一接口
    
    Args:
        exchange: ccxt交易所实例
        trade_config: 交易配置字典
        signal_data: 信号数据，必须包含 'signal' 字段 ('BUY' 或 'SELL')
        price_data: 价格数据，必须包含 'price' 字段；可选包含 'manual_btc_amount' 用于手动交易
    
    Returns:
        dict: 交易结果 {'success': bool, 'message': str, 'trades': list}
    """
    try:
        # 获取当前持仓
        current_position = get_current_position(exchange, trade_config)
        
        # 检查是否手动指定了张数（张数即BTC数量，OKX中1张=0.01BTC）
        if 'manual_contracts' in price_data and price_data['manual_contracts'] > 0:
            trade_size = price_data['manual_contracts']  # 直接使用张数作为BTC数量
            print(f"📊 使用手动指定仓位: {trade_size:.4f} BTC")
        else:
            # 计算交易仓位
            trade_size = calculate_position_size(signal_data, price_data, trade_config, current_position)
        
        # 如果仓位计算失败或为0，跳过交易
        if trade_size <= 0:
            return {
                'success': False,
                'message': '仓位计算失败或仓位为0',
                'trades': []
            }

        print(f"📊 执行仓位: {trade_size:.4f} BTC")
        
        executed_trades = []
        
        # 执行买入
        if signal_data['signal'] == 'BUY':
            if current_position and current_position['side'] == 'long':
                # 同向加仓
                print(f"📈 多头加仓: {trade_size:.4f} BTC")
                response = exchange.create_market_buy_order(
                    trade_config['symbol'], 
                    trade_size
                )
                print(f"✅ 多头加仓成功: {response}")
                
                # 保存交易记录
                record_trade('ADD_LONG', 'buy', trade_size, price_data['price'], response, signal_data)
                executed_trades.append({'action': 'ADD_LONG', 'size': trade_size})
                
            elif current_position and current_position['side'] == 'short':
                # 先平空仓
                current_size = abs(current_position['size'])
                print(f"📉 平空仓: {current_size:.4f} BTC")
                close_response = exchange.create_market_buy_order(
                    trade_config['symbol'], 
                    current_size
                )
                print(f"✅ 平空成功: {close_response}")
                
                # 再开多仓
                time.sleep(1)  # 稍微等待一下
                print(f"📈 开多仓: {trade_size:.4f} BTC")
                open_response = exchange.create_market_buy_order(
                    trade_config['symbol'], 
                    trade_size
                )
                print(f"✅ 开多成功: {open_response}")
                
                # 保存两个交易记录
                record_trade('CLOSE_SHORT', 'buy', current_size, price_data['price'], close_response, signal_data)
                record_trade('OPEN_LONG', 'buy', trade_size, price_data['price'], open_response, signal_data)
                executed_trades.append({'action': 'CLOSE_SHORT', 'size': current_size})
                executed_trades.append({'action': 'OPEN_LONG', 'size': trade_size})
                
            else:
                # 直接开多仓
                print(f"📈 开多仓: {trade_size:.4f} BTC")
                response = exchange.create_market_buy_order(
                    trade_config['symbol'], 
                    trade_size
                )
                print(f"✅ 开多成功: {response}")
                
                # 保存交易记录
                record_trade('OPEN_LONG', 'buy', trade_size, price_data['price'], response, signal_data)
                executed_trades.append({'action': 'OPEN_LONG', 'size': trade_size})
        
        # 执行卖出
        elif signal_data['signal'] == 'SELL':
            if current_position and current_position['side'] == 'short':
                # 同向加仓
                print(f"📉 空头加仓: {trade_size:.4f} BTC")
                response = exchange.create_market_sell_order(
                    trade_config['symbol'], 
                    trade_size
                )
                print(f"✅ 空头加仓成功: {response}")
                
                # 保存交易记录
                record_trade('ADD_SHORT', 'sell', trade_size, price_data['price'], response, signal_data)
                executed_trades.append({'action': 'ADD_SHORT', 'size': trade_size})
                
            elif current_position and current_position['side'] == 'long':
                # 先平多仓
                current_size = abs(current_position['size'])
                print(f"📈 平多仓: {current_size:.4f} BTC")
                close_response = exchange.create_market_sell_order(
                    trade_config['symbol'], 
                    current_size
                )
                print(f"✅ 平多成功: {close_response}")
                
                # 再开空仓
                time.sleep(1)
                print(f"📉 开空仓: {trade_size:.4f} BTC")
                open_response = exchange.create_market_sell_order(
                    trade_config['symbol'], 
                    trade_size
                )
                print(f"✅ 开空成功: {open_response}")
                
                # 保存两个交易记录
                record_trade('CLOSE_LONG', 'sell', current_size, price_data['price'], close_response, signal_data)
                record_trade('OPEN_SHORT', 'sell', trade_size, price_data['price'], open_response, signal_data)
                executed_trades.append({'action': 'CLOSE_LONG', 'size': current_size})
                executed_trades.append({'action': 'OPEN_SHORT', 'size': trade_size})
                
            else:
                # 直接开空仓
                print(f"📉 开空仓: {trade_size:.4f} BTC")
                response = exchange.create_market_sell_order(
                    trade_config['symbol'], 
                    trade_size
                )
                print(f"✅ 开空成功: {response}")
                
                # 保存交易记录
                record_trade('OPEN_SHORT', 'sell', trade_size, price_data['price'], response, signal_data)
                executed_trades.append({'action': 'OPEN_SHORT', 'size': trade_size})
        
        else:
            return {
                'success': False,
                'message': f'无效的交易信号: {signal_data["signal"]}',
                'trades': []
            }
        
        return {
            'success': True,
            'message': f'交易执行成功，共执行 {len(executed_trades)} 笔交易',
            'trades': executed_trades
        }
        
    except ccxt.BaseError as e:
        error_msg = str(e)
        if "Insufficient balance" in error_msg:
            print(f"❌ 余额不足: {e}")
            return {'success': False, 'message': f'余额不足: {error_msg}', 'trades': []}
        else:
            print(f"❌ 交易所错误: {e}")
            return {'success': False, 'message': f'交易所错误: {error_msg}', 'trades': []}
            
    except Exception as e:
        print(f"❌ 交易执行失败: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'message': f'交易执行失败: {str(e)}', 'trades': []}
