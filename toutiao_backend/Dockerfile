# =============================================================================
# Dockerfile — Toutiao Backend
# 构建命令:   docker build -t toutiao-backend .
# 启动命令:   docker run --rm -p 8000:8000 --env-file .env toutiao-backend
# =============================================================================

FROM python:3.10-slim

# 设置时区（日志时间按北京时间显示）
ENV TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

# 系统依赖（aiomysql / chromadb / onnxruntime 需要的基础库）
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gcc \
        g++ \
        libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# 先拷贝 requirements，利用 Docker layer 缓存，避免每次都重新 pip install
COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# 拷贝业务代码
COPY . .

# 健康检查（云平台会用这个判断是否就绪）
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/ || exit 1

EXPOSE 8000

# 启动：多 workers 提升吞吐；单 worker 也能跑
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]
