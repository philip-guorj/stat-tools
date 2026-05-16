#!/bin/sh
# StatTools Docker 启动脚本
# 在 Streamlit 启动前完成初始化

# 确保 billing.db 可通过 /app/billing.db 访问（实际存储于 /app/data/billing.db）
if [ ! -L /app/billing.db ]; then
    ln -sf /app/data/billing.db /app/billing.db 2>/dev/null || true
fi

# 确保数据目录存在
mkdir -p /app/data /app/logs 2>/dev/null || true

# 使 app 目录可写（SQLite WAL 模式需要在该目录下创建 journal 文件）
chmod 777 /app 2>/dev/null || true

# 启动 Streamlit
exec streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true
