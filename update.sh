#!/bin/bash
# Monthly update script for University Brand Monitor
cd "$(dirname "$0")"
echo "[$(date)] Starting monthly update..." >> update.log
python3 main.py crawl >> update.log 2>&1
python3 main.py analyze >> update.log 2>&1
echo "[$(date)] Update complete." >> update.log
