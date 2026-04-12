FROM python:3.11-slim

WORKDIR /app

# Install nginx + curl
RUN apt-get update && apt-get install -y nginx curl && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Make start script executable
RUN chmod +x /app/start.sh

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=15s \
  CMD curl -f http://localhost:${PORT:-8080}/manifest.json || exit 1

CMD ["/app/start.sh"]
