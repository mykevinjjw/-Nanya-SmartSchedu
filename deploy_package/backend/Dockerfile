# 使用輕量級 Python 映像檔
FROM python:3.11-slim

# 安裝系統依賴（PostgreSQL 連線所需）
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# 設定工作目錄
WORKDIR /app

# 複製依賴清單並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製後端原始碼
COPY . .

# 暴露 API 端口
EXPOSE 9000

# 啟動後端伺服器
CMD ["python", "main.py"]
