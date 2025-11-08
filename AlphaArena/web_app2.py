# -*- coding: utf-8 -*-

from flask import Flask, jsonify, request, make_response
from flask_cors import CORS
import os
import json
from datetime import datetime, timedelta
from data_manager import data_manager
from deepseekok3 import exchange, TRADE_CONFIG

app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)
app.secret_key = ''

USERNAME = 'quant'
PASSWORD = 'quant@2025'

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if data.get('username') == USERNAME and data.get('password') == PASSWORD:
        return jsonify({'success': True, 'username': USERNAME})
    return jsonify({'success': False, 'msg': '用户名或密码错误'}), 401

@app.route('/api/system-status', methods=['GET'])
def get_system_status():
    return jsonify(data_manager.get_system_status())

@app.route('/api/trade-history', methods=['GET'])
def get_trade_history():
    return jsonify(data_manager.get_trade_history())

@app.route('/api/ai-analysis-history', methods=['GET'])
def get_ai_analysis():
    # 获取分页参数
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 10, type=int)
    
    # 获取所有数据
    all_data = data_manager.get_ai_analysis_history()
    
    # 计算分页
    total_count = len(all_data)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    # 按时间倒序排列（最新的在前面）
    sorted_data = sorted(all_data, key=lambda x: x.get('timestamp', ''), reverse=True)
    
    # 获取当前页数据
    page_data = sorted_data[start_idx:end_idx]
    
    return jsonify({
        'data': page_data,
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total_count': total_count,
            'total_pages': (total_count + page_size - 1) // page_size,
            'has_next': end_idx < total_count,
            'has_prev': page > 1
        }
    })

@app.route('/api/performance', methods=['GET'])
def get_performance():
    return jsonify(data_manager.get_performance())

@app.route('/api/technical-chart', methods=['GET'])
def get_technical_chart_data():
    """获取K线和技术指标数据 - 使用deepseekok3.py的公共函数"""
    try:
        # 导入deepseekok3模块
        import sys
        sys.path.append(os.path.dirname(__file__))
        
        # 尝试导入deepseekok3的公共函数和依赖
        try:
            from market_data import get_btc_ohlcv_for_web
            from technical_analysis import calculate_technical_indicators, get_sentiment_indicators, calculate_integrated_trading_score
            from deepseekok3 import exchange, TRADE_CONFIG
            print("✅ 成功导入deepseekok3的公共函数")
        except ImportError as e:
            print(f"❌ 导入deepseekok3失败: {e}")
            # 如果导入失败，回退到本地实现
            return jsonify({'error': '无法导入交易引擎模块'}), 500
        
        # 解析可选的 days 参数（默认2天）来动态控制数据窗口大小
        try:
            days = int(request.args.get('days', 2))
        except Exception:
            days = 2
        days = max(1, min(days, 30))  # 安全边界：1~30天

        def tf_to_minutes(tf: str) -> int:
            try:
                tf = (tf or '').lower().strip()
                if tf.endswith('m'):
                    return max(int(tf[:-1]), 1)
                if tf.endswith('h'):
                    return max(int(tf[:-1]) * 60, 1)
                if tf.endswith('d'):
                    return max(int(tf[:-1]) * 60 * 24, 1)
            except Exception:
                pass
            return 15

        # 使用deepseekok3的公共函数获取数据
        try:
            # 使用共享函数获取数据和指标
            # 根据 days 计算需要的K线数量（以timeframe为步长）
            tf_minutes = tf_to_minutes(TRADE_CONFIG.get('timeframe', '15m'))
            per_day_bars = max(int((24 * 60) / tf_minutes), 1)
            data_points = int(days * per_day_bars) + 2  # 加2根缓冲

            # 构建局部配置，避免修改全局 TRADE_CONFIG
            local_config = dict(TRADE_CONFIG)
            local_config['data_points'] = min(max(data_points, 10), 2000)

            web_data = get_btc_ohlcv_for_web(
                exchange, local_config,
                calculate_technical_indicators, get_sentiment_indicators, calculate_integrated_trading_score
            )
            if not web_data:
                return jsonify({'error': '无法获取市场数据'}), 500
            
            df = web_data['dataframe']
            sentiment_info = web_data['sentiment']
            current_price = web_data['current_price']
            timeframe = web_data['timeframe']
            
            # 获取交易决策数据
            decision_signals = []
            kline_count = len(df)
            
            try:
                # 初始化决策信号数组
                decision_signals = [0] * kline_count
                print(f"初始化决策信号数组，长度: {kline_count}")
                
                # 获取交易记录并匹配到K线数据
                trade_history = data_manager.get_trade_history()
                
                if trade_history and len(trade_history) > 0:
                    print(f"找到 {len(trade_history)} 条交易记录，开始匹配...")
                    print(f"K线时间范围: {df['timestamp'].min()} 到 {df['timestamp'].max()}")
                    
                    import pandas as pd
                    import numpy as np
                    
                    # 准备交易数据
                    trade_times = []
                    trade_signals = []
                    
                    for trade in trade_history:
                        try:
                            trade_time_str = trade.get('timestamp', '')
                            if not trade_time_str:
                                continue
                            trade_time = pd.to_datetime(trade_time_str)
                            signal = trade.get('signal', 'HOLD')
                            signal_value = 1 if signal == 'BUY' else -1 if signal == 'SELL' else 0
                            
                            trade_times.append(trade_time)
                            trade_signals.append(signal_value)
                        except:
                            continue
                    
                    if trade_times:
                        # 创建交易DataFrame
                        trade_df = pd.DataFrame({
                            'trade_time': trade_times,
                            'signal': trade_signals
                        })
                        
                        # 根据时间周期动态设置匹配容忍度（默认回退15分钟）并强制向后对齐（backward）
                        tol_minutes = tf_to_minutes(timeframe) if 'timeframe' in locals() else 15

                        # 方案更新：改用K线【开盘时间】进行对齐，消除“延时显示”
                        # 解释：
                        #  - 以前使用 close_time(backward) 会导致：
                        #    * 在一根K线进行中（trade_time 位于 open 和 close 之间），因尚未到 close_time，无法匹配到该K线 -> 显示延时
                        #    * trade_time 恰好等于下一根 open，会归到上一根（视觉上也显得“落后一根”）
                        #  - 现在使用 open_time(backward)：
                        #    * 任意 trade_time ∈ [open_i, open_{i+1}) 将匹配到 index=i，实时归属当前正在走的K线
                        #    * trade_time == open_{i+1} 将归于新开的一根 index=i+1，更符合直觉
                        kline_df = df[['timestamp']].copy().reset_index()

                        matched = pd.merge_asof(
                            trade_df.sort_values('trade_time'),
                            kline_df.sort_values('timestamp'),
                            left_on='trade_time',
                            right_on='timestamp',
                            tolerance=pd.Timedelta(minutes=tol_minutes),
                            direction='backward'
                        )
                        
                        # 设置决策信号
                        matched_count = 0
                        for _, row in matched.iterrows():
                            if pd.notna(row['index']):  # 有匹配的K线
                                decision_signals[int(row['index'])] = row['signal']
                                matched_count += 1
                                print(f"交易匹配: {row['trade_time']} 归属开盘 {row['timestamp']} -> 索引 {int(row['index'])}, 信号 {row['signal']}")
                        
                        print(f"决策信号匹配完成，匹配成功: {matched_count}/{len(trade_df)} 条交易")
                    else:
                        print("没有有效的交易时间数据")
                else:
                    print("没有交易记录，使用默认决策信号")
                    
            except Exception as e:
                print(f"处理交易决策数据失败: {e}")
                decision_signals = [0] * kline_count
            
            # 准备返回数据 - 统一时间格式
            klines_data = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
            klines_data['timestamp'] = klines_data['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
            
            chart_data = {
                # K线数据
                'klines': klines_data.to_dict('records'),
                
                # 技术指标数据
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
                    'scores': df['score'].fillna(0).tolist(),
                    'decisions': decision_signals
                },
                
                # 时间标签
                'labels': [ts.strftime('%H:%M') for ts in df['timestamp']],
                
                # 当前数据
                'current': {
                    'price': current_price,
                    'timeframe': timeframe,
                    'days': days,
                    'current_score': float(df['score'].iloc[-1]),
                    'score_trend': 'bullish' if df['score'].iloc[-1] > 0 else 'bearish' if df['score'].iloc[-1] < 0 else 'neutral',
                    'latest_decision': decision_signals[-1] if decision_signals else 0
                },
                
                # 市场情绪数据
                'sentiment': sentiment_info
            }
            
            return jsonify(chart_data)
            
        except Exception as exchange_error:
            print(f"获取交易所数据失败: {exchange_error}")
            return jsonify({'error': f'无法获取市场数据: {str(exchange_error)}'}), 500
        
    except Exception as e:
        print(f"获取技术图表数据失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/backtest', methods=['POST'])
def run_backtest_api():
    """回测接口：默认回测最近2天，15分钟级别。可选传参 days, interval, strategy_version。"""
    try:
        # 延迟导入，避免循环依赖
        from backtest import run_backtest

        data = request.get_json(silent=True) or {}
        days = int(data.get('days', 2))
        interval = data.get('interval', '15m')
        strategy_version = data.get('strategy_version', 'strategy_decision_v2')

        result = run_backtest(days=days, interval=interval, strategy_version=strategy_version)
        if 'error' in result:
            return jsonify(result), 500
        return jsonify(result)
    except Exception as e:
        print(f"回测执行失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/strategy-config', methods=['GET'])
def get_strategy_config():
    """获取策略配置"""
    try:
        import os
        config_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'strategy_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return jsonify(config)
    except Exception as e:
        print(f"获取策略配置失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/strategy-config/live', methods=['GET'])
def get_live_strategy():
    """获取当前实时交易使用的策略版本"""
    try:
        import os
        config_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'strategy_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        live_trading = config.get('live_trading', {})
        
        # 查找对应版本的详细信息
        version = live_trading.get('version', 'strategy_decision_v2')
        available = config.get('available_versions', [])
        version_info = next((v for v in available if v['version'] == version), None)
        
        return jsonify({
            'version': version,
            'name': version_info.get('name', '未知策略') if version_info else '未知策略',
            'description': version_info.get('description', '') if version_info else '',
            'last_updated': live_trading.get('last_updated', '')
        })
    except Exception as e:
        print(f"获取实时策略版本失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # 处理表单登录
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == USERNAME and password == PASSWORD:
            # 登录成功，返回JavaScript重定向
            return '''
            <script>
                localStorage.setItem('isLoggedIn', 'true');
                localStorage.setItem('username', '{}');
                window.location.href = '/dashboard';
            </script>
            '''.format(username)
        else:
            # 登录失败，重新显示登录页面并显示错误
            error_message = "用户名或密码错误"
    else:
        error_message = None
    
    try:
        file_path = os.path.join(os.path.dirname(__file__), 'templates', 'login.html')
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 如果有错误，在页面中显示
        if error_message:
            content = content.replace('{% if error %}', '<!-- if error -->')
            content = content.replace('{{ error }}', error_message)
            content = content.replace('{% endif %}', '<!-- endif -->')
        else:
            # 移除错误显示部分
            import re
            content = re.sub(r'{% if error %}.*?{% endif %}', '', content, flags=re.DOTALL)
        
        response = make_response(content)
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        return response
    except Exception as e:
        return f"错误: {str(e)}", 500

@app.route('/dashboard', methods=['GET'])
def dashboard():
    try:
        file_path = os.path.join(os.path.dirname(__file__), 'templates', 'antd-index.html')
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        response = make_response(content)
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        return response
    except Exception as e:
        return f"错误: {str(e)}", 500


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 0, 'msg': 'API正常', 'data': {'service': 'AlphaArena', 'version': '2.0'}})

if __name__ == '__main__':
    print(f"🚀 AlphaArena Web服务启动 - http://172.16.0.252:8003/")
    app.run(host='0.0.0.0', port=8003, debug=True, threaded=True)
