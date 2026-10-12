#!/bin/bash
# QuantPilot 后端启动器：崩溃后自动重启，保证服务持续可用。
# KMP_DUPLICATE_LIB_OK 修复 macOS 上 xgboost/lightgbm 同时加载 libomp 导致的崩溃。
export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
cd "$(dirname "$0")" || exit 1
PORT="${PORT:-8000}"
while true; do
  echo "[run_api] starting uvicorn on :$PORT $(date '+%F %T')"
  .venv/bin/python -u .venv/bin/uvicorn server.app:app --port "$PORT" --log-level warning
  code=$?
  echo "[run_api] exited (code $code) $(date '+%F %T'); restarting in 3s..."
  sleep 3
done
