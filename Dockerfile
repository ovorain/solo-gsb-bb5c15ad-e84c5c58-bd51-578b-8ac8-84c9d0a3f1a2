FROM python:3.11-slim

# 必要配置：时区与 Python 运行环境
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

# 先复制依赖清单以利用 Docker 层缓存完成依赖安装
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app ./app

EXPOSE 8000

# 容器启动即完成依赖校验与应用初始化（ASGI 应用加载到 uvicorn 工作进程）
CMD ["sh", "-c", "python -c 'import fastapi, uvicorn, pydantic' && exec python -m uvicorn app.main:app --host ${HOST} --port ${PORT}"]
