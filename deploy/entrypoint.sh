#!/bin/sh
set -eu

INTERNAL_PORT=8000
PUBLIC_PORT="${PORT:-8080}"

# 1) 持久卷挂载会盖掉镜像里的 /data，目录必须运行时创建
mkdir -p /data/uploads/materials

# 2) 生成 nginx 配置（apt 版 nginx 没有 envsubst 钩子，用 sed 最稳）
mkdir -p /etc/nginx/conf.d
rm -f /etc/nginx/sites-enabled/default
sed "s|__PUBLIC_PORT__|${PUBLIC_PORT}|g" /app/deploy/nginx.conf.template \
    > /etc/nginx/conf.d/default.conf

# 2.1) 鉴权：AUTH_ENABLED=true 时由应用内登录页负责，跳过 Basic Auth；
#      否则沿用 AUTH_USER/AUTH_PASSWORD 的 Basic Auth；都未设置则保持公开。
AUTH_CONF=/etc/nginx/taskradar-auth.conf
: > "$AUTH_CONF"
if [ "${AUTH_ENABLED:-false}" = "true" ]; then
    echo "[entrypoint] 已启用应用内登录，跳过 Basic Auth"
elif [ -n "${AUTH_USER:-}" ] && [ -n "${AUTH_PASSWORD:-}" ]; then
    if command -v openssl >/dev/null 2>&1; then
        printf '%s:%s\n' "$AUTH_USER" "$(openssl passwd -apr1 "$AUTH_PASSWORD")" \
            > /etc/nginx/.htpasswd
        chmod 640 /etc/nginx/.htpasswd
        printf 'auth_basic "TaskRadar";\nauth_basic_user_file /etc/nginx/.htpasswd;\n' \
            > "$AUTH_CONF"
        echo "[entrypoint] 已启用 Basic Auth"
    else
        echo "[entrypoint] 未找到 openssl，跳过 Basic Auth"
    fi
else
    echo "[entrypoint] 未设置鉴权，站点保持公开"
fi

# 3) 后端单 worker：SQLite 写串行，多 worker 会让演示数据重复播种
cd /app/backend
uvicorn app.main:app --host 127.0.0.1 --port "${INTERNAL_PORT}" \
        --workers 1 --proxy-headers &
BACKEND_PID=$!

# 4) 等后端就绪（最多 60s）
i=0
while [ "$i" -lt 60 ]; do
    if curl -fsS "http://127.0.0.1:${INTERNAL_PORT}/api/health" >/dev/null 2>&1; then
        break
    fi
    i=$((i + 1))
    sleep 1
done

# 5) 空库自动播种演示数据：免费平台磁盘重置后仍可演示，无需人工点按钮
if curl -fsS "http://127.0.0.1:${INTERNAL_PORT}/api/demo/status" 2>/dev/null \
        | grep -q '"seeded":true'; then
    echo "[entrypoint] 演示数据已存在，跳过播种"
else
    echo "[entrypoint] 空库，执行演示数据播种"
    curl -fsS -X POST "http://127.0.0.1:${INTERNAL_PORT}/api/demo/seed?refresh=false" \
        >/dev/null || echo "[entrypoint] 播种失败，跳过（不阻塞启动）"
fi

# 6) nginx 当前台主进程；后端异常退出时随之退出，交给编排重启
( sleep 3; while kill -0 "$BACKEND_PID" 2>/dev/null; do sleep 5; done
  echo "[entrypoint] 后端已退出，关闭 nginx"; nginx -s quit ) &

exec nginx -g 'daemon off;'
