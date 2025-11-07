import os
import time
import schedule
from openai import OpenAI
import ccxt
import pandas as pd
import re
from dotenv import load_dotenv
import json
import requests
from datetime import datetime, timedelta

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

# 初始化DeepSeek客户端
deepseek_client = OpenAI(
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    base_url="https://api.deepseek.com"
)

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
        'trend_strength_multiplier': 1.2
    }
}


def setup_exchange():
    """设置交易所参数 - 强制全仓模式"""
    try:

        # 首先获取合约规格信息
        print("🔍 获取BTC合约规格...")
        markets = exchange.load_markets()
        btc_market = markets[TRADE_CONFIG['symbol']]

        # 获取合约乘数
        contract_size = float(btc_market['contractSize'])
        print(f"✅ 合约规格: 1张 = {contract_size} BTC")

        # 存储合约规格到全局配置
        TRADE_CONFIG['contract_size'] = contract_size
        TRADE_CONFIG['min_amount'] = btc_market['limits']['amount']['min']

        print(f"📏 最小交易量: {TRADE_CONFIG['min_amount']} 张")

        # 先检查现有持仓
        print("🔍 检查现有持仓模式...")
        positions = exchange.fetch_positions([TRADE_CONFIG['symbol']])

        has_isolated_position = False
        isolated_position_info = None

        for pos in positions:
            if pos['symbol'] == TRADE_CONFIG['symbol']:
                contracts = float(pos.get('contracts', 0))
                mode = pos.get('mgnMode')

                if contracts > 0 and mode == 'isolated':
                    has_isolated_position = True
                    isolated_position_info = {
                        'side': pos.get('side'),
                        'size': contracts,
                        'entry_price': pos.get('entryPrice'),
                        'mode': mode
                    }
                    break

        # 2. 如果有逐仓持仓，提示并退出
        if has_isolated_position:
            print("❌ 检测到逐仓持仓，程序无法继续运行！")
            print(f"📊 逐仓持仓详情:")
            print(f"   - 方向: {isolated_position_info['side']}")
            print(f"   - 数量: {isolated_position_info['size']}")
            print(f"   - 入场价: {isolated_position_info['entry_price']}")
            print(f"   - 模式: {isolated_position_info['mode']}")
            print("\n🚨 解决方案:")
            print("1. 手动平掉所有逐仓持仓")
            print("2. 或者将逐仓持仓转为全仓模式")
            print("3. 然后重新启动程序")
            return False

        # 3. 设置单向持仓模式
        print("🔄 设置单向持仓模式...")
        try:
            exchange.set_position_mode(False, TRADE_CONFIG['symbol'])  # False表示单向持仓
            print("✅ 已设置单向持仓模式")
        except Exception as e:
            print(f"⚠️ 设置单向持仓模式失败 (可能已设置): {e}")

        # 4. 设置全仓模式和杠杆
        print("⚙️ 设置全仓模式和杠杆...")
        exchange.set_leverage(
            TRADE_CONFIG['leverage'],
            TRADE_CONFIG['symbol'],
            {'mgnMode': 'cross'}  # 强制全仓模式
        )
        print(f"✅ 已设置全仓模式，杠杆倍数: {TRADE_CONFIG['leverage']}x")

        # 5. 验证设置
        print("🔍 验证账户设置...")
        balance = exchange.fetch_balance()
        usdt_balance = balance['USDT']['free']
        print(f"💰 当前USDT余额: {usdt_balance:.2f}")

        # 获取当前持仓状态
        current_pos = get_current_position()
        if current_pos:
            print(f"📦 当前持仓: {current_pos['side']}仓 {current_pos['size']}张")
        else:
            print("📦 当前无持仓")

        print("🎯 程序配置完成：全仓模式 + 单向持仓")
        return True

    except Exception as e:
        print(f"❌ 交易所设置失败: {e}")
        import traceback
        traceback.print_exc()
        return False


# 全局变量存储历史数据
price_history = []
signal_history = []
position = None
first_run = True  # 新增：标记是否为第一次运行


def calculate_intelligent_position(signal_data, price_data, current_position):
    """计算智能仓位大小 - 修复版"""
    config = TRADE_CONFIG['position_management']

    # 🆕 新增：如果禁用智能仓位，使用固定仓位
    if not config.get('enable_intelligent_position', True):
        fixed_contracts = 0.1  # 固定仓位大小，可以根据需要调整
        print(f"🔧 智能仓位已禁用，使用固定仓位: {fixed_contracts} 张")
        return fixed_contracts

    try:
        # 获取账户余额
        balance = exchange.fetch_balance()
        usdt_balance = balance['USDT']['free']

        # 基础USDT投入
        base_usdt = config['base_usdt_amount']
        print(f"💰 可用USDT余额: {usdt_balance:.2f}, 下单基数{base_usdt}")

        # 根据信心程度调整 - 修复这里
        confidence_multiplier = {
            'HIGH': config['high_confidence_multiplier'],
            'MEDIUM': config['medium_confidence_multiplier'],
            'LOW': config['low_confidence_multiplier']
        }.get(signal_data['confidence'], 1.0)  # 添加默认值

        # 根据趋势强度调整
        trend = price_data['trend_analysis'].get('overall', '震荡整理')
        if trend in ['强势上涨', '强势下跌']:
            trend_multiplier = config['trend_strength_multiplier']
        else:
            trend_multiplier = 1.0

        # 根据RSI状态调整（超买超卖区域减仓）
        rsi = price_data['technical_data'].get('rsi', 50)
        if rsi > 75 or rsi < 25:
            rsi_multiplier = 0.7
        else:
            rsi_multiplier = 1.0

        # 计算建议投入USDT金额
        suggested_usdt = base_usdt * confidence_multiplier * trend_multiplier * rsi_multiplier

        # 风险管理：不超过总资金的指定比例 - 删除重复定义
        max_usdt = usdt_balance * config['max_position_ratio']
        final_usdt = min(suggested_usdt, max_usdt)

        # 正确的合约张数计算！
        # 公式：合约张数 = (投入USDT) / (当前价格 * 合约乘数)
        contract_size = (final_usdt) / (price_data['price'] * TRADE_CONFIG['contract_size'])

        print(f"📊 仓位计算详情:")
        print(f"   - 基础USDT: {base_usdt}")
        print(f"   - 信心倍数: {confidence_multiplier}")
        print(f"   - 趋势倍数: {trend_multiplier}")
        print(f"   - RSI倍数: {rsi_multiplier}")
        print(f"   - 建议USDT: {suggested_usdt:.2f}")
        print(f"   - 最终USDT: {final_usdt:.2f}")
        print(f"   - 合约乘数: {TRADE_CONFIG['contract_size']}")
        print(f"   - 计算合约: {contract_size:.4f} 张")

        # 精度处理：OKX BTC合约最小交易单位为0.01张
        contract_size = round(contract_size, 2)  # 保留2位小数

        # 确保最小交易量
        min_contracts = TRADE_CONFIG.get('min_amount', 0.01)
        if contract_size < min_contracts:
            contract_size = min_contracts
            print(f"⚠️ 仓位小于最小值，调整为: {contract_size} 张")

        print(f"🎯 最终仓位: {final_usdt:.2f} USDT → {contract_size:.2f} 张合约")
        return contract_size

    except Exception as e:
        print(f"❌ 仓位计算失败，使用基础仓位: {e}")
        # 紧急备用计算
        base_usdt = config['base_usdt_amount']
        contract_size = (base_usdt * TRADE_CONFIG['leverage']) / (
                    price_data['price'] * TRADE_CONFIG.get('contract_size', 0.01))
        return round(max(contract_size, TRADE_CONFIG.get('min_amount', 0.01)), 2)


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
        df['volume_ratio'] = df['volume'] / df['volume_ma']

        # 支撑阻力位
        df['resistance'] = df['high'].rolling(20).max()
        df['support'] = df['low'].rolling(20).min()

        # 填充NaN值
        df = df.bfill().ffill()

        return df
    except Exception as e:
        print(f"技术指标计算失败: {e}")
        return df


def get_support_resistance_levels(df, lookback=20):
    """计算支撑阻力位"""
    try:
        recent_high = df['high'].tail(lookback).max()
        recent_low = df['low'].tail(lookback).min()
        current_price = df['close'].iloc[-1]

        resistance_level = recent_high
        support_level = recent_low

        # 动态支撑阻力（基于布林带）
        bb_upper = df['bb_upper'].iloc[-1]
        bb_lower = df['bb_lower'].iloc[-1]

        return {
            'static_resistance': resistance_level,
            'static_support': support_level,
            'dynamic_resistance': bb_upper,
            'dynamic_support': bb_lower,
            'price_vs_resistance': ((resistance_level - current_price) / current_price) * 100,
            'price_vs_support': ((current_price - support_level) / support_level) * 100
        }
    except Exception as e:
        print(f"支撑阻力计算失败: {e}")
        return {}


def get_recent_trades(limit=5):
    """获取最近的交易记录，避免重复同向交易"""
    try:
        trade_history = data_manager.get_trade_history()
        if not trade_history:
            return []
        
        # 获取最近limit条记录
        recent_trades = trade_history[-limit:] if len(trade_history) >= limit else trade_history
        
        # 格式化交易记录
        formatted_trades = []
        for trade in recent_trades:
            formatted_trades.append({
                'timestamp': trade.get('timestamp', ''),
                'signal': trade.get('signal', ''),
                'price': trade.get('price', 0),
                'confidence': trade.get('confidence', ''),
                'reason': trade.get('reason', '')[:50] + '...' if len(trade.get('reason', '')) > 50 else trade.get('reason', '')
            })
        
        return formatted_trades
    except Exception as e:
        print(f"获取交易记录失败: {e}")
        return []


def get_recent_ai_analysis(limit=5):
    """获取最近的AI分析历史记录"""
    try:
        ai_history = data_manager.get_ai_analysis_history()
        if not ai_history:
            return []
        
        # 获取最近limit条记录
        recent_analysis = ai_history[-limit:] if len(ai_history) >= limit else ai_history
        
        # 格式化AI分析记录
        formatted_analysis = []
        for analysis in recent_analysis:
            timestamp = analysis.get('timestamp', '')
            time_str = timestamp[-8:-3] if len(timestamp) > 8 else timestamp
            
            # 构建持仓状态描述
            position_desc = "无持仓"
            if analysis.get('has_position'):
                side_zh = "多头" if analysis.get('position_side') == 'long' else "空头"
                size = analysis.get('position_size', 0)
                position_desc = f"{side_zh}{size:.2f}张"
            
            formatted_analysis.append({
                'timestamp': time_str,
                'signal': analysis.get('signal', ''),
                'confidence': analysis.get('confidence', ''),
                'btc_price': analysis.get('btc_price', 0),
                'position_desc': position_desc,
                'reason': analysis.get('reason', '')[:60] + '...' if len(analysis.get('reason', '')) > 60 else analysis.get('reason', '')
            })
        
        return formatted_analysis
    except Exception as e:
        print(f"获取AI分析历史失败: {e}")
        return []


def get_sentiment_indicators():
    """获取情绪指标 - 简洁版本"""
    try:
        API_URL = "https://service.cryptoracle.network/openapi/v2/endpoint"
        API_KEY = "7ad48a56-8730-4238-a714-eebc30834e3e"

        # 获取最近4小时数据
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=4)

        request_body = {
            "apiKey": API_KEY,
            "endpoints": ["CO-A-02-01", "CO-A-02-02"],  # 只保留核心指标
            "startTime": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "endTime": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "timeType": "15m",
            "token": ["BTC"]
        }

        headers = {"Content-Type": "application/json", "X-API-KEY": API_KEY}
        response = requests.post(API_URL, json=request_body, headers=headers)

        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200 and data.get("data"):
                time_periods = data["data"][0]["timePeriods"]

                # 查找第一个有有效数据的时间段
                for period in time_periods:
                    period_data = period.get("data", [])

                    sentiment = {}
                    valid_data_found = False

                    for item in period_data:
                        endpoint = item.get("endpoint")
                        value = item.get("value", "").strip()

                        if value:  # 只处理非空值
                            try:
                                if endpoint in ["CO-A-02-01", "CO-A-02-02"]:
                                    sentiment[endpoint] = float(value)
                                    valid_data_found = True
                            except (ValueError, TypeError):
                                continue

                    # 如果找到有效数据
                    if valid_data_found and "CO-A-02-01" in sentiment and "CO-A-02-02" in sentiment:
                        positive = sentiment['CO-A-02-01']
                        negative = sentiment['CO-A-02-02']
                        net_sentiment = positive - negative

                        # 正确的时间延迟计算
                        data_delay = int((datetime.now() - datetime.strptime(
                            period['startTime'], '%Y-%m-%d %H:%M:%S')).total_seconds() // 60)

                        print(f"✅ 使用情绪数据时间: {period['startTime']} (延迟: {data_delay}分钟)")

                        return {
                            'positive_ratio': positive,
                            'negative_ratio': negative,
                            'net_sentiment': net_sentiment,
                            'data_time': period['startTime'],
                            'data_delay_minutes': data_delay
                        }

                print("❌ 所有时间段数据都为空")
                return None

        return None
    except Exception as e:
        print(f"情绪指标获取失败: {e}")
        return None


def get_market_trend(df):
    """判断市场趋势"""
    try:
        current_price = df['close'].iloc[-1]

        # 多时间框架趋势分析
        trend_short = "上涨" if current_price > df['sma_20'].iloc[-1] else "下跌"
        trend_medium = "上涨" if current_price > df['sma_50'].iloc[-1] else "下跌"

        # MACD趋势
        macd_trend = "bullish" if df['macd'].iloc[-1] > df['macd_signal'].iloc[-1] else "bearish"

        # 综合趋势判断
        if trend_short == "上涨" and trend_medium == "上涨":
            overall_trend = "强势上涨"
        elif trend_short == "下跌" and trend_medium == "下跌":
            overall_trend = "强势下跌"
        else:
            overall_trend = "震荡整理"

        return {
            'short_term': trend_short,
            'medium_term': trend_medium,
            'macd': macd_trend,
            'overall': overall_trend,
            'rsi_level': df['rsi'].iloc[-1]
        }
    except Exception as e:
        print(f"趋势分析失败: {e}")
        return {}


def get_btc_ohlcv_base():
    """共享的核心K线数据获取和技术指标计算函数"""
    try:
        # 获取K线数据
        ohlcv = exchange.fetch_ohlcv(TRADE_CONFIG['symbol'], TRADE_CONFIG['timeframe'],
                                     limit=TRADE_CONFIG['data_points'])

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        # 将UTC时间转换为北京时间（当前系统时间）
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)

        # 计算技术指标
        df = calculate_technical_indicators(df)
        
        return df
    except Exception as e:
        print(f"获取基础K线数据失败: {e}")
        return None


def get_btc_ohlcv_enhanced():
    """增强版：获取BTC K线数据并计算技术指标 - 用于交易机器人"""
    try:
        # 使用共享的基础数据获取函数
        df = get_btc_ohlcv_base()
        if df is None:
            return None

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
            'timeframe': TRADE_CONFIG['timeframe'],
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


def get_current_position():
    """获取当前持仓情况 - OKX版本"""
    try:
        positions = exchange.fetch_positions([TRADE_CONFIG['symbol']])
        
        # 添加调试信息：显示所有持仓数据
        print(f"🔍 获取到的所有持仓数据: {len(positions)}个")
        for i, pos in enumerate(positions):
            contracts = float(pos['contracts']) if pos['contracts'] else 0
            print(f"持仓{i+1}: {pos['symbol']} {pos['side']} {contracts}张 @{pos.get('entryPrice', 'N/A')} PnL:{pos.get('unrealizedPnl', 'N/A')}")

        for pos in positions:
            if pos['symbol'] == TRADE_CONFIG['symbol']:
                contracts = float(pos['contracts']) if pos['contracts'] else 0

                if contracts > 0:
                    return {
                        'side': pos['side'],  # 'long' or 'short'
                        'size': contracts,
                        'entry_price': float(pos['entryPrice']) if pos['entryPrice'] else 0,
                        'unrealized_pnl': float(pos['unrealizedPnl']) if pos['unrealizedPnl'] else 0,
                        'leverage': float(pos['leverage']) if pos['leverage'] else TRADE_CONFIG['leverage'],
                        'symbol': pos['symbol']
                    }

        return None

    except Exception as e:
        print(f"获取持仓失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def safe_json_parse(json_str):
    """安全解析JSON，处理格式不规范的情况"""
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        try:
            # 修复常见的JSON格式问题
            json_str = json_str.replace("'", '"')
            json_str = re.sub(r'(\w+):', r'"\1":', json_str)
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"JSON解析失败，原始内容: {json_str}")
            print(f"错误详情: {e}")
            return None


def create_fallback_signal(price_data):
    """创建备用交易信号"""
    return {
        "signal": "HOLD",
        "reason": "因技术分析暂时不可用，采取保守策略",
        "stop_loss": price_data['price'] * 0.98,  # -2%
        "take_profit": price_data['price'] * 1.02,  # +2%
        "confidence": "LOW",
        "is_fallback": True
    }


def get_btc_ohlcv_for_web():
    """专门为web界面提供的K线数据和技术指标 - 用于Web API"""
    try:
        # 使用共享的基础数据获取函数
        df = get_btc_ohlcv_base()
        if df is None:
            return None

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
            'timeframe': TRADE_CONFIG['timeframe']
        }
        
    except Exception as e:
        print(f"获取Web端K线数据失败: {e}")
        return None


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


def analyze_with_deepseek(price_data):
    """使用DeepSeek分析市场并生成交易信号（增强版）"""

    # 生成技术分析文本
    technical_analysis = generate_technical_analysis_text(price_data)

    # K线数据已包含在技术分析中，无需单独展示

    # 添加上次交易信号
    signal_text = ""
    if signal_history:
        last_signal = signal_history[-1]
        signal_text = f"\n【上次交易信号】\n信号: {last_signal.get('signal', 'N/A')}\n信心: {last_signal.get('confidence', 'N/A')}"

    # 获取最近5次AI分析历史
    recent_ai_analysis = get_recent_ai_analysis(5)
    ai_analysis_history_text = ""
    if recent_ai_analysis:
        ai_analysis_history_text = "\n【最近5次AI分析历史】（供决策参考）\n"
        for i, analysis in enumerate(recent_ai_analysis):
            ai_analysis_history_text += f"{i+1}. {analysis['timestamp']} {analysis['signal']} @${analysis['btc_price']:.2f} ({analysis['confidence']}) [{analysis['position_desc']}] - {analysis['reason']}\n"

    # 获取最近5次交易记录
    recent_trades = get_recent_trades(10)
    trade_history_text = ""
    if recent_trades:
        trade_history_text = "\n【最近10次交易记录】\n"
        for i, trade in enumerate(recent_trades):
            time_str = trade['timestamp'][-8:-3] if len(trade['timestamp']) > 8 else trade['timestamp']
            trade_history_text += f"{i+1}. {time_str} {trade['signal']} @{trade['price']:.2f} ({trade['confidence']}) - {trade['reason']}\n"

    # 移除市场情绪分析，专注MACD信号线和布林带策略
    sentiment_text = ""  # 不使用情绪数据

    # 添加当前持仓信息 - 增强版
    current_pos = get_current_position()
    if current_pos:
        position_side_zh = "多头" if current_pos['side'] == 'long' else "空头"
        pnl_status = "盈利" if current_pos['unrealized_pnl'] > 0 else "亏损" if current_pos['unrealized_pnl'] < 0 else "平衡"
        pnl_percent = (current_pos['unrealized_pnl'] / (current_pos['entry_price'] * current_pos['size'] * TRADE_CONFIG.get('contract_size', 0.01))) * 100 if current_pos['entry_price'] > 0 else 0
        position_text = f"{position_side_zh}持仓 {current_pos['size']:.2f}张 @{current_pos['entry_price']:.2f} ({pnl_status}{current_pos['unrealized_pnl']:.2f}USDT, {pnl_percent:+.2f}%)"
        pnl_text = f", 持仓详情: {position_side_zh}{current_pos['size']:.2f}张，入场价{current_pos['entry_price']:.2f}，{pnl_status}{abs(current_pos['unrealized_pnl']):.2f}USDT"
        
        # 计算与当前价格的差距
        price_diff_percent = ((price_data['price'] - current_pos['entry_price']) / current_pos['entry_price']) * 100
        if current_pos['side'] == 'short':
            price_diff_percent = -price_diff_percent
        position_analysis = f"\n【持仓状态详细分析】\n- 持仓方向: {position_side_zh}\n- 持仓量: {current_pos['size']:.2f}张\n- 入场价: ${current_pos['entry_price']:.2f}\n- 当前价: ${price_data['price']:.2f}\n- 价格变化: {price_diff_percent:+.2f}% ({'有利' if price_diff_percent > 0 else '不利' if price_diff_percent < 0 else '持平'})\n- 盈亏状态: {pnl_status} {abs(current_pos['unrealized_pnl']):.2f} USDT ({pnl_percent:+.2f}%)"
    else:
        position_text = "无持仓"
        pnl_text = ""
        position_analysis = "\n【持仓状态详细分析】\n- 当前无持仓，可根据技术信号开仓"

    prompt = f"""
    你是一个专业的加密货币交易分析师。请基于以下BTC/USDT {TRADE_CONFIG['timeframe']}周期数据进行分析：

    {technical_analysis}

    {signal_text}

    {ai_analysis_history_text}

    {trade_history_text}

    【当前行情】
    - 当前价格: ${price_data['price']:,.2f}
    - 时间: {price_data['timestamp']}
    - 本K线最高: ${price_data['high']:,.2f}
    - 本K线最低: ${price_data['low']:,.2f}
    - 本K线成交量: {price_data['volume']:.2f} BTC
    - 价格变化: {price_data['price_change']:+.2f}%
    - 当前持仓: {position_text}{pnl_text}
    
    {position_analysis}

    【交易策略】
    1. **MACD信号线主导** (70%权重):
       ⚠️ **重要数据质量说明**：
       - 最新的当前MACD值可能存在滞后或不准确
       - 不能仅依赖当前值做判断，必须看历史趋势形态
       - 重点分析前3个数据点的完整趋势形态
       
       ✅ **正确的趋势判断逻辑**：
       - 局部低点已过：前前值 > 前值 < 当前值 (V型反转) → BUY
       - 局部高点已过：前前值 < 前值 > 当前值 (倒V型反转) → SELL
       - 上升趋势延续：前前值 < 前值 < 当前值 → 持续看多
       - 下降趋势延续：前前值 > 前值 > 当前值 → 持续看空
       
       🔍 **关键分析要点**：
       - 优先分析MACD信号线序列中的前3点趋势
       - 寻找明确的V型或倒V型转折形态
       - 当前值仅作为趋势确认，不作为主要判断依据
       
       🚨 **频繁波动检测** (防止过度交易):
       - 检查MACD前10个数据点是否出现频繁上下波动
       - 识别标准：连续出现多次小幅上升下降交替
       - 波动判断：如前10点中出现≥2次方向变化
       - 频繁波动期间 → 强制HOLD，维持现状
       - 等待明确的持续上升或下降趋势再操作
       
       ❌ **错误判断**：仅凭两点比较无法确认趋势转折
       - 错误：-413 → -450 就说"高点已过" ✗
       - 正确：-400 → -500 → -450 才是"低点已过" ✓
    
    2. **布林带确认** (30%权重):
       - 下轨(<20%) + MACD低点已过 → 强买入
       - 上轨(>80%) + MACD高点已过 → 强卖出
       - 冲突时以MACD为准
    
    3. **持仓控制原则**:
       - 无持仓：根据技术信号开仓
       - 有持仓且盈利中：保持持仓，避免过度交易
       - 有持仓且亏损>2%：考虑止损
       - 反向信号：平仓+反向开仓
    
    【当前数据】
    - MACD信号线: {price_data['technical_data'].get('macd_signal', 0):.4f}
    - 布林带位置: {price_data['technical_data'].get('bb_position', 0):.1%}
    
    【核心交易逻辑】
    - 基于MACD信号线识别趋势转折点
    - 费用成本0.05%，确保盈利覆盖成本
    - 避免过度交易，专注高质量信号
    - 检测MACD前10点频繁波动，避免震荡市频繁交易

    【智能持仓决策逻辑】
    0. **频繁波动检测** (最高优先级):
       - 先检查MACD前10点是否存在频繁波动
       - 如检测到频繁波动→强制HOLD，等待趋势明确
       - 只有在明确上升或下降趋势时才允许交易
    
    1. **无持仓状态**：
       - 等待MACD三点确认趋势转折
       - V型反转(局部低点已过)→BUY开多
       - 倒V型反转(局部高点已过)→SELL开空
    
    2. **多头持仓状态分析**：
       - 盈利状态：优先HOLD保护利润，但关注倒V型反转
       - 亏损状态：重点关注是否出现倒V型反转信号
       - 倒V型反转确认→SELL平多开空
       
    3. **空头持仓状态分析**：
       - 盈利状态：优先HOLD保护利润，但关注V型反转  
       - 亏损状态：重点关注是否出现V型反转信号
       - V型反转确认→BUY平空开多
       
    4. **核心交易原则**：
       ✅ 趋势跟随：顺势而为，不逆势操作
       ✅ 盈利保护：持仓盈利时保持耐心，但遇反转信号及时转向
       ✅ 敏感反转：发现反转迹象即果断转向，无需等待明确信号
       ❌ 禁止追涨杀跌：避免在同方向连续加仓
       ❌ 禁止过度交易：震荡市中保持耐心

    【最终决策指导】
    � **第一优先级：频繁波动检测** (防止过度交易)
    - 必须先检查MACD前10个数据点的波动情况
    - 计算前10点中方向变化次数（上升→下降 或 下降→上升）
    - 如方向变化≥2次 → 判定为频繁波动，强制HOLD
    - 频繁波动期间禁止任何BUY/SELL操作
    
    �🚨 **第二优先级：数据质量警告**：当前最新MACD值可能不准确或存在滞后！
    - 重点分析MACD信号线序列中的前3个数据点
    - 寻找完整的V型或倒V型转折形态
    - 不要过度依赖最新的当前值
    
    ⚠️ **重要**：必须基于"MACD前3点趋势形态"做决策，不能仅凭单点或两点数据判断趋势！
    
    决策优先级：
    0. **频繁波动检测** → 强制HOLD (最高优先级)
    1. **V型反转确认** (前3点形成局部低点已过) → BUY
    2. **倒V型反转确认** (前3点形成局部高点已过) → SELL  
    3. **趋势延续** + 持仓盈利 → HOLD
    4. **震荡状态** 或 数据不足 → HOLD观望
    5. **持仓亏损** + 反转确认 → 转向操作
    
    ❌ **禁止错误分析**：
    - 不能说"-413→-450是高点已过"
    - 必须前3点确认：如-400→-500→-450才是"低点已过"
    - 不能仅依赖当前值做判断，要看历史形态
    
    请用以下JSON格式回复：
    {{
        "signal": "BUY|SELL|HOLD",
        "reason": "决策理由：1)首先检查MACD前10点频繁波动情况 2)如无频繁波动则分析前3点趋势形态 3)识别V型/倒V型/延续/震荡 4)说明是否因频繁波动强制HOLD",
        "stop_loss": 具体价格,
        "take_profit": 具体价格, 
        "confidence": "HIGH|MEDIUM|LOW"
    }}
    """

    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[
                {"role": "system",
                 "content": f"您是一位专业的量化交易分析师，专注于{TRADE_CONFIG['timeframe']}周期的趋势跟随策略。核心原则：1)持仓盈利时保持耐心但遇反转迹象及时转向 2)发现反转迹象即果断行动，无需等待明确信号 3)避免过度交易和追涨杀跌。请严格按照JSON格式输出决策。"},
                {"role": "user", "content": prompt}
            ],
            stream=False,
            temperature=0.1
        )

        # 安全解析JSON
        result = response.choices[0].message.content
        print(f"DeepSeek原始回复: {result}")

        # 提取JSON部分
        start_idx = result.find('{')
        end_idx = result.rfind('}') + 1

        if start_idx != -1 and end_idx != 0:
            json_str = result[start_idx:end_idx]
            signal_data = safe_json_parse(json_str)

            if signal_data is None:
                signal_data = create_fallback_signal(price_data)
        else:
            signal_data = create_fallback_signal(price_data)

        # 验证必需字段
        required_fields = ['signal', 'reason', 'stop_loss', 'take_profit', 'confidence']
        if not all(field in signal_data for field in required_fields):
            signal_data = create_fallback_signal(price_data)

        # 保存信号到历史记录
        signal_data['timestamp'] = price_data['timestamp']
        signal_history.append(signal_data)
        if len(signal_history) > 30:
            signal_history.pop(0)

        # 信号统计
        signal_count = len([s for s in signal_history if s.get('signal') == signal_data['signal']])
        total_signals = len(signal_history)
        print(f"信号统计: {signal_data['signal']} (最近{total_signals}次中出现{signal_count}次)")

        # 信号连续性检查
        if len(signal_history) >= 3:
            last_three = [s['signal'] for s in signal_history[-3:]]
            if len(set(last_three)) == 1:
                print(f"⚠️ 注意：连续3次{signal_data['signal']}信号")

        return signal_data

    except Exception as e:
        print(f"DeepSeek分析失败: {e}")
        return create_fallback_signal(price_data)


def execute_intelligent_trade(signal_data, price_data):
    """执行智能交易 - OKX版本（支持同方向加仓减仓）"""
    global position

    current_position = get_current_position()

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

    # 计算智能仓位
    position_size = calculate_intelligent_position(signal_data, price_data, current_position)

    print(f"交易信号: {signal_data['signal']}")
    print(f"信心程度: {signal_data['confidence']}")
    print(f"智能仓位: {position_size:.2f} 张")
    print(f"理由: {signal_data['reason']}")
    print(f"当前持仓: {current_position}")

    # 风险管理
    if signal_data['confidence'] == 'LOW' and not TRADE_CONFIG['test_mode']:
        print("⚠️ 低信心信号，跳过执行")
        return

    if TRADE_CONFIG['test_mode']:
        print("测试模式 - 仅模拟交易")
        return

    try:
        # 执行交易逻辑 - 支持同方向加仓减仓
        if signal_data['signal'] == 'BUY':
            if current_position and current_position['side'] == 'short':
                # 先检查空头持仓是否真实存在且数量正确
                if current_position['size'] > 0:
                    print(f"平空仓 {current_position['size']:.2f} 张并开多仓 {position_size:.2f} 张...")
                    # 平空仓
                    response1 = exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'buy',
                        current_position['size'],
                        params={'reduceOnly': True, 'tag': '60bb4a8d3416BCDE'}
                    )
                    save_trade_log("平空仓", 'buy', current_position['size'], response1)
                    time.sleep(1)
                    # 开多仓
                    response2 = exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'buy',
                        position_size,
                        params={'tag': '60bb4a8d3416BCDE'}
                    )
                    save_trade_log("开多仓", 'buy', position_size, response2)
                else:
                    print("⚠️ 检测到空头持仓但数量为0，直接开多仓")
                    response = exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'buy',
                        position_size,
                        params={'tag': '60bb4a8d3416BCDE'}
                    )
                    save_trade_log("开多仓", 'buy', position_size, response)

            elif current_position and current_position['side'] == 'long':
                # 同方向，检查是否需要调整仓位
                size_diff = position_size - current_position['size']

                if abs(size_diff) >= 0.01:  # 有可调整的差异
                    if size_diff > 0:
                        # 加仓
                        add_size = round(size_diff, 2)
                        print(
                            f"多仓加仓 {add_size:.2f} 张 (当前:{current_position['size']:.2f} → 目标:{position_size:.2f})")
                        response = exchange.create_market_order(
                            TRADE_CONFIG['symbol'],
                            'buy',
                            add_size,
                            params={'tag': '60bb4a8d3416BCDE'}
                        )
                        save_trade_log("多仓加仓", 'buy', add_size, response)
                    else:
                        # 减仓
                        reduce_size = round(abs(size_diff), 2)
                        print(
                            f"多仓减仓 {reduce_size:.2f} 张 (当前:{current_position['size']:.2f} → 目标:{position_size:.2f})")
                        response = exchange.create_market_order(
                            TRADE_CONFIG['symbol'],
                            'sell',
                            reduce_size,
                            params={'reduceOnly': True, 'tag': '60bb4a8d3416BCDE'}
                        )
                        save_trade_log("多仓减仓", 'sell', reduce_size, response)
                else:
                    print(
                        f"已有多头持仓，仓位合适保持现状 (当前:{current_position['size']:.2f}, 目标:{position_size:.2f})")
                    return  # 保持现状，不记录交易
            else:
                # 无持仓时开多仓
                print(f"开多仓 {position_size:.2f} 张...")
                response = exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'buy',
                    position_size,
                    params={'tag': '60bb4a8d3416BCDE'}
                )
                save_trade_log("开多仓", 'buy', position_size, response)

        elif signal_data['signal'] == 'SELL':
            if current_position and current_position['side'] == 'long':
                # 先检查多头持仓是否真实存在且数量正确
                if current_position['size'] > 0:
                    print(f"平多仓 {current_position['size']:.2f} 张并开空仓 {position_size:.2f} 张...")
                    # 平多仓
                    response1 = exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'sell',
                        current_position['size'],
                        params={'reduceOnly': True, 'tag': '60bb4a8d3416BCDE'}
                    )
                    save_trade_log("平多仓", 'sell', current_position['size'], response1)
                    time.sleep(1)
                    # 开空仓
                    response2 = exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'sell',
                        position_size,
                        params={'tag': '60bb4a8d3416BCDE'}
                    )
                    save_trade_log("开空仓", 'sell', position_size, response2)
                else:
                    print("⚠️ 检测到多头持仓但数量为0，直接开空仓")
                    response = exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'sell',
                        position_size,
                        params={'tag': '60bb4a8d3416BCDE'}
                    )
                    save_trade_log("开空仓", 'sell', position_size, response)

            elif current_position and current_position['side'] == 'short':
                # 同方向，检查是否需要调整仓位
                size_diff = position_size - current_position['size']

                if abs(size_diff) >= 0.01:  # 有可调整的差异
                    if size_diff > 0:
                        # 加仓
                        add_size = round(size_diff, 2)
                        print(
                            f"空仓加仓 {add_size:.2f} 张 (当前:{current_position['size']:.2f} → 目标:{position_size:.2f})")
                        response = exchange.create_market_order(
                            TRADE_CONFIG['symbol'],
                            'sell',
                            add_size,
                            params={'tag': '60bb4a8d3416BCDE'}
                        )
                        save_trade_log("空仓加仓", 'sell', add_size, response)
                    else:
                        # 减仓
                        reduce_size = round(abs(size_diff), 2)
                        print(
                            f"空仓减仓 {reduce_size:.2f} 张 (当前:{current_position['size']:.2f} → 目标:{position_size:.2f})")
                        response = exchange.create_market_order(
                            TRADE_CONFIG['symbol'],
                            'buy',
                            reduce_size,
                            params={'reduceOnly': True, 'tag': '60bb4a8d3416BCDE'}
                        )
                        save_trade_log("空仓减仓", 'buy', reduce_size, response)
                else:
                    print(
                        f"已有空头持仓，仓位合适保持现状 (当前:{current_position['size']:.2f}, 目标:{position_size:.2f})")
                    return  # 保持现状，不记录交易
            else:
                # 无持仓时开空仓
                print(f"开空仓 {position_size:.2f} 张...")
                response = exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'sell',
                    position_size,
                    params={'tag': '60bb4a8d3416BCDE'}
                )
                save_trade_log("开空仓", 'sell', position_size, response)

        elif signal_data['signal'] == 'HOLD':
            print("建议观望，不执行交易")
            return

        print("智能交易执行成功")
        time.sleep(2)
        position = get_current_position()
        print(f"更新后持仓: {position}")
        
        # 保存交易记录（只有实际执行交易才会到达这里）
        try:
            # 计算实际盈亏（如果有持仓）
            pnl = 0
            if current_position and position:
                # 如果方向改变或平仓，计算盈亏
                if current_position['side'] != position.get('side'):
                    if current_position['side'] == 'long':
                        pnl = (price_data['price'] - current_position['entry_price']) * current_position['size'] * TRADE_CONFIG.get('contract_size', 0.01)
                    else:
                        pnl = (current_position['entry_price'] - price_data['price']) * current_position['size'] * TRADE_CONFIG.get('contract_size', 0.01)
            
            # 计算手续费 (按0.05%计算交易金额的手续费)
            trade_value = price_data['price'] * position_size * TRADE_CONFIG.get('contract_size', 0.01)
            fee = trade_value * 0.0005  # 0.05% taker费率
            
            trade_record = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'signal': signal_data['signal'],
                'price': price_data['price'],
                'amount': position_size,
                'confidence': signal_data['confidence'],
                'reason': signal_data['reason'],
                'pnl': pnl,
                'fee': round(fee, 6)  # 手续费，保留6位小数
            }
            save_trade_record(trade_record)
            print("✅ 交易记录已保存")
        except Exception as e:
            print(f"保存交易记录失败: {e}")

    except Exception as e:
        print(f"交易执行失败: {e}")

        # 如果是持仓不存在的错误，尝试直接开新仓
        if "don't have any positions" in str(e):
            print("尝试直接开新仓...")
            try:
                if signal_data['signal'] == 'BUY':
                    response = exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'buy',
                        position_size,
                        params={'tag': '60bb4a8d3416BCDE'}
                    )
                    save_trade_log("重试开多仓", 'buy', position_size, response)
                elif signal_data['signal'] == 'SELL':
                    response = exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'sell',
                        position_size,
                        params={'tag': '60bb4a8d3416BCDE'}
                    )
                    save_trade_log("重试开空仓", 'sell', position_size, response)
                print("直接开仓成功")
            except Exception as e2:
                print(f"直接开仓也失败: {e2}")

        import traceback
        traceback.print_exc()


def analyze_with_deepseek_with_retry(price_data, max_retries=2):
    """带重试的DeepSeek分析"""
    for attempt in range(max_retries):
        try:
            signal_data = analyze_with_deepseek(price_data)
            if signal_data and not signal_data.get('is_fallback', False):
                return signal_data

            print(f"第{attempt + 1}次尝试失败，进行重试...")
            time.sleep(1)

        except Exception as e:
            print(f"第{attempt + 1}次尝试异常: {e}")
            if attempt == max_retries - 1:
                return create_fallback_signal(price_data)
            time.sleep(1)

    return create_fallback_signal(price_data)



def trading_bot():
    """主交易机器人函数"""

    print("\n" + "=" * 60)
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 获取增强版K线数据
    price_data = get_btc_ohlcv_enhanced()
    if not price_data:
        print("❌ 获取K线数据失败，跳过本次执行")
        return False  # 返回False表示本次执行失败，但进程继续运行

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
    current_position = get_current_position()
    position_info = None
    if current_position:
        position_info = {
            'side': current_position['side'],
            'size': current_position['size'],
            'entry_price': current_position['entry_price'],
            'unrealized_pnl': current_position['unrealized_pnl']
        }

    # 4. 使用DeepSeek分析（带重试）
    signal_data = analyze_with_deepseek_with_retry(price_data)

    if signal_data.get('is_fallback', False):
        print("⚠️ 使用备用交易信号")

    # 5. 保存AI分析历史记录
    try:
        analysis_record = {
            'signal': signal_data['signal'],
            'confidence': signal_data['confidence'],
            'reason': signal_data['reason'],
            'stop_loss': signal_data['stop_loss'],
            'take_profit': signal_data['take_profit'],
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

    # 6. 更新系统状态到Web界面
    try:
        update_system_status(
            status='running',
            account_info=account_info,
            btc_info={
                'price': price_data['price'],
                'change': price_data['price_change'],
                'timeframe': TRADE_CONFIG['timeframe'],
                'mode': '全仓-单向'
            },
            position=position_info,
            ai_signal={
                'signal': signal_data['signal'],
                'confidence': signal_data['confidence'],
                'reason': signal_data['reason'],
                'stop_loss': signal_data['stop_loss'],
                'take_profit': signal_data['take_profit']
            }
        )
        print("✅ 系统状态已更新到Web界面")
    except Exception as e:
        print(f"更新系统状态失败: {e}")

    # 7. 执行智能交易
    execute_intelligent_trade(signal_data, price_data)


def main():
    """主函数"""
    print("BTC/USDT OKX自动交易机器人启动成功！")
    print("融合技术指标策略 + OKX实盘接口")

    if TRADE_CONFIG['test_mode']:
        print("当前为模拟模式，不会真实下单")
    else:
        print("实盘交易模式，请谨慎操作！")

    print(f"交易周期: {TRADE_CONFIG['timeframe']} (每1分钟执行策略)")
    print("已启用完整技术指标分析和持仓跟踪功能")

    # 设置交易所
    if not setup_exchange():
        print("交易所初始化失败，程序退出")
        return
    
    # 初始化Web界面数据文件
    print("🌐 初始化Web界面数据...")
    try:
        # 获取初始账户信息
        balance = exchange.fetch_balance()
        initial_account = {
            'balance': float(balance['USDT'].get('free', 0)),
            'equity': float(balance['USDT'].get('total', 0)),
            'leverage': TRADE_CONFIG['leverage']
        }
        
        # 获取当前BTC价格
        ticker = exchange.fetch_ticker(TRADE_CONFIG['symbol'])
        initial_btc = {
            'price': float(ticker['last']),
            'change': float(ticker['percentage']) if ticker.get('percentage') else 0,
            'timeframe': TRADE_CONFIG['timeframe'],
            'mode': '全仓-单向'
        }
        
        # 获取当前持仓
        current_pos = get_current_position()
        initial_position = None
        if current_pos:
            initial_position = {
                'side': current_pos['side'],
                'size': current_pos['size'],
                'entry_price': current_pos['entry_price'],
                'unrealized_pnl': current_pos['unrealized_pnl']
            }
        
        # 初始化系统状态
        update_system_status(
            status='running',
            account_info=initial_account,
            btc_info=initial_btc,
            position=initial_position,
            ai_signal={
                'signal': 'HOLD',
                'confidence': 'N/A',
                'reason': '系统启动中，等待首次分析...',
                'stop_loss': 0,
                'take_profit': 0
            }
        )
        print("✅ Web界面数据初始化完成")
    except Exception as e:
        print(f"⚠️ Web界面数据初始化失败: {e}")
        print("继续运行，将在首次交易时创建数据")

    print("执行频率: 每1分钟执行一次")

    # 循环执行（简化逻辑，避免冲突）
    while True:
        try:
            # 直接调用交易机器人，函数内部会处理等待逻辑
            result = trading_bot()
            
            # 如果执行成功，等待一段时间再检查
            if result is not False:
                print("✅ 本次交易分析执行完成，等待下一次执行...")
                time.sleep(60)  # 每1分钟检查一次
            else:
                # 如果执行失败，等待更长时间再重试
                print("⚠️ 本次执行失败，等待1分钟后重试...")
                time.sleep(60)  # 1分钟后重试
                
        except Exception as e:
            print(f"交易机器人执行异常: {e}")
            # 异常后等待一段时间再重试
            time.sleep(60)  # 1分钟后重试


if __name__ == "__main__":
    main()