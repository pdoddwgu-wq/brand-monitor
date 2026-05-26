#!/bin/bash
# Keeps dashboard running in background — added as a Login Item
# so it starts automatically when you log into your Mac.

cd "/Users/preston.dodd/Desktop/For Claude/brand_monitor"

# Kill any existing instance on port 8501
lsof -ti:8501 | xargs kill -9 2>/dev/null
sleep 1

# Start dashboard and keep it running
while true; do
    /usr/bin/python3 -m streamlit run dashboard.py \
        --server.headless true \
        --server.port 8501 \
        >> "/Users/preston.dodd/Desktop/For Claude/brand_monitor/dashboard.log" 2>&1
    sleep 3  # Brief pause before restart if it crashes
done
