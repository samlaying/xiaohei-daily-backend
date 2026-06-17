"""Configuration management."""

import os
import json
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "xiaohei.db"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

# AI Config (Xiaomi Mimo)
AI_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
AI_API_KEY = "tp-czq97wj2vol05hpfipuico337yuvk7tbo8ikslu5yh8vjnlb"
AI_MODEL = "mimo-v2.5"

# Screenshot interval in seconds (configurable: 30, 60, 300)
SCREENSHOT_INTERVAL_SEC = int(os.environ.get("SCREENSHOT_INTERVAL_SEC", "60"))

# HTTP Server
HTTP_HOST = os.environ.get("HTTP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8089"))

# Preserve screenshots on disk
PRESERVE_SCREENSHOTS = True

# Max screenshots to keep (disk cleanup)
MAX_SCREENSHOTS = 2000
