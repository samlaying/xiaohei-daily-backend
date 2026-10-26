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
REPORT_DIR = DATA_DIR / "reports"
REPORT_DIR.mkdir(exist_ok=True)

# 人货场定位（记忆的一部分，报告生成时读取；改动即时生效，无需重启）
PROFILE_PATH = DATA_DIR / "profile.yaml"
# 素材链 Timeline：每天追加「产出物 + 数据 + 结论」，周报/月报基于它生成
OUTPUT_LOG_PATH = DATA_DIR / "output-log.md"


def _load_local_proxy_key() -> str:
    """API key 优先取环境变量，否则读本机 ~/.myagents/config.json 的 local-proxy。"""
    env = os.environ.get("AI_API_KEY")
    if env:
        return env
    try:
        cfg = json.loads((Path.home() / ".myagents" / "config.json").read_text())
        return cfg["providerApiKeys"]["local-proxy"] or ""
    except Exception:
        return ""


# AI Config（OpenAI 兼容 local-proxy；模型名 cn:/global: 前缀选路由域，裸名走默认域）
AI_BASE_URL = os.environ.get("AI_BASE_URL", "http://192.227.138.214:7863/v1")
AI_API_KEY = _load_local_proxy_key()
AI_VISION_MODEL = os.environ.get("AI_VISION_MODEL", "cn:glm-5v-turbo")  # 截图分析（多模态）
AI_TEXT_MODEL = os.environ.get("AI_TEXT_MODEL", "cn:glm-5.3-flash")     # 分析/生成/自检

# Screenshot interval in seconds (configurable: 30, 60, 300)
SCREENSHOT_INTERVAL_SEC = int(os.environ.get("SCREENSHOT_INTERVAL_SEC", "60"))

# HTTP Server
HTTP_HOST = os.environ.get("HTTP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8089"))

# 报告调度时区（与系统时区无关，固定按此时区的钟点触发）
REPORT_TIMEZONE = os.environ.get("REPORT_TIMEZONE", "Asia/Shanghai")

# 截图保留：报告生成不删截图，仅在超过天数/数量上限时清最旧的（磁盘兜底）
PRESERVE_SCREENSHOTS = True
SCREENSHOT_KEEP_DAYS = int(os.environ.get("SCREENSHOT_KEEP_DAYS", "7"))
MAX_SCREENSHOTS = 2000

# 日报约束（人货场之「场」；profile.yaml 里的 maxChars 可覆盖）
REPORT_MAX_CHARS = 500
