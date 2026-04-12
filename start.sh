#!/bin/sh
# Replace __PORT__ placeholder with actual $PORT (Render sets this)
PORT=${PORT:-8080}
STREAMLIT_PORT=8501

sed "s/__PORT__/$PORT/g" /app/nginx.conf > /tmp/nginx.conf

# Start Streamlit in background
streamlit run app.py \
  --server.port=$STREAMLIT_PORT \
  --server.address=127.0.0.1 \
  --server.headless=true \
  --browser.gatherUsageStats=false &

# Wait for Streamlit to be ready
for i in $(seq 1 30); do
  curl -sf http://127.0.0.1:$STREAMLIT_PORT/_stcore/health > /dev/null 2>&1 && break
  sleep 1
done

# Start nginx in foreground
exec nginx -c /tmp/nginx.conf -g "daemon off;"
