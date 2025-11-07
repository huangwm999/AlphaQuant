# QuantConnect 数据配置修复指南

## 问题分析
您遇到的问题是 Docker 容器内的数据路径映射不正确。需要在启动时明确指定数据源。

## 解决方案

### 方法1：修改启动命令（推荐）
```bash
cd /home/SSD1/AIQuantConnect/Project
source ../myenv/bin/activate

# 使用本地数据提供商启动
lean research "Pensive Green kitten" \
  --data-provider-historical local \
  --port 8888
```

### 方法2：直接在 Jupyter 中测试数据访问
在启动的 Jupyter 中运行：

```python
import os
import pandas as pd
from datetime import datetime

# 检查数据路径
data_path = "/Lean/Data"
print(f"Data directory exists: {os.path.exists(data_path)}")
if os.path.exists(data_path):
    print("Contents:", os.listdir(data_path))

# 尝试直接读取 SPY 数据
spy_path = "/Lean/Data/equity/usa/minute/spy"
if os.path.exists(spy_path):
    print(f"SPY data exists: {os.listdir(spy_path)}")
```

### 方法3：在 Jupyter 中手动创建数据
```python
# 创建测试数据
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# 生成测试数据
dates = pd.date_range(start='2023-01-01', end='2024-01-01', freq='D')
prices = 100 + np.cumsum(np.random.randn(len(dates)) * 0.5)

df = pd.DataFrame({
    'close': prices,
    'open': prices + np.random.randn(len(dates)) * 0.1,
    'high': prices + np.abs(np.random.randn(len(dates)) * 0.2),
    'low': prices - np.abs(np.random.randn(len(dates)) * 0.2),
    'volume': np.random.randint(1000000, 10000000, len(dates))
}, index=dates)

# 计算布林带
window = 20
df['sma'] = df['close'].rolling(window=window).mean()
df['std'] = df['close'].rolling(window=window).std()
df['upper_band'] = df['sma'] + (2 * df['std'])
df['lower_band'] = df['sma'] - (2 * df['std'])

# 绘制布林带
plt.figure(figsize=(12, 6))
plt.plot(df.index, df['close'], label='Close Price', linewidth=1)
plt.plot(df.index, df['sma'], label='SMA(20)', color='red')
plt.plot(df.index, df['upper_band'], label='Upper Band', color='green', linestyle='--')
plt.plot(df.index, df['lower_band'], label='Lower Band', color='green', linestyle='--')
plt.fill_between(df.index, df['upper_band'], df['lower_band'], alpha=0.1, color='green')
plt.title("Bollinger Bands - Test Data")
plt.legend()
plt.grid(True)
plt.show()
```

## 数据路径检查
当前您的环境中数据应该在：
- 本地：`/home/SSD1/AIQuantConnect/Project/data/`
- Docker内：`/Lean/Data/`

映射可能有问题，需要确认 Docker 的卷挂载是否正确。