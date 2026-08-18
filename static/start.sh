#!/bin/bash

# ==================== 启动脚本模板 ====================
# 变量会在部署时被替换:
#   APP_NAME  -> 服务名称
#   APP_JAR   -> JAR 文件名
#   APP_DIR   -> 服务目录

APP="APP_NAME"
DIR="APP_DIR"
APP_JAR="$DIR/APP_NAME.jar"
LOG="$DIR/logs/console.log"
PIDF="$DIR/app.pid"

# 创建日志目录
mkdir -p "$DIR/logs"

echo ""
echo "=== $APP ==="

# 通过 PID 文件停止旧进程
if [ -f "$PIDF" ]; then
    OP=$(cat "$PIDF")
    if kill -0 $OP 2>/dev/null; then
        echo -e "  Stopping PID:$OP"
        kill $OP 2>/dev/null
        sleep 3
        kill -0 $OP 2>/dev/null && kill -9 $OP 2>/dev/null
    fi
    rm -f "$PIDF"
fi

# 通过进程名停止旧进程
PID=$(ps aux | grep "java -jar" | grep "$APP_JAR" | grep -v grep | awk '{print $2}')
if [ -n "$PID" ]; then
    echo -e "  Stopping process PID:$PID"
    kill $PID 2>/dev/null
    sleep 2
    kill -0 $PID 2>/dev/null && kill -9 $PID 2>/dev/null
fi

# 启动服务
echo -e "  Starting..."
cd "$DIR"

# 构建启动参数
JAVA_OPTS=""

# 检查是否有外部配置文件（支持多种格式）
CONFIG_FILE_YML="$DIR/application.yml"
CONFIG_FILE_YAML="$DIR/application.yaml"
CONFIG_FILE_PROPERTIES="$DIR/application.properties"

if [ -f "$CONFIG_FILE_YML" ]; then
    JAVA_OPTS="--spring.config.location=file:$CONFIG_FILE_YML"
    echo -e "  Using config: $CONFIG_FILE_YML"
elif [ -f "$CONFIG_FILE_YAML" ]; then
    JAVA_OPTS="--spring.config.location=file:$CONFIG_FILE_YAML"
    echo -e "  Using config: $CONFIG_FILE_YAML"
elif [ -f "$CONFIG_FILE_PROPERTIES" ]; then
    JAVA_OPTS="--spring.config.location=file:$CONFIG_FILE_PROPERTIES"
    echo -e "  Using config: $CONFIG_FILE_PROPERTIES"
else
    echo -e "  No external config found, using jar internal config"
    # 使用 Spring Boot 默认配置，指定激活的 profile 为 prod
    JAVA_OPTS="--spring.profiles.active=prod"
fi

# 启动服务，将输出重定向到日志文件
nohup java -jar "$APP_JAR" $JAVA_OPTS > "$LOG" 2>&1 &
NP=$!
echo $NP > "$PIDF"

# 等待启动完成
sleep 5

# 检查进程是否存在
if kill -0 $NP 2>/dev/null; then
    echo -e "  SUCCESS (PID:$NP)"
    exit 0
else
    # 进程已退出，检查日志
    echo -e "  FAILED"
    echo -e "  Last 20 lines of log:"
    tail -20 "$LOG"
    exit 1
fi