#!/usr/bin/env python
"""
start_backend.py - 本地一键启动后端（Windows / Mac / Linux 都能直接跑）

做的事情:
1. 检查 .env 是否存在，不存在就从 .env.example 复制一份
2. 检查 chroma_data / bge_model 目录，不存在就创建
3. 用 uvicorn 启动 FastAPI（默认 http://127.0.0.1:8000）

用法:
    cd toutiao_backend
    python start_backend.py            # 正常启动
    python start_backend.py --port 8001  # 改端口
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def ensure_dotenv() -> None:
    env_file = ROOT / ".env"
    example = ROOT / ".env.example"
    if not env_file.exists() and example.exists():
        shutil.copy(example, env_file)
        print(f"[init] 未找到 .env，已从 .env.example 复制一份: {env_file}")
        print("       请打开 .env 填入 DATABASE_URL / REDIS / LLM_API_KEY 等配置后重新启动。")
        raise SystemExit(0)


def ensure_dirs() -> None:
    for name in ["chroma_data", "vector_store/bge_model", "test_reports/allure-results"]:
        p = ROOT / name
        p.mkdir(parents=True, exist_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="本地一键启动 Toutiao Backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--reload", action="store_true", help="开发模式自动重载")
    args = parser.parse_args()

    ensure_dotenv()
    ensure_dirs()

    cmd = [
        sys.executable, "-m", "uvicorn", "main:app",
        "--host", args.host,
        "--port", str(args.port),
        "--workers", str(args.workers),
        "--log-level", "info",
    ]
    if args.reload:
        cmd.append("--reload")
        # reload 模式不支持多 worker
        cmd = [c for c in cmd if not c.startswith("--workers") and not c.isdigit() or c != str(args.workers)]

    print(f"[start] 执行: {' '.join(cmd)}")
    print(f"[start] 后端地址: http://{args.host}:{args.port}")
    print(f"[start] Swagger 文档: http://{args.host}:{args.port}/docs")
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
