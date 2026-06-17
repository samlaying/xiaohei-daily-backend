"""Foreground app tracker — macOS osascript (no extra deps)."""

import subprocess
import logging
from datetime import datetime, timezone

log = logging.getLogger("app_tracker")

_current_app = None
_current_start = None

_FRONTMOST_SCRIPT = '''
tell application "System Events"
    set frontApp to first application process whose frontmost is true
    set appName to name of frontApp
    try
        set winTitle to title of front window of frontApp
    on error
        set winTitle to ""
    end try
    return appName & "||" & winTitle
end tell
'''


def get_frontmost_context() -> dict:
    """
    获取前台应用上下文：{app, windowTitle}。
    窗口标题需要"辅助功能"权限；拿不到则降级为只有 app 名。
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", _FRONTMOST_SCRIPT],
            capture_output=True, text=True, timeout=5
        )
        out = result.stdout.strip()
        parts = out.split("||", 1)
        app = parts[0] if parts and parts[0] else "Unknown"
        title = parts[1] if len(parts) > 1 else ""
        return {"app": app, "windowTitle": title}
    except Exception as e:
        log.debug("get_frontmost_context failed: %s", e)
        return {"app": "Unknown", "windowTitle": ""}


def get_frontmost_app() -> str:
    """兼容旧接口：只返回应用名。"""
    return get_frontmost_context()["app"]


def tick():
    """
    周期调用（如每次截图间隔）。追踪前台应用切换，返回已结束的 session。
    返回 [(app_name, started_at_iso, ended_at_iso, duration_sec), ...]
    """
    global _current_app, _current_start

    now = datetime.now(timezone.utc)
    app = get_frontmost_app()
    sessions = []

    if app != _current_app:
        if _current_app and _current_start:
            duration = (now - _current_start).total_seconds()
            if duration > 5:  # 忽略极短切换
                sessions.append((
                    _current_app,
                    _current_start.isoformat(),
                    now.isoformat(),
                    int(duration),
                ))
        _current_app = app
        _current_start = now

    return sessions


def flush():
    """关闭时 flush 当前 session。"""
    global _current_app, _current_start
    sessions = []
    if _current_app and _current_start:
        now = datetime.now(timezone.utc)
        duration = (now - _current_start).total_seconds()
        if duration > 5:
            sessions.append((
                _current_app,
                _current_start.isoformat(),
                now.isoformat(),
                int(duration),
            ))
    _current_app = None
    _current_start = None
    return sessions
