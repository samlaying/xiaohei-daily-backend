"""Screenshot capture — macOS screencapture command (no permission issues for CLI)."""

import logging
import subprocess
import time
import base64
from pathlib import Path

import config


def capture_screens() -> list[dict]:
    """
    Capture all screens, return list of {displayId, sourceName, dataUrl, path}.
    Uses macOS screencapture CLI which works without special entitlements.
    """
    results = []
    timestamp = int(time.time() * 1000)

    # screencapture -x (no sound) -C (cursor) captures the main screen
    # For multi-monitor, macOS screencapture captures all screens by default
    path = config.SCREENSHOT_DIR / f"screen_{timestamp}.png"

    try:
        subprocess.run(
            ["screencapture", "-x", "-C", str(path)],
            check=True, capture_output=True, timeout=10
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        # Fallback to mss if screencapture not available
        return _capture_mss()

    if not path.exists():
        return _capture_mss()

    with open(path, "rb") as f:
        raw = f.read()

    b64 = base64.b64encode(raw).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"

    results.append({
        "displayId": "0",
        "sourceName": "Screen 0",
        "dataUrl": data_url,
        "path": str(path) if config.PRESERVE_SCREENSHOTS else None,
    })

    # Cleanup old screenshots
    _cleanup_screenshots()

    return results


def _capture_mss() -> list[dict]:
    """Fallback: use mss library for cross-platform capture."""
    import mss
    import mss.tools

    results = []
    with mss.mss() as sct:
        for i, monitor in enumerate(sct.monitors[1:], 1):  # skip "all in one" monitor 0
            shot = sct.grab(monitor)
            png_bytes = mss.tools.to_png(shot.rgb, shot.size)
            b64 = base64.b64encode(png_bytes).decode("ascii")
            data_url = f"data:image/png;base64,{b64}"

            path = None
            if config.PRESERVE_SCREENSHOTS:
                timestamp = int(time.time() * 1000)
                p = config.SCREENSHOT_DIR / f"screen_{timestamp}_{i}.png"
                p.write_bytes(png_bytes)
                path = str(p)

            results.append({
                "displayId": str(i),
                "sourceName": f"Screen {i}",
                "dataUrl": data_url,
                "path": path,
            })

    _cleanup_screenshots()
    return results


def cleanup_screenshots(keep_days: int = None, max_count: int = None) -> int:
    """
    清理旧截图文件。

    keep_days: 保留最近 N 天的截图（默认 7 天）
    max_count: 兜底上限（默认 2000 张）
    返回删除的文件数。
    """
    import os
    from datetime import timedelta

    keep_days = keep_days if keep_days is not None else 7
    max_count = max_count if max_count is not None else config.MAX_SCREENSHOTS
    cutoff = time.time() - keep_days * 86400

    files = sorted(config.SCREENSHOT_DIR.glob("screen_*.png"),
                   key=lambda f: f.stat().st_mtime)

    removed = 0
    # 1. 按天数清理
    for f in files:
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
            removed += 1

    # 2. 兜底：超过 max_count 删最旧的
    remaining = sorted(config.SCREENSHOT_DIR.glob("screen_*.png"),
                       key=lambda f: f.stat().st_mtime)
    while len(remaining) > max_count:
        remaining.pop(0).unlink(missing_ok=True)
        removed += 1

    return removed


def _cleanup_screenshots():
    """启动时自动清理。"""
    removed = cleanup_screenshots()
    if removed:
        logging.getLogger("screenshot").info("清理旧截图 %d 张", removed)
