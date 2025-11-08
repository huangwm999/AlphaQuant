#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略决策模块
从 deepseekok3.py 重构分离出来的AI策略决策功能
"""

import json
import re
from datetime import datetime
from openai import OpenAI


class StrategyAnalyzer:
    """策略分析器类 - 负责AI策略决策"""
    
    def __init__(self, deepseek_client):
        """初始化策略分析器
        
        Args:
            deepseek_client: DeepSeek AI客户端
        """
        self.deepseek_client = deepseek_client
    
    def safe_json_parse(self, json_str):
        """安全解析JSON字符串"""
        try:
            return json.loads(json_str)
        except:
            try:
                # 尝试修复常见的JSON格式问题
                json_str = re.sub(r',\s*}', '}', json_str)  # 移除末尾逗号
                json_str = re.sub(r',\s*]', ']', json_str)  # 移除末尾逗号
                return json.loads(json_str)
            except:
                return None

    def create_fallback_signal(self, price_data):
        """创建回退信号，当AI分析失败时使用"""
        return {
            "signal": "HOLD",
            "reason": "AI分析失败，采用保守策略",
            "stop_loss": price_data['price'] * 0.98,
            "take_profit": price_data['price'] * 1.02,
            "confidence": "LOW",
            "timestamp": datetime.now().isoformat(),
            "is_fallback": True
        }

    def analyze_with_deepseek(self, price_data, generate_technical_analysis_text, get_recent_ai_analysis, get_recent_trades, signal_history):
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

        # 支撑阻力分析
        support_resistance_text = ""
        if 'levels_analysis' in price_data:
            levels = price_data['levels_analysis']
            support_resistance_text = f"\n【支撑阻力分析】\n支撑位: ${levels['support']:.2f} (距离: {levels['distance_to_support']:.1f}%)\n阻力位: ${levels['resistance']:.2f} (距离: {levels['distance_to_resistance']:.1f}%)"

        # 趋势分析
        trend_text = ""
        if 'trend_analysis' in price_data:
            trend = price_data['trend_analysis']
            trend_text = f"\n【趋势分析】\n趋势: {trend['trend']}\n强度: {trend['strength']}"

        prompt = f"""你是一个专业的比特币量化交易分析师。请分析当前市场数据并给出交易决策。

【当前市场数据】
BTC价格: ${price_data['price']:,.2f} USDT
价格变化: {price_data.get('price_change', 0):+.2f}%
时间周期: {price_data['timeframe']}
数据时间: {price_data['timestamp']}

【技术分析数据】{technical_analysis}

{support_resistance_text}

{trend_text}

{signal_text}

{ai_analysis_history_text}

{trade_history_text}

【分析要求】
1. 综合技术指标（MACD、布林带、RSI等）进行判断
2. 考虑支撑阻力位和趋势状态
3. 参考历史交易记录，避免频繁反转
4. 重点关注MACD信号线变化趋势
5. 布林带位置作为超买超卖参考

【决策输出】
请严格按照以下JSON格式输出，不要添加任何其他文字：

{{
  "signal": "BUY/SELL/HOLD",
  "confidence": "HIGH/MEDIUM/LOW", 
  "reason": "详细的分析原因",
  "stop_loss": 数值,
  "take_profit": 数值,
  "timestamp": "{datetime.now().isoformat()}"
}}

注意：
- signal必须是BUY、SELL或HOLD之一
- confidence表示信心程度：HIGH(高信心)、MEDIUM(中等信心)、LOW(低信心)
- reason要具体说明技术分析依据
- stop_loss和take_profit设置合理的止损止盈位
- 严格按照JSON格式，确保可以被程序解析
"""

        try:
            print("🤖 正在调用DeepSeek AI分析...")
            
            response = self.deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system", 
                        "content": "你是专业的量化交易分析师，专门分析比特币市场。你必须严格按照JSON格式输出交易决策，不能有任何格式错误。"
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            ai_response = response.choices[0].message.content.strip()
            print(f"🤖 DeepSeek原始响应: {ai_response[:200]}...")

            # 尝试从响应中提取JSON
            json_match = re.search(r'\{.*?\}', ai_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                signal_data = self.safe_json_parse(json_str)
                
                if signal_data and all(key in signal_data for key in ['signal', 'confidence', 'reason']):
                    # 验证signal字段
                    if signal_data['signal'] not in ['BUY', 'SELL', 'HOLD']:
                        print(f"⚠️ 无效的信号值: {signal_data['signal']}")
                        return self.create_fallback_signal(price_data)
                    
                    # 验证confidence字段
                    if signal_data['confidence'] not in ['HIGH', 'MEDIUM', 'LOW']:
                        print(f"⚠️ 无效的信心值: {signal_data['confidence']}")
                        signal_data['confidence'] = 'MEDIUM'  # 设置默认值
                    
                    # 设置默认的止损止盈（如果没有）
                    if 'stop_loss' not in signal_data or not isinstance(signal_data['stop_loss'], (int, float)):
                        signal_data['stop_loss'] = price_data['price'] * 0.98
                        
                    if 'take_profit' not in signal_data or not isinstance(signal_data['take_profit'], (int, float)):
                        signal_data['take_profit'] = price_data['price'] * 1.02

                    signal_data['timestamp'] = datetime.now().isoformat()
                    signal_data['ai_response'] = ai_response
                    signal_data['is_fallback'] = False
                    
                    print(f"✅ DeepSeek分析成功: {signal_data['signal']} ({signal_data['confidence']})")
                    return signal_data
                else:
                    print("❌ JSON数据格式不完整")
                    print(f"解析结果: {signal_data}")
            else:
                print("❌ 响应中未找到有效JSON")
                print(f"完整响应: {ai_response}")

        except Exception as e:
            print(f"❌ DeepSeek API调用失败: {e}")

        # 如果所有尝试都失败，返回保守的HOLD信号
        print("🔄 使用回退信号")
        return self.create_fallback_signal(price_data)

    def analyze_market_strategy(self, price_data, generate_technical_analysis_text, get_recent_ai_analysis, get_recent_trades, signal_history, max_retries=2):
        """带重试的DeepSeek策略分析 - 对外接口"""
        for attempt in range(max_retries + 1):
            try:
                signal_data = self.analyze_with_deepseek(price_data, generate_technical_analysis_text, get_recent_ai_analysis, get_recent_trades, signal_history)
                
                if signal_data and not signal_data.get('is_fallback', False):
                    print(f"✅ DeepSeek分析成功 (尝试 {attempt + 1}/{max_retries + 1})")
                    return signal_data
                elif attempt < max_retries:
                    print(f"⚠️ 第 {attempt + 1} 次尝试失败，重试中...")
                    continue
                    
            except Exception as e:
                print(f"❌ 第 {attempt + 1} 次尝试异常: {e}")
                if attempt < max_retries:
                    print(f"🔄 重试中... ({attempt + 1}/{max_retries})")
                    continue
        
        print("❌ 所有重试都失败，使用回退信号")
        return self.create_fallback_signal(price_data)


# 为了保持向后兼容性，提供旧接口的包装函数
def analyze_with_deepseek_with_retry(deepseek_client, price_data, generate_technical_analysis_text, get_recent_ai_analysis, get_recent_trades, signal_history, max_retries=2):
    """向后兼容的包装函数"""
    analyzer = StrategyAnalyzer(deepseek_client)
    return analyzer.analyze_market_strategy(price_data, generate_technical_analysis_text, get_recent_ai_analysis, get_recent_trades, signal_history, max_retries)