#!/bin/sh
PORT=${PORT:-8080}
UVICORN_PORT=8000

sed "s/__PORT__/$PORT/g" /app/nginx.conf > /tmp/nginx.conf

# Start nginx FIRST — serves loading.html immediately on 502 while uvicorn warms up
nginx -c /tmp/nginx.conf -g "daemon off;" &

# Start uvicorn in background
uvicorn server:app --host 127.0.0.1 --port $UVICORN_PORT --workers 1

