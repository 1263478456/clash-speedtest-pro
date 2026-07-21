FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gzip \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download mihomo
RUN mkdir -p /app/mihomo && \
    wget -q https://github.com/MetaCubeX/mihomo/releases/download/v1.19.28/mihomo-linux-amd64-v1.19.28.gz -O /tmp/mihomo.gz && \
    gzip -d /tmp/mihomo.gz && \
    mv /tmp/mihomo /app/mihomo/mihomo && \
    chmod +x /app/mihomo/mihomo && \
    rm -f /tmp/mihomo.gz

# Copy application
COPY app.py config.py ./
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Create directories
RUN mkdir -p /app/data /app/results && \
    chmod -R 777 /app

EXPOSE 8080

CMD ["python", "app.py"]
