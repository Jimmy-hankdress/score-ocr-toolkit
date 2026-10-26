# ScoreOCR Toolkit - Dockerfile
# 多階段建置：建置階段 + 執行階段

# ============================================================
# 建置階段
# ============================================================
FROM python:3.11-slim AS builder

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴 (建置時需要)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libopencv-dev \
    && rm -rf /var/lib/apt/lists/*

# 建立虛擬環境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 升級 pip 並安裝建構工具
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 複製需求檔案並安裝 Python 依賴
COPY requirements.txt requirements-homr.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-homr.txt || echo "HOMR install failed, continuing..."

# ============================================================
# 執行階段
# ============================================================
FROM python:3.11-slim AS runtime

# 設定環境變數
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    SCOREOCR_HOST=0.0.0.0 \
    SCOREOCR_PORT=8000 \
    SCOREOCR_MAX_UPLOAD_MB=50 \
    SCOREOCR_LOG_LEVEL=INFO

# 安裝執行時系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1-mesa-glx \
    libopencv-core4.10 \
    libopencv-imgproc4.10 \
    libopencv-imgcodecs4.10 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 從建置階段複製虛擬環境
COPY --from=builder /opt/venv /opt/venv

# 建立非 root 使用者
RUN groupadd -r appuser && useradd -r -g appuser appuser
WORKDIR /app

# 複製應用程式碼
COPY --chown=appuser:appuser . .

# 建立必要目錄並設定權限
RUN mkdir -p uploads processed static && \
    chown -R appuser:appuser uploads processed static

# 切換到非 root 使用者
USER appuser

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 暴露端口
EXPOSE 8000

# 啟動命令
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]