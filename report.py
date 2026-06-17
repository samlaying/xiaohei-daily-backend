"""Markdown 日报生成器 — 把当天的工作记录整理成精细的日报文件。"""

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import db
import config


def _fmt_min(minutes: int) -> str:
    """分钟数格式化。"""
    if minutes < 60:
        return f"{minutes}min"
    h = minutes / 60
    return f"{h:.1f}h"


def _local_time(iso_str: str) -> str:
    """ISO 时间戳 → 本地时间 HH:MM:SS。"""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%H:%M:%S")
    except Exception:
        return iso_str[:19]


def _local_date(iso_str: str) -> str:
    """ISO 时间戳 → 本地日期 YYYY-MM-DD。"""
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
    except Exception:
        return iso_str[:10]


def generate_markdown(date: str = None) -> str:
    """
    生成指定日期的 Markdown 日报。date 格式 YYYY-MM-DD，默认今天。
    返回 Markdown 字符串。
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    start = f"{date}T00:00:00"
    end = f"{date}T23:59:59"

    records = db.query_work_records(start, end)
    summary = db.query_daily_summary(start, end)

    lines = []
    lines.append(f"# {date} 工作日报\n")

    # ── 概要 ──
    if summary:
        lines.append("## 概要\n")
        lines.append(f"- **记录条数**：{summary['recordCount']}")
        lines.append(f"- **专注时长**：{_fmt_min(summary['focusMinutes'])}")
        lines.append(f"- **活跃时段**：{summary['activePeriod']}")
        lines.append("")

        # 分类时长分布
        cats = summary.get("categoryBreakdown", {})
        if cats:
            lines.append("## 分类时长分布\n")
            lines.append("| 分类 | 时长 |")
            lines.append("|------|------|")
            for cat, mins in cats.items():
                lines.append(f"| {cat} | {_fmt_min(mins)} |")
            lines.append("")

    # ── 活动时间线 ──
    if records:
        lines.append("## 活动时间线\n")
        # 按时间正序（从早到晚）
        for r in sorted(records, key=lambda x: x["started_at"]):
            t = _local_time(r["started_at"])
            tag = r["category"]
            app = ""
            if r.get("details_json"):
                import json
                try:
                    d = json.loads(r["details_json"])
                    app_name = d.get("frontmostApp", "")
                    win_title = d.get("windowTitle", "")
                    if app_name:
                        app = f" · {app_name}"
                        if win_title:
                            # 截断过长标题，保留关键信息
                            short_title = win_title[:60] + "..." if len(win_title) > 60 else win_title
                            app += f" — {short_title}"
                except Exception:
                    pass

            lines.append(f"### {t} `[{tag}]`{app}\n")
            lines.append(f"{r['summary']}\n")
    else:
        lines.append("## 活动时间线\n")
        lines.append("该时段无工作记录。\n")

    # ── 生成时间 ──
    lines.append("---")
    lines.append(f"*由日报助手自动生成 · {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")

    return "\n".join(lines)


def generate_and_save(date: str = None, output_dir: str = None) -> str:
    """
    生成 Markdown 日报并保存到文件。
    生成后自动清理该日期前的旧截图（已出报告，原始截图不再需要）。
    返回保存路径。
    """
    if not output_dir:
        output_dir = str(config.DATA_DIR / "reports")
    os.makedirs(output_dir, exist_ok=True)

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    md = generate_markdown(date)
    path = os.path.join(output_dir, f"{date}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)

    # 生成报告后，清理该日期前的旧截图（已出报告的不需要保留原始图）
    try:
        import screenshot
        removed = screenshot.cleanup_screenshots(keep_days=3)
        if removed:
            import logging
            logging.getLogger("report").info("报告生成后清理旧截图 %d 张", removed)
    except Exception:
        pass

    return path


if __name__ == "__main__":
    path = generate_and_save()
    print(f"日报已生成: {path}")
