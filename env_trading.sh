#!/bin/bash

echo "========================================"
echo "  AlphaArena 环境变量设置脚本"
echo "========================================"

# ========================================
# 请在此处填写您的 API 密钥
# ========================================

DEEPSEEK_API_KEY="sk-"
OKX_API_KEY="735e2d0d-"
OKX_SECRET="0834DF"
OKX_PASSWORD="Qua"

# ========================================
# 设置环境变量
# ========================================

export DEEPSEEK_API_KEY
export OKX_API_KEY
export OKX_SECRET
export OKX_PASSWORD

echo "✅ 环境变量已设置:"
echo "   DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY:0:10}..."
echo "   OKX_API_KEY: ${OKX_API_KEY:0:10}..."
echo "   OKX_SECRET: ${OKX_SECRET:0:10}..."
echo "   OKX_PASSWORD: [已设置]"
echo ""
echo "💡 使用方法:"
echo "   source env_trading.sh  # 在当前终端设置环境变量"
echo "   ./env_trading.sh       # 在子进程中设置（不推荐）"