#!/usr/bin/env bash
# 单条命令启动：自动安装依赖（首次运行）、初始化并启动应用。
# 用法: ./start.sh
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON:-python3}"
VENV_DIR=".venv"
export PORT="${PORT:-8000}"
export HOST="${HOST:-0.0.0.0}"

# 依赖安装：优先使用项目内虚拟环境，首次运行时自动创建并安装
if [ ! -d "$VENV_DIR" ]; then
    echo "[start.sh] 首次运行：创建虚拟环境 $VENV_DIR ..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if ! python -c "import fastapi, uvicorn, pydantic" 2>/dev/null; then
    echo "[start.sh] 安装依赖 requirements.txt ..."
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
fi

echo "[start.sh] 启动圆桌座位优化 API: http://${HOST}:${PORT}"
echo "[start.sh] 接口文档: http://${HOST}:${PORT}/docs"

# 应用初始化：以 app.main:app 为入口启动 uvicorn
exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
