#!/bin/bash
# Monthly update script for University Brand Monitor
cd "$(dirname "$0")"
echo "[$(date)] Starting monthly update..." >> update.log

python3 main.py crawl >> update.log 2>&1
python3 main.py analyze >> update.log 2>&1

# Push updated database to GitHub so Streamlit Cloud refreshes
git add brand_monitor.db >> update.log 2>&1
git commit -m "Monthly data update $(date +%Y-%m-%d)" >> update.log 2>&1
git push >> update.log 2>&1

echo "[$(date)] Update complete — data pushed to Streamlit Cloud." >> update.log
