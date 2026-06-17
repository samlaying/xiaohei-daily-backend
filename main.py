#!/usr/bin/env python3
"""
日报助手 — Python Backend
定时截图 → AI Vision 分析 → 分类存储 → 自动生成 Markdown 日报

Usage:
    python main.py                              # 默认 60s 间隔
    SCREENSHOT_INTERVAL_SEC=30 python main.py   # 30s 间隔
    SCREENSHOT_INTERVAL_SEC=300 python main.py  # 5min 间隔
"""

import os
import sys
import signal
import logging
import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

import config
import db
import screenshot
import permission_check
import server
import collector
import report

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

# 壁纸垃圾记录关键词（权限未生效时产生的无用记录）
_WALLPAPER_KEYWORDS = ("壁纸", "系统桌面", "无正在进行的", "窗口被一张风景壁纸")


def _cleanup_wallpaper_records():
    """删除权限未生效期间产生的壁纸垃圾记录。"""
    import sqlite3
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, summary FROM work_records").fetchall()
    to_delete = []
    for r in rows:
        s = r["summary"] or ""
        if any(kw in s for kw in _WALLPAPER_KEYWORDS):
            to_delete.append(r["id"])
    if to_delete:
        conn.executemany("DELETE FROM work_records WHERE id = ?",
                         [(rid,) for rid in to_delete])
        conn.commit()
        log.info("清理壁纸垃圾记录 %d 条", len(to_delete))
    conn.close()


def _run_permission_check():
    """启动自检：检测 macOS 屏幕录制权限是否生效。"""
    if os.environ.get("SKIP_PERMISSION_CHECK"):
        log.info("跳过权限自检 (SKIP_PERMISSION_CHECK=1)")
        return
    log.info("正在检测屏幕录制权限... (请在此时正常使用电脑)")
    try:
        result = permission_check.run_startup_check(
            capture_fn=lambda: screenshot.capture_screens()[0]["path"],
            wait_seconds=3,
        )
        log.info(result["verdict"])
        log.info("  信号: %s", result["signals"])
        if result["status"] == "wallpaper":
            permission_check.print_permission_guide()
            if os.environ.get("EXIT_ON_PERMISSION_FAIL"):
                log.error("权限未生效，退出")
                sys.exit(1)
            log.warning("权限未生效，继续运行但截图将只有壁纸。请尽快开启权限。")
        else:
            log.info("权限检测通过 ✅")
    except Exception as e:
        log.warning("权限自检异常(已跳过): %s", e)


def main():
    log.info("=" * 50)
    log.info("日报助手 — Python Backend")
    log.info("=" * 50)
    log.info("AI Model:   %s", config.AI_MODEL)
    log.info("Interval:   %ds", config.SCREENSHOT_INTERVAL_SEC)
    log.info("DB:         %s", config.DB_PATH)
    log.info("HTTP API:   http://%s:%d", config.HTTP_HOST, config.HTTP_PORT)
    log.info("Report dir: %s/reports/", config.DATA_DIR)
    log.info("=" * 50)

    # Init database
    db.init_db()
    log.info("Database initialized")

    # 清理历史壁纸垃圾记录
    _cleanup_wallpaper_records()

    # Startup permission self-check
    _run_permission_check()

    # Start HTTP server
    server.start_server()

    # Schedule periodic captures + daily report
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        collector.run_once,
        "interval",
        seconds=config.SCREENSHOT_INTERVAL_SEC,
        id="screenshot_collector",
        max_instances=1,
        coalesce=True,
    )

    # 每天 18:00 自动生成 Markdown 日报
    scheduler.add_job(
        lambda: report.generate_and_save(),
        "cron",
        hour=18, minute=0,
        id="daily_report",
    )
    scheduler.start()
    log.info("Scheduler started — capturing every %ds, report daily at 18:00", config.SCREENSHOT_INTERVAL_SEC)

    # Run first capture immediately
    log.info("Running initial capture...")
    result = collector.run_once()
    if result:
        log.info("First capture: [%s] %s", result["category"], result["summary"][:80])
    else:
        log.warning("First capture failed — will retry on next interval")

    # Keep alive
    def shutdown(sig, frame):
        log.info("Shutting down...")
        collector.flush()
        # 退出前生成一次报告（如果有当天数据）
        try:
            path = report.generate_and_save()
            log.info("Report saved: %s", path)
        except Exception:
            pass
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    log.info("Running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        shutdown(None, None)


if __name__ == "__main__":
    main()
