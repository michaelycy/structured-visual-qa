#!/usr/bin/env bash
# 一键启动前后端开发环境。
#
# 用法：
#   ./scripts/dev.sh            # 前端(5180) + 后端(8765) 同时启动
#   ./scripts/dev.sh stop       # 停止本脚本启动的进程
#
# 行为：
# - 后端：.venv/bin/document-qa-server --port 8765
# - 前端：cd frontend && bun run dev（Vite 5180，/api 已代理到 8765）
# - 复用已运行的实例：端口已被占用时跳过启动并提示，避免重复进程
# - Ctrl-C 同时结束两端；进程号写入 tmp/dev.pids 供 stop 使用
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$ROOT/tmp/dev.pids"
BACKEND_PORT=8765
FRONTEND_PORT=5180

mkdir -p "$ROOT/tmp"

port_alive() { # 判断端口是否已有服务在监听
  curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$1" && return 0 || return 1
}

stop_all() {
  if [[ -f "$PIDFILE" ]]; then
    while read -r pid name; do
      if kill "$pid" 2>/dev/null; then
        echo "已停止 $name (pid $pid)"
      fi
    done < "$PIDFILE"
    rm -f "$PIDFILE"
  else
    echo "没有找到 pid 记录（tmp/dev.pids）；可手动 kill 进程"
  fi
}

cleanup() { # 前台退出（Ctrl-C/异常）时带走所有子进程
  trap - EXIT INT TERM
  [[ -f "$PIDFILE" ]] && stop_all
  exit 0
}

if [[ "${1:-}" == "stop" ]]; then
  stop_all
  exit 0
fi

BACKEND_PID=""
FRONTEND_PID=""

if port_alive $BACKEND_PORT; then
  echo "后端 $BACKEND_PORT 端口已有服务在运行，跳过启动"
else
  # --reload：开发模式热更新（server/core 源码变更自动重启进程）。
  "$ROOT/.venv/bin/document-qa-server" --port $BACKEND_PORT --reload &
  BACKEND_PID=$!
  echo "后端已启动 (pid $BACKEND_PID, http://127.0.0.1:$BACKEND_PORT, 热更新开启)"
fi

if port_alive $FRONTEND_PORT; then
  echo "前端 $FRONTEND_PORT 端口已有服务在运行，跳过启动"
else
  (cd "$ROOT/frontend" && exec bun run dev) &
  FRONTEND_PID=$!
  echo "前端已启动 (pid $FRONTEND_PID, http://127.0.0.1:$FRONTEND_PORT)"
fi

[[ -n "$BACKEND_PID" || -n "$FRONTEND_PID" ]] || {
  echo "前后端均已在运行，无需操作。"
  exit 0
}

# 记录 pid 供 stop 子命令使用（沿用旧记录，追加新实例）。
{
  [[ -f "$PIDFILE" ]] && cat "$PIDFILE"
  [[ -n "$BACKEND_PID" ]] && echo "$BACKEND_PID backend"
  [[ -n "$FRONTEND_PID" ]] && echo "$FRONTEND_PID frontend"
} > "$PIDFILE"

# 等待两端就绪后给出访问入口（最多 30s，超时不阻塞）。
for _ in $(seq 1 30); do
  port_alive $BACKEND_PORT && port_alive $FRONTEND_PORT && break
  sleep 1
done

trap cleanup EXIT INT TERM
echo ""
echo "✓ 就绪：打开 http://127.0.0.1:$FRONTEND_PORT 使用界面（Ctrl-C 停止全部）"

wait
