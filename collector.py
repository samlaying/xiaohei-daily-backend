"""Core collection loop — screenshot → AI analyze → classify → store."""

import logging
import json
from datetime import datetime, timezone, timedelta

import screenshot
import ai_client
import classifier
import app_tracker
import db
import config

log = logging.getLogger("collector")

_last_capture_time = None


def analyze_and_store(images: list[dict]) -> dict:
    """
    Take captured images, send to AI, classify, and store in DB.
    Returns the created work record dict.
    """
    global _last_capture_time

    if not images:
        log.warning("No images to analyze")
        return None

    img = images[0]
    now = datetime.now(timezone.utc)

    # 抓取前台应用上下文（聚焦 AI 注意力）
    ctx = app_tracker.get_frontmost_context()
    app_name = ctx["app"]
    win_title = ctx["windowTitle"]
    if app_name != "Unknown":
        log.info("前台应用: %s | 窗口: %s", app_name,
                 (win_title[:50] + "...") if len(win_title) > 50 else win_title)

    # Call AI vision (带前台应用聚焦)
    try:
        result = ai_client.analyze_screenshot(img["dataUrl"], app_name, win_title)
    except Exception as e:
        log.error("AI analysis failed: %s", e)
        return None

    summary = result["summary"]
    category = classifier.classify(summary)

    # The record covers the period from last capture to now
    started_at = _last_capture_time or now
    ended_at = now
    _last_capture_time = now

    # Store work record
    rid = db.create_work_record(
        category=category,
        summary=summary,
        started_at=started_at.isoformat(),
        ended_at=ended_at.isoformat(),
        confidence=0.8,
        source="screenshot",
        screenshot_path=img.get("path"),
        details=json.dumps({
            "provider": result["provider"],
            "model": result["model"],
            "displayCount": len(images),
            "frontmostApp": app_name,
            "windowTitle": win_title,
        }),
    )

    log.info("[%s] %s — %s", category, summary[:60], rid[:8])

    # Track app usage
    sessions = app_tracker.tick()
    for app_name, started, ended, dur in sessions:
        db.create_app_usage(app_name, started, ended, dur)

    return {
        "id": rid,
        "category": category,
        "summary": summary,
        "startedAt": started_at.isoformat(),
        "endedAt": ended_at.isoformat(),
        "confidence": 0.8,
        "source": "screenshot",
        "provider": result["provider"],
        "model": result["model"],
    }


def flush():
    """Flush pending app usage sessions (call on shutdown)."""
    sessions = app_tracker.flush()
    for app_name, started, ended, dur in sessions:
        db.create_app_usage(app_name, started, ended, dur)
    log.info("Flushed %d pending app sessions", len(sessions))


def run_once():
    """Single capture → analyze → store cycle."""
    try:
        images = screenshot.capture_screens()
        if not images:
            log.warning("Screenshot capture returned empty")
            return None
        return analyze_and_store(images)
    except Exception as e:
        log.error("Collection cycle failed: %s", e)
        return None
