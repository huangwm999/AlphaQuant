import os
import time
import schedule
from openai import OpenAI
import ccxt
import pandas as pd
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta

# 导入重构分离的模块
from market_data import (
    get_recent_trades, get_recent_ai_analysis, get_btc_ohlcv_base,
    get_btc_ohlcv_enhanced, get_current_position, get_btc_ohlcv_for_web
)
from technical_analysis import (
    calculate_technical_indicators, get_support_resistance_levels,
    get_market_trend, generate_technical_analysis_text,
    get_sentiment_indicators, calculate_integrated_trading_score
)
from strategy_decision import StrategyInterface

def load_strategy_config():
    """从配置文件加载策略配置"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'strategy_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"⚠️ 加载策略配置失败: {e}，使用默认版本 strategy_decision_v2")
        return {
            'live_trading': {'version': 'strategy_decision_v2'},
            'available_versions': [],
            'backtest_default': {'version': 'strategy_decision_v2', 'days': 2, 'interval': '15m'}
        }

def save_trade_log(action, side, size, response):
    """保存交易日志到data/trade_logs.json"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "side": side,
        "size": size,
        "response": response
    }
    
    log_file = "data/trade_logs.json"
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            logs = json.load(f)
    else:
        logs = []
    
    logs.append(log_entry)
    
    # 只保留最近100条记录
    if len(logs) > 100:
        logs = logs[-100:]
    
    with open(log_file, 'w') as f:
        json.dump(logs, f, indent=2)

from data_manager import update_system_status, save_trade_record, save_ai_analysis_record, DataManager

load_dotenv()

# 初始化数据管理器
data_manager = DataManager()

# 创建 DeepSeek AI 客户端
deepseek_client = OpenAI(
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    base_url="https://api.deepseek.com"
)

# 初始加载策略配置（仅用于启动时输出信息）
initial_config = load_strategy_config()
initial_version = initial_config.get('live_trading', {}).get('version', 'strategy_decision_v2')
print(f"🎯 启动时策略版本: {initial_version}")

# 统一交易记录封装，确保前端匹配到K线
def record_trade(action: str, side: str, size: float, ref_price: float, response: dict, signal_data: dict, extra: dict | None = None):
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

# 初始化OKX交易所
exchange = ccxt.okx({
    'options': {
        'defaultType': 'swap',  # OKX使用swap表示永续合约
    },
    'apiKey': os.getenv('OKX_API_KEY'),
    'secret': os.getenv('OKX_SECRET'),
    'password': os.getenv('OKX_PASSWORD'),  # OKX需要交易密码
})

# 交易参数配置 - 结合两个版本的优点
TRADE_CONFIG = {
    'symbol': 'BTC/USDT:USDT',  # OKX的合约符号格式
    'leverage': 10,  # 杠杆倍数,只影响保证金不影响下单价值
    'timeframe': '15m',  # 使用15分钟K线
    'test_mode': False,  # 测试模式
    'data_points': 96,  # 24小时数据（96根15分钟K线）
    'analysis_periods': {
        'short_term': 20,  # 短期均线
        'medium_term': 50,  # 中期均线
        'long_term': 96  # 长期趋势
    },
    # 新增智能仓位参数
    'position_management': {
        'enable_intelligent_position': True,  # 🆕 新增：是否启用智能仓位管理
        'base_usdt_amount': 300,  # USDT投入下单基数 - 调整为20适合小资金账户
        'high_confidence_multiplier': 1.5,
        'medium_confidence_multiplier': 1.0,
        'low_confidence_multiplier': 0.5,
        'max_position_ratio': 10,  # 单次最大仓位比例
        'atr_multiplier': 2.0,  # ATR止损倍数
        'enable_scaling': True  # 启用分级加仓
    }
}

# 全局变量存储历史数据
signal_history = []


def setup_exchange():
    """设置交易所参数并验证连接"""
    try:
        print("正在初始化OKX交易所...")
        
        # 设置交易所参数
        exchange.set_sandbox_mode(False)  # 使用实盘环境
        
        # 测试API连接
        balance = exchange.fetch_balance()
        print(f"✅ 成功连接到OKX交易所")
        print(f"USDT余额: {balance['USDT']['free']:.2f}")
        
        # 设置杠杆（OKX合约需要）
        try:
            # 首先获取当前杠杆
            current_leverage = exchange.fetch_leverage(TRADE_CONFIG['symbol'])
            print(f"当前杠杆: {current_leverage}")
            
            # 如果需要，设置新的杠杆
            if current_leverage != TRADE_CONFIG['leverage']:
                print(f"设置杠杆为: {TRADE_CONFIG['leverage']}x")
                exchange.set_leverage(TRADE_CONFIG['leverage'], TRADE_CONFIG['symbol'])
                print(f"✅ 杠杆设置成功: {TRADE_CONFIG['leverage']}x")
            else:
                print(f"✅ 杠杆已设置为: {TRADE_CONFIG['leverage']}x")
                
        except Exception as leverage_error:
            print(f"⚠️ 设置杠杆失败: {leverage_error}")
            print("继续使用默认杠杆设置")
        
        # 获取市场信息
        ticker = exchange.fetch_ticker(TRADE_CONFIG['symbol'])
        print(f"BTC/USDT当前价格: ${ticker['last']:,.2f}")
        
        return True
        
    except ccxt.NetworkError as e:
        print(f"❌ 网络连接错误: {e}")
        return False
    except ccxt.ExchangeError as e:
        print(f"❌ 交易所错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 未知错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def calculate_intelligent_position(signal_data, price_data, current_position):
    """智能仓位计算函数 - 增强版"""
    try:
        base_usdt = TRADE_CONFIG['position_management']['base_usdt_amount']
        
        # 信心程度倍数
        confidence_multipliers = {
            'HIGH': TRADE_CONFIG['position_management']['high_confidence_multiplier'],
            'MEDIUM': TRADE_CONFIG['position_management']['medium_confidence_multiplier'],
            'LOW': TRADE_CONFIG['position_management']['low_confidence_multiplier']
        }
        
        confidence_multiplier = confidence_multipliers.get(signal_data['confidence'], 1.0)
        
        # 趋势强度调整
        trend_analysis = price_data.get('trend_analysis', {})
        trend_strength = trend_analysis.get('strength', '中')
        
        if trend_strength == '强':
            trend_multiplier = 1.3
        elif trend_strength == '中':
            trend_multiplier = 1.0
        else:
            trend_multiplier = 0.7
        
        # 根据RSI状态调整（超买超卖区域减仓）
        rsi = price_data['technical_data'].get('rsi', 50)
        if rsi > 75 or rsi < 25:
            rsi_multiplier = 0.7
        else:
            rsi_multiplier = 1.0
        
        # 计算建议USDT金额
        suggested_usdt = base_usdt * confidence_multiplier * trend_multiplier * rsi_multiplier
        
        # 转换为BTC数量
        btc_amount = suggested_usdt / price_data['price']
        
        # 确保符合交易所最小交易量要求
        min_amount = 0.0001  # OKX最小交易量
        if btc_amount < min_amount:
            btc_amount = min_amount
        
        # 最大仓位限制
        max_position_usdt = base_usdt * TRADE_CONFIG['position_management']['max_position_ratio']
        max_btc_amount = max_position_usdt / price_data['price']
        
        if btc_amount > max_btc_amount:
            btc_amount = max_btc_amount
        
        print(f"\n📊 智能仓位计算:")
        print(f"   - 基础投入: ${base_usdt}")
        print(f"   - 信心倍数: {confidence_multiplier}")
        print(f"   - 趋势倍数: {trend_multiplier}")
        print(f"   - RSI倍数: {rsi_multiplier}")
        print(f"   - 建议金额: ${suggested_usdt:.2f}")
        print(f"   - 计算仓位: {btc_amount:.4f} BTC")
        
        return btc_amount
        
    except Exception as e:
        print(f"仓位计算错误: {e}")
        return 0.0001  # 返回最小仓位


def execute_intelligent_trade(signal_data, price_data):
    """执行智能交易 - OKX版本（支持同方向加仓减仓）"""
    global position

    current_position = get_current_position(exchange, TRADE_CONFIG)

    # 防止频繁反转的逻辑保持不变
    if current_position and signal_data['signal'] != 'HOLD':
        current_side = current_position['side']  # 'long' 或 'short'

        if signal_data['signal'] == 'BUY':
            new_side = 'long'
        elif signal_data['signal'] == 'SELL':
            new_side = 'short'
        else:
            new_side = None

        # 如果方向相反，需要高信心才执行
        # if new_side != current_side:
        #     if signal_data['confidence'] != 'HIGH':
        #         print(f"🔒 非高信心反转信号，保持现有{current_side}仓")
        #         return

        #     if len(signal_history) >= 2:
        #         last_signals = [s['signal'] for s in signal_history[-2:]]
        #         if signal_data['signal'] in last_signals:
        #             print(f"🔒 近期已出现{signal_data['signal']}信号，避免频繁反转")
        #             return

    # 使用智能仓位计算
    trade_size = calculate_intelligent_position(signal_data, price_data, current_position)
    
    # 如果仓位计算失败或为0，跳过交易
    if trade_size <= 0:
        print("❌ 仓位计算失败或仓位为0，跳过交易")
        return

    print(f"📊 计算仓位: {trade_size:.4f} BTC")

    try:
        if signal_data['signal'] == 'BUY':
            if current_position and current_position['side'] == 'long':
                # 同向加仓
                print(f"📈 多头加仓: {trade_size:.4f} BTC")
                response = exchange.create_market_buy_order(
                    TRADE_CONFIG['symbol'], 
                    trade_size
                )
                print(f"✅ 多头加仓成功: {response}")
            elif current_position and current_position['side'] == 'short':
                # 先平空仓
                current_size = abs(current_position['size'])
                print(f"📉 平空仓: {current_size:.4f} BTC")
                close_response = exchange.create_market_buy_order(
                    TRADE_CONFIG['symbol'], 
                    current_size
                )
                print(f"✅ 平空成功: {close_response}")
                
                # 再开多仓
                time.sleep(1)  # 稍微等待一下
                print(f"📈 开多仓: {trade_size:.4f} BTC")
                open_response = exchange.create_market_buy_order(
                    TRADE_CONFIG['symbol'], 
                    trade_size
                )
                print(f"✅ 开多成功: {open_response}")
                
                # 保存两个交易记录（统一格式）
                record_trade('CLOSE_SHORT', 'buy', current_size, price_data['price'], close_response, signal_data)
                record_trade('OPEN_LONG', 'buy', trade_size, price_data['price'], open_response, signal_data)
                save_trade_log('CLOSE_SHORT', 'buy', current_size, close_response)
                save_trade_log('OPEN_LONG', 'buy', trade_size, open_response)
                return
            else:
                # 直接开多仓
                print(f"📈 开多仓: {trade_size:.4f} BTC")
                response = exchange.create_market_buy_order(
                    TRADE_CONFIG['symbol'], 
                    trade_size
                )
                print(f"✅ 开多成功: {response}")
            
            # 保存交易记录（统一格式）
            action = 'OPEN_LONG' if not current_position else 'ADD_LONG'
            record_trade(action, 'buy', trade_size, price_data['price'], response, signal_data)
            save_trade_log(action, 'buy', trade_size, response)

        elif signal_data['signal'] == 'SELL':
            if current_position and current_position['side'] == 'short':
                # 同向加仓
                print(f"📉 空头加仓: {trade_size:.4f} BTC")
                response = exchange.create_market_sell_order(
                    TRADE_CONFIG['symbol'], 
                    trade_size
                )
                print(f"✅ 空头加仓成功: {response}")
            elif current_position and current_position['side'] == 'long':
                # 先平多仓
                current_size = abs(current_position['size'])
                print(f"📈 平多仓: {current_size:.4f} BTC")
                close_response = exchange.create_market_sell_order(
                    TRADE_CONFIG['symbol'], 
                    current_size
                )
                print(f"✅ 平多成功: {close_response}")
                
                # 再开空仓
                time.sleep(1)
                print(f"📉 开空仓: {trade_size:.4f} BTC")
                open_response = exchange.create_market_sell_order(
                    TRADE_CONFIG['symbol'], 
                    trade_size
                )
                print(f"✅ 开空成功: {open_response}")
                
                # 保存两个交易记录（统一格式）
                record_trade('CLOSE_LONG', 'sell', current_size, price_data['price'], close_response, signal_data)
                record_trade('OPEN_SHORT', 'sell', trade_size, price_data['price'], open_response, signal_data)
                save_trade_log('CLOSE_LONG', 'sell', current_size, close_response)
                save_trade_log('OPEN_SHORT', 'sell', trade_size, open_response)
                return
            else:
                # 直接开空仓
                print(f"📉 开空仓: {trade_size:.4f} BTC")
                response = exchange.create_market_sell_order(
                    TRADE_CONFIG['symbol'], 
                    trade_size
                )
                print(f"✅ 开空成功: {response}")
                
            # 保存交易记录（统一格式）
            action = 'OPEN_SHORT' if not current_position else 'ADD_SHORT'
            record_trade(action, 'sell', trade_size, price_data['price'], response, signal_data)
            save_trade_log(action, 'sell', trade_size, response)

        else:  # HOLD或其他
            print("💤 保持观望")

    except ccxt.BaseError as e:
        if "Insufficient balance" in str(e):
            print(f"❌ 余额不足: {e}")
        else:
            print(f"❌ 交易所错误: {e}")
    except Exception as e:
        print(f"❌ 交易执行失败: {e}")
        import traceback
        traceback.print_exc()


def trading_bot():
    """主交易机器人函数"""

    print("\n" + "=" * 60)
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 获取增强版K线数据
    price_data = get_btc_ohlcv_enhanced(exchange, TRADE_CONFIG, calculate_technical_indicators, get_support_resistance_levels, get_market_trend)
    if not price_data:
        print("❌ 获取K线数据失败，跳过本次执行")
        return False

    print(f"BTC当前价格: ${price_data['price']:,.2f}")
    print(f"数据周期: {TRADE_CONFIG['timeframe']} (每1分钟执行策略)")
    print(f"价格变化: {price_data['price_change']:+.2f}%")

    # 2. 获取账户信息
    try:
        balance = exchange.fetch_balance()
        account_info = {
            'balance': float(balance['USDT'].get('free', 0)),
            'equity': float(balance['USDT'].get('total', 0)),
            'leverage': TRADE_CONFIG['leverage']
        }
    except Exception as e:
        print(f"获取账户信息失败: {e}")
        account_info = None

    # 3. 获取当前持仓
    current_position = get_current_position(exchange, TRADE_CONFIG)
    position_info = None
    if current_position:
        position_info = {
            'side': current_position['side'],
            'size': current_position['size'],
            'entry_price': current_position['entry_price'],
            'unrealized_pnl': current_position['unrealized_pnl']
        }

    # 4. 每次都重新加载策略配置，支持动态切换
    strategy_config = load_strategy_config()
    strategy_version = strategy_config.get('live_trading', {}).get('version', 'strategy_decision_v2')
    print(f"🔄 使用策略版本: {strategy_version}")
    
    # 使用当前配置的策略版本创建策略接口
    strategy_interface = StrategyInterface(deepseek_client, strategy_version=strategy_version)
    
    # 使用策略接口进行市场分析（带重试）
    signal_data = strategy_interface.analyze_market_strategy(
        price_data, signal_history
    )

    if signal_data:
        print(f"🎯 AI交易信号: {signal_data['signal']} (信心: {signal_data['confidence']})")
        print(f"📝 分析原因: {signal_data['reason']}")
        
        # 添加到历史记录
        signal_history.append(signal_data)
        if len(signal_history) > 50:  # 保留最近50条记录
            signal_history.pop(0)

        # 5. 执行交易
        if signal_data['signal'] != 'HOLD':
            execute_intelligent_trade(signal_data, price_data)
        else:
            print("💤 保持观望")

        # 6. 保存AI分析记录
        try:
            analysis_record = {
                'signal': signal_data['signal'],
                'confidence': signal_data['confidence'],
                'reason': signal_data['reason'],
                'stop_loss': signal_data.get('stop_loss', 0),
                'take_profit': signal_data.get('take_profit', 0),
                'btc_price': price_data['price'],
                'price_change': price_data['price_change'],
                'has_position': current_position is not None,
                'position_side': current_position['side'] if current_position else None,
                'position_size': current_position['size'] if current_position else 0
            }
            save_ai_analysis_record(analysis_record)
            print("✅ AI分析记录已保存")
        except Exception as e:
            print(f"保存AI分析记录失败: {e}")

    # 7. 更新系统状态到Web界面
    try:
        # 构造符合 data_manager.py 期望的数据结构
        btc_info_data = {
            'price': price_data['price'],
            'change': price_data['price_change']
        }
        
        ai_signal_data = {
            'signal': signal_data['signal'] if signal_data else 'NONE',
            'confidence': signal_data['confidence'] if signal_data else 'NONE',
            'reason': signal_data.get('reason', '') if signal_data else ''
        }
        
        # 调用正确的更新函数，传递5个参数
        update_system_status(
            status='running',
            account_info=account_info,
            btc_info=btc_info_data,
            position=position_info,
            ai_signal=ai_signal_data
        )
        print("✅ 系统状态已更新")
    except Exception as e:
        print(f"更新系统状态失败: {e}")

    return True


def main():
    """主函数"""
    print("🚀 启动DeepSeek智能交易机器人 v3.0")
    print("=" * 50)
    
    # 初始化交易所
    if not setup_exchange():
        print("❌ 交易所初始化失败，程序退出")
        return
    
    # 设置定时任务
    schedule.every(1).minutes.do(trading_bot)
    
    print("⏰ 定时任务已设置: 每1分钟执行一次")
    print("🤖 机器人开始运行...")
    print("按 Ctrl+C 停止程序")
    
    try:
        # 先执行一次
        trading_bot()
        
        # 进入定时循环
        while True:
            schedule.run_pending()
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n👋 收到停止信号，正在安全退出...")
    except Exception as e:
        print(f"\n❌ 程序异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("✅ 程序已安全退出")

if __name__ == "__main__":
    main()