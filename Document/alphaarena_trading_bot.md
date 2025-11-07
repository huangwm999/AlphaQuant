# AlphaArena BTC 交易机器人

## 项目概述

AlphaArena 是一个基于 AI 的 BTC/USDT 自动交易机器人，结合了 DeepSeek AI 市场分析和 OKX 交易所的实盘交易功能。

## 核心特性

### 🤖 AI 驱动分析
- **DeepSeek AI**: 使用先进的语言模型进行市场分析
- **多维度分析**: 结合技术指标、市场情绪和价格走势
- **智能信号生成**: 生成 BUY/SELL/HOLD 交易信号

### 📊 技术指标分析
- **移动平均线**: SMA5, SMA20, SMA50
- **动量指标**: RSI, MACD
- **波动率指标**: 布林带
- **成交量分析**: 成交量比率

### 🎯 智能仓位管理
- **动态仓位**: 根据信心程度调整仓位大小
- **风险控制**: 最大仓位比例限制
- **趋势适应**: 考虑市场趋势强度

### 🔄 自动化交易
- **OKX 交易所**: 支持永续合约交易
- **全仓模式**: 单向持仓策略
- **杠杆交易**: 10倍杠杆配置

## 系统架构

### 核心组件
```
AlphaArena/
├── deepseekok2.py      # 主交易机器人
├── web_app.py          # Web 监控界面
├── data_manager.py     # 数据管理模块
├── env_trading.sh      # 环境变量设置
└── screen_start.sh     # 多进程启动脚本
```

### 工作流程
1. **数据获取**: 从 OKX 获取 BTC/USDT 15分钟 K线数据
2. **技术分析**: 计算各种技术指标和市场趋势
3. **AI 分析**: 使用 DeepSeek 生成交易信号
4. **仓位计算**: 根据信号和风险参数计算仓位大小
5. **交易执行**: 在 OKX 执行相应的交易操作
6. **状态更新**: 保存交易记录并更新 Web 界面

## 技术栈

- **编程语言**: Python 3.10
- **AI 服务**: DeepSeek API
- **交易所接口**: OKX API (ccxt 库)
- **数据处理**: pandas, numpy
- **Web 界面**: Flask
- **部署工具**: screen (多进程管理)

## 配置参数

### 交易配置
```python
TRADE_CONFIG = {
    'symbol': 'BTC/USDT:USDT',  # 交易对
    'leverage': 10,             # 杠杆倍数
    'timeframe': '15m',         # 时间周期
    'data_points': 96,          # 数据点数 (24小时)
}
```

### 仓位管理
```python
'position_management': {
    'base_usdt_amount': 100,        # 基础投入金额
    'high_confidence_multiplier': 1.5,  # 高信心倍数
    'max_position_ratio': 10,       # 最大仓位比例
}
```

## 安装和运行

### 环境准备
```bash
# 激活虚拟环境
source myenv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 配置 API 密钥
编辑 `env_trading.sh` 文件：
```bash
DEEPSEEK_API_KEY="your_deepseek_key"
OKX_API_KEY="your_okx_key"
OKX_SECRET="your_okx_secret"
OKX_PASSWORD="your_trading_password"
```

### 启动服务
```bash
# 方式1：使用 screen 脚本
./screen_start.sh

# 方式2：手动启动
source env_trading.sh
python AlphaArena/web_app.py    # 终端1：Web界面
python AlphaArena/deepseekok2.py # 终端2：交易机器人
```

## 监控和维护

### Web 界面
访问 `http://127.0.0.1:8003` 查看：
- 实时 BTC 价格和趋势
- 当前持仓状态
- AI 分析信号
- 交易历史记录
- 系统性能指标

### 日志监控
```bash
# 查看交易日志
tail -f AlphaArena/*.log

# 使用 screen 查看进程
screen -ls
screen -rd AlphaArena
```

## 风险控制

### 安全措施
- **测试模式**: 可在 `TRADE_CONFIG['test_mode']` 中启用
- **账户验证**: 启动时检查账户模式和余额
- **错误处理**: 网络异常和 API 错误的自动重试
- **仓位限制**: 防止过度集中投资

### 风险参数
- 最大单次仓位: 总资金的 10%
- 止损设置: 基于 AI 分析的动态止损
- 杠杆控制: 固定 10 倍杠杆

## 性能监控

### 关键指标
- **胜率**: 交易成功率统计
- **盈亏比**: 平均盈利/平均亏损
- **最大回撤**: 历史最大亏损幅度
- **夏普比率**: 风险调整后收益

### 数据记录
- 每笔交易的详细记录
- AI 分析决策过程
- 市场条件和信号强度
- 实盘执行结果

## 故障排除

### 常见问题
1. **API 密钥错误**: 检查 `env_trading.sh` 中的密钥配置
2. **账户模式问题**: 确保 OKX 账户支持合约交易
3. **网络连接**: 检查网络连接和 API 可用性
4. **余额不足**: 确认账户有足够的 USDT 余额

### 调试模式
```python
# 启用详细日志
TRADE_CONFIG['debug'] = True

# 查看 API 响应
print(f"Balance: {balance}")
print(f"Position: {position}")
```

## 扩展开发

### 添加新指标
在 `calculate_technical_indicators()` 函数中添加新的技术指标计算。

### 自定义策略
修改 `analyze_with_deepseek()` 函数中的 AI 分析提示。

### 新数据源
扩展 `get_btc_ohlcv_enhanced()` 函数支持更多数据源。

## 版本历史

- **v1.0**: 基础 AI 交易功能
- **v1.1**: 添加智能仓位管理
- **v1.2**: 集成 Web 监控界面
- **v1.3**: 优化错误处理和重试机制

## 许可证

本项目仅供学习和研究使用，请勿用于实盘交易而未经充分测试。