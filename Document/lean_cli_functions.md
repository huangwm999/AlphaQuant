# Lean CLI 完整功能分析

## 🔧 项目管理
```bash
# 创建新项目
lean create-project "我的策略"

# 删除项目
lean delete-project "我的策略"

# 查看项目状态
lean whoami
```

## 📊 本地开发和测试
```bash
# 本地回测
lean backtest "项目名"

# 参数优化
lean optimize "项目名"

# 生成报告
lean report
```

## ☁️ 云端同步
```bash
# 登录/登出
lean login
lean logout

# 云端同步
lean cloud pull
lean cloud push

# 云端回测
lean cloud backtest "项目名"
```

## 🔬 研究环境
```bash
# 启动 Jupyter 研究环境
lean research "项目名"

# 查看日志
lean logs
```

## 📈 数据管理
```bash
# 下载数据
lean data download

# 生成自定义数据
lean data generate
```

## ⚙️ 配置管理
```bash
# 配置设置
lean config list
lean config set key value
lean config get key
```

## 🏭 实盘交易
```bash
# 本地实盘
lean live "项目名"

# 云端实盘
lean cloud live "项目名"
```

## 🔒 安全功能
```bash
# 加密项目
lean encrypt "项目名"

# 解密项目
lean decrypt "项目名"
```

## 📚 库管理
```bash
# 添加自定义库
lean library add "库名"

# 移除库
lean library remove "库名"
```

## 🖥️ GUI 界面
```bash
# 启动本地GUI
lean gui
```