# ---------- 阶段 1：构建前端 ----------
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# build 脚本 = tsc --noEmit && vite build，类型错误会在这里失败
RUN npm run build

# ---------- 阶段 2：运行时 ----------
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# opencv 需要 libGL/libglib，onnxruntime 需要 libgomp，缺一个启动即崩
RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx curl openssl libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/ ./backend/

COPY --from=frontend /build/dist /usr/share/nginx/html
COPY deploy/nginx.conf.template /app/deploy/nginx.conf.template
COPY deploy/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV APP_ENV=production \
    HOST=127.0.0.1 \
    DATABASE_PATH=/data/taskradar.db \
    MATERIAL_UPLOAD_DIR=/data/uploads/materials \
    APP_TIMEZONE=Asia/Shanghai \
    MAX_UPLOAD_MB=10

VOLUME ["/data"]
EXPOSE 8080
WORKDIR /app/backend
CMD ["/app/entrypoint.sh"]
