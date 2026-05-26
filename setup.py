#!/usr/bin/env python3
"""
One-time setup: resets the database and verifies dependencies.
No API key needed — sentiment analysis runs fully offline.
Run: python3 setup.py
"""
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
DB_FILE = HERE / "brand_monitor.db"

print("=" * 50)
print("  University Brand Monitor — Setup")
print("=" * 50)
print()

# Install dependencies
print("Installing dependencies...")
subprocess.check_call(
    [sys.executable, "-m", "pip", "install", "-r", str(HERE / "requirements.txt"), "-q"]
)
print("✅ Dependencies installed")

# Reset DB
if DB_FILE.exists():
    DB_FILE.unlink()
    print("✅ Old database cleared")

print()
print("Setup complete! Now run:")
print()
print("  python3 main.py crawl      ← pulls Reddit, Niche, Trustpilot")
print("  python3 main.py analyze    ← runs sentiment analysis (free, offline)")
print("  python3 main.py dashboard  ← opens the dashboard")
print()
