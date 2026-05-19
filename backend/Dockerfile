FROM python:3.11-slim

WORKDIR /app

# 安裝編譯 psycopg2 所需的依賴
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製後端所有檔案
COPY . .

# 注意：如果需要讀取父目錄的 course_summary.md，建議透過 docker-compose mount
# 或者在此處手動複製 (但 build context 必須包含它)

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
