FROM python:3.11-slim

WORKDIR /app

# 系统依赖（匹配 HF 模板，额外加 g++ 确保 scipy/statsmodels 可编译）
RUN apt-get update && apt-get install -y \
    git \
    git-lfs \
    ffmpeg \
    libsm6 \
    libxext6 \
    cmake \
    rsync \
    libgl1 \
    g++ \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/* \
    && git lfs install

# 安装 Python 依赖（完全由 requirements.txt 控制，无额外追加）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# Streamlit 端口（HF 会设置 PORT 环境变量，默认 8501）
EXPOSE 8501

CMD sh -c "streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0"
