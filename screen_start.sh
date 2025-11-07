#!/bin/bash
# AlphaArena Screen 启动脚本
# 参考: ../AIAgents/docker/4_screen_start.sh
# 使用方法: ./screen_start.sh [-f|--force]

# 配置区域 - 在此处定义窗口和对应的命令
SESSION_NAME="AlphaArena"
BASE_DIR="./"

export DEEPSEEK_API_KEY
export OKX_API_KEY
export OKX_SECRET
export OKX_PASSWORD

# 定义窗口名称和对应的命令
declare -A WINDOWS
WINDOWS["web"]="cd $BASE_DIR && source myenv/bin/activate && python AlphaArena/web_app2.py"
WINDOWS["trading"]="cd $BASE_DIR && source env_trading.sh && source myenv/bin/activate && python AlphaArena/deepseekok3.py && echo 'End'"
WINDOWS["monitor"]="cd $BASE_DIR && source myenv/bin/activate && echo '🔍 监控窗口 - 按 Ctrl+C 退出' && python -c 'import time; [print(f\"监控中... {time.strftime(\"%H:%M:%S\")}\", end=\"\\r\") or time.sleep(1) for _ in range(999999)]'"
WINDOWS["logs"]="cd $BASE_DIR && tail -f AlphaArena/*.log 2>/dev/null || echo '暂无日志文件'"

# 定义窗口启动顺序
WINDOW_ORDER=("web" "trading" "monitor" "logs")

# 解析参数：支持 -f 或 --force 跳过确认
FORCE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--force)
            FORCE=1
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [-f|--force]"
            echo "  -f, --force    强制重启，不询问确认"
            echo "  -h, --help     显示帮助信息"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            echo "使用 -h 查看帮助"
            exit 1
            ;;
    esac
done

# 检查虚拟环境
if [ ! -d "$BASE_DIR/myenv" ]; then
    echo "❌ 错误: 未找到虚拟环境 $BASE_DIR/myenv"
    exit 1
fi

# 检查现有会话
if screen -list | grep -q "$SESSION_NAME"; then
    echo "发现现有会话: $SESSION_NAME"
    if [[ $FORCE -eq 1 ]]; then
        echo "强制模式已启用：终止现有会话并重新启动"
        screen -S $SESSION_NAME -X quit
        sleep 1
    else
        read -p "是否终止现有会话并重新启动? (y/N): " confirm
        if [[ $confirm =~ ^[Yy]$ ]]; then
            echo "终止现有会话: $SESSION_NAME"
            screen -S $SESSION_NAME -X quit
            sleep 1
        else
            echo "操作已取消，保持现有会话"
            exit 0
        fi
    fi
fi

echo "创建 Screen 会话: $SESSION_NAME"

# 按指定顺序创建窗口
first_window=${WINDOW_ORDER[0]}

# 创建第一个窗口
echo "创建窗口: $first_window"
screen -dmS $SESSION_NAME -t $first_window bash -c "${WINDOWS[$first_window]}; exec bash"

# 创建其余窗口
for ((i=1; i<${#WINDOW_ORDER[@]}; i++)); do
    window=${WINDOW_ORDER[$i]}
    echo "创建窗口: $window"
    screen -S $SESSION_NAME -X screen -t $window bash -c "${WINDOWS[$window]}; exec bash"
    sleep 0.5
done

# 返回到第一个窗口
screen -S $SESSION_NAME -X select 0

echo "✅ Screen 会话 '$SESSION_NAME' 创建成功!"
echo ""
echo "📋 窗口说明:"
echo "  web      - Web界面 (http://127.0.0.1:8003)"
echo "  trading  - 交易机器人"
echo "  monitor  - 系统监控"
echo "  logs     - 日志查看"
echo ""
echo "🔗 连接命令:"
echo "  screen -rd $SESSION_NAME          # 连接到会话"
echo "  screen -rd $SESSION_NAME -p 0     # 直接进入Web窗口"
echo ""
echo "🎮 Screen 快捷键:"
echo "  Ctrl+A D    # 脱离会话"
echo "  Ctrl+A K    # 杀死当前窗口"
echo "  Ctrl+A N/P  # 切换到下一个/上一个窗口"
echo "  Ctrl+A \"    # 窗口列表"
echo ""
echo "当前 screen 会话列表:"
screen -ls
