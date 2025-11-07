# QuantConnect 开发工作流程

## 🔄 推荐的混合开发模式

### 第1步：本地开发环境
```bash
# 在本地VS Code中开发
git init
git add .
git commit -m "初始化量化策略"
```

### 第2步：代码同步到云端
```bash
# 推送到QuantConnect
lean cloud push

# 或者推送特定项目
lean cloud push --project "Adaptable Sky Blue Jackal"
```

### 第3步：云端回测
- 在QuantConnect网站进行专业回测
- 使用真实数据验证策略
- 分析风险指标

### 第4步：结果同步回本地
```bash
# 拉取云端修改
lean cloud pull

# 提交到Git
git add .
git commit -m "更新回测结果"
git push origin main
```

## 🛠️ 开发工具配置

### VS Code 扩展推荐：
- Python
- Jupyter
- GitLens
- Python Docstring Generator
- Pylance

### Git 工作流：
```bash
# 功能分支开发
git checkout -b feature/new-strategy
git add .
git commit -m "添加新策略"
git push origin feature/new-strategy

# 合并到主分支
git checkout main
git merge feature/new-strategy
```

## 📊 数据处理策略

### 本地数据（开发阶段）：
- 使用样本数据快速开发
- 本地Docker环境测试基础逻辑

### 云端数据（验证阶段）：
- 真实市场数据回测
- 性能和风险分析
- 实盘前验证

## 🚀 部署流程

1. **本地开发** → VS Code + Git
2. **本地测试** → Docker + 样本数据  
3. **云端验证** → QuantConnect + 真实数据
4. **实盘部署** → 云端自动交易

这样既保持了本地开发的高效性，又获得了云端数据的专业性。

## 📋 Lean CLI 完整功能列表

### 🚀 项目管理
```bash
# 创建新项目
lean create-project "My Strategy"

# 删除项目（本地+云端）
lean delete-project "My Strategy"

# 初始化Lean环境
lean init

# 查看当前登录用户
lean whoami

# 登录/登出
lean login
lean logout
```

### 🔬 本地开发与测试
```bash
# 本地回测（使用Docker）
lean backtest "My Strategy"

# 参数优化
lean optimize "My Strategy"

# 生成回测报告
lean report

# 查看日志
lean logs
```

### 🌐 云端操作
```bash
# 云端回测
lean cloud backtest "My Strategy"

# 云端优化
lean cloud optimize "My Strategy"

# 项目同步
lean cloud pull
lean cloud push

# 查看云端状态
lean cloud status
```

### 🔧 环境配置
```bash
# 配置选项
lean config list
lean config set <key> <value>
lean config get <key>

# 数据下载/生成
lean data download
lean data generate
```

### 🐳 Docker 相关
```bash
# 研究环境
lean research "My Strategy"

# 实时交易
lean live "My Strategy"

# 构建自定义LEAN镜像
lean build
```

### 🔐 安全功能
```bash
# 加密项目
lean encrypt "My Strategy" --key encryption.key

# 解密项目
lean decrypt "My Strategy" --key encryption.key
```

### 📚 库管理
```bash
# 添加自定义库
lean library add "MyLibrary"

# 移除库
lean library remove "MyLibrary"
```

### 🎛️ GUI界面
```bash
# 启动本地GUI界面
lean gui
```

### 🗄️ 对象存储
```bash
# 管理对象存储
lean object-store list
lean object-store delete <key>
```