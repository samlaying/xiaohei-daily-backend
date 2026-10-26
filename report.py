"""日报/周报/月报生成器。

流水线（用户定稿的设计）：
  到点 → 读取记忆(memory) → 分析(analyzer) → 四段式生成(AI) → 自检(checker) → 落盘
  + 追加 output-log 素材链；AI 不可用时降级为规则模板。

正文给人看（四段式，≤500 字）；附录给"三个月后写简历/述职的自己"看（统计+全量时间线）。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

import ai_client
import analyzer
import checker
import config
import db
import memory
import prompt as prompts

log = logging.getLogger("report")


# ── 工具 ──

def _fmt_min(minutes) -> str:
    minutes = int(minutes or 0)
    if minutes < 60:
        return f"{minutes}min"
    return f"{minutes / 60:.1f}h"


def _biz_time(iso_str: str) -> str:
    """记录时间戳 → 业务时区（北京时间）HH:MM:SS 显示。"""
    try:
        dt = db._parse_ts(iso_str)
        return db._to_biz(dt).strftime("%H:%M:%S") if dt else iso_str[:19]
    except Exception:
        return iso_str[:19]


def _record_app_line(r: dict) -> str:
    app = ""
    try:
        d = json.loads(r.get("details_json") or "{}")
        name = d.get("frontmostApp", "")
        title = d.get("windowTitle", "")
        if name and name != "Unknown":
            app = f" · {name}"
            if title:
                short = title[:60] + "..." if len(title) > 60 else title
                app += f" — {short}"
    except Exception:
        pass
    return app


# ── 正文生成（AI）──

def _generate_body(profile: dict, analysis: dict, inputs_text: str,
                   extra_feedback: str = None) -> str | None:
    system = (prompts.REPORT_SYSTEM_PROMPT
              + "\n\n" + prompts.REPORT_OUTPUT_SCHEMA)
    user = prompts.build_report_user_prompt(profile, analysis, inputs_text,
                                            profile.get("maxChars", 500))
    if extra_feedback:
        user += f"\n\n【上一版自检未通过的问题，本次务必修正】\n{extra_feedback}"
    try:
        return ai_client.chat_text(system, user, max_tokens=1500)
    except Exception as e:
        log.error("AI 正文生成失败: %s", e)
        return None


def _rule_issue_count(issues: list[str]) -> int:
    return len([i for i in issues if not i.startswith("AI 自检")])


def _generate_with_retry(profile, analysis, inputs_text, max_chars) -> tuple[str, list[str]]:
    """生成 + 自检 + 一轮重写。返回 (正文, 最终问题列表)。"""
    body = _generate_body(profile, analysis, inputs_text)
    if body is None:
        return None, []

    issues = checker.check(body, analysis, max_chars)
    if not issues:
        return body, []

    # 带着问题重写一轮
    feedback = "\n".join(f"- {i}" for i in issues)
    body2 = _generate_body(profile, analysis, inputs_text, extra_feedback=feedback)
    if body2:
        issues2 = checker.check(body2, analysis, max_chars)
        # 规则问题更少（或持平）则采用重写版
        if _rule_issue_count(issues2) <= _rule_issue_count(issues):
            return body2, issues2
    return body, issues


# ── 降级模板（AI 不可用时的规则拼接，即旧版日报）──

def _fallback_body(ctx: dict, date: str) -> str:
    records = ctx["records"]
    deliverables = ctx["deliverableRecords"]

    lines = ["## 今日重点进展", ""]
    if deliverables:
        for r in deliverables[:4]:
            s = r["summary"].split("【产出】")[-1]
            lines.append(f"- {s}（{r['category']}）")
    else:
        lines.append(f"- 共记录 {len(records)} 条工作活动（今日无标记产出物）")
    lines += ["", "## 问题与风险", "", "今日无明显阻塞", "",
              "## 明日计划", "", "- 见活动时间线中的待办事项", "",
              "## 需要支持", "", "暂无"]
    return "\n".join(lines)


# ── 附录（统计 + 全量时间线）──

def _build_appendix(date: str) -> str:
    records = db.query_work_records(date, date)
    summary = db.query_daily_summary(date, date)

    lines = ["---", "", "## 附录（数据与时间线）"]

    if summary:
        lines += ["", "### 概要", "",
                  f"- 记录条数：{summary['recordCount']}"
                  f"（其中产出物 {summary.get('deliverableCount', 0)} 条）",
                  f"- 专注时长：{_fmt_min(summary['focusMinutes'])}",
                  f"- 活跃时段：{summary['activePeriod']}"]

        cats = summary.get("categoryBreakdown", {})
        if cats:
            lines += ["", "### 分类时长分布", "", "| 分类 | 时长 |", "|------|------|"]
            for cat, mins in cats.items():
                lines.append(f"| {cat} | {_fmt_min(mins)} |")

    if records:
        lines += ["", "### 活动时间线（全量）", ""]
        deliverable_first = sorted(
            records, key=lambda r: (not r.get("is_deliverable"), r["started_at"]))
        for r in deliverable_first:
            t = _biz_time(r["started_at"])
            mark = " 📦" if r.get("is_deliverable") else ""
            lines.append(f"#### {t} `[{r['category']}]`{_record_app_line(r)}{mark}")
            lines.append(f"{r['summary']}")
            lines.append("")

    return "\n".join(lines)


# ── output-log 素材链追加 ──

def _append_log_entry(date: str, analysis: dict | None, ctx: dict):
    lines = []
    if analysis:
        if analysis.get("deliverables"):
            items = "；".join(str(d) for d in analysis["deliverables"][:5])
            lines.append(f"- 产出：{items}")
        drills = analysis.get("drillDown") or []
        if drills:
            data = "；".join(str(d.get("data", "")) for d in drills[:3] if d.get("data"))
            if data:
                lines.append(f"- 数据：{data}")
        if analysis.get("headline"):
            lines.append(f"- 结论：{analysis['headline']}")
    else:
        for r in ctx["deliverableRecords"][:3]:
            s = r["summary"].split("【产出】")[-1]
            lines.append(f"- 产出：{s}")
    if lines:
        memory.append_output_log(date, lines)


# ── 主入口：日报 ──

def generate_and_save(date: str = None, output_dir: str = None) -> str | None:
    """
    完整流水线：读记忆 → 分析 → 生成 → 自检 → 落盘 + 素材链追加。
    无素材返回 None；AI 全挂时降级规则模板。
    """
    if not date:
        date = db.biz_today()
    if not output_dir:
        output_dir = str(config.REPORT_DIR)
    os.makedirs(output_dir, exist_ok=True)

    ctx = memory.build_generation_context(date)
    profile = ctx["profile"]
    max_chars = int(profile.get("maxChars", config.REPORT_MAX_CHARS))

    if not ctx["records"] and not ctx["inputs"]:
        log.info("[%s] 无素材，跳过日报生成", date)
        return None

    # 1) 分析 pass
    try:
        analysis = analyzer.analyze_day(date)
    except Exception as e:
        log.error("[%s] 分析 pass 失败，降级规则模板: %s", date, e)
        analysis = None

    # 2)+3) 生成 + 自检（分析失败时直接降级）
    warnings, status = [], "completed"
    if analysis:
        body, issues = _generate_with_retry(profile, analysis, ctx["inputsText"], max_chars)
        if body is None:
            body = _fallback_body(ctx, date)
            status = "fallback"
            warnings.append("AI 生成不可用，已降级为规则模板")
        else:
            warnings = [f"重写后仍未通过：{i}" for i in issues]
    else:
        body = _fallback_body(ctx, date)
        status = "fallback"
        warnings.append("分析 pass 不可用，已降级为规则模板")

    # 4) 组装 + 落盘（截图保留，不做清理）
    parts = [f"# {date} 工作日报", ""]
    if warnings:
        parts.append("> ⚠️ " + "；".join(warnings[:3]))
        parts.append("")
    parts.append(body.strip())
    parts.append("")
    parts.append(_build_appendix(date))
    parts += ["", "---",
              f"*由日报助手自动生成 · 分析/生成模型 {config.AI_TEXT_MODEL} · "
              f"{datetime.now().strftime('%Y-%m-%d %H:%M')}*"]
    md = "\n".join(parts)

    path = os.path.join(output_dir, f"{date}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    db.replace_report("daily", f"{date} 工作日报", md, date, date, status=status)

    # 5) 素材链
    _append_log_entry(date, analysis, ctx)

    log.info("[%s] 日报已生成: %s (status=%s, warnings=%d)", date, path, status, len(warnings))
    return path


# ── 周报 / 月报（基于 output-log 素材链裁剪）──

def _week_range(end_date: str) -> tuple[str, str]:
    d = datetime.strptime(end_date, "%Y-%m-%d")
    monday = d - timedelta(days=d.weekday())
    return monday.strftime("%Y-%m-%d"), end_date


def generate_weekly_and_save(end_date: str = None, output_dir: str = None) -> str | None:
    """周报：写给上级，阶段成果视角。素材 = 本周 output-log + 汇总统计。"""
    if not end_date:
        end_date = db.biz_today()
    if not output_dir:
        output_dir = str(config.REPORT_DIR)
    start, end = _week_range(end_date)

    entries = [e for e in memory.read_output_log() if start <= e["date"] <= end]
    if not entries:
        log.info("周报跳过：[%s ~ %s] 无素材链", start, end)
        return None

    summary = db.query_daily_summary(start, end)
    stat_text = ""
    if summary:
        stat_text = (f"记录 {summary['recordCount']} 条，产出物 "
                     f"{summary.get('deliverableCount', 0)} 条，"
                     f"专注 {_fmt_min(summary['focusMinutes'])}，"
                     f"分类分布 {json.dumps(summary['categoryBreakdown'], ensure_ascii=False)}")

    log_text = "\n\n".join(f"[{e['date']}]\n{e['text']}" for e in entries)
    profile = memory.load_profile()
    user = (f"【周期】{start} ~ {end}\n"
            f"【本周素材链】\n{log_text}\n\n"
            f"【本周汇总统计】{stat_text}\n\n"
            f"【团队 KPI】{profile.get('teamKpi', '')}\n"
            "请生成周报。")

    try:
        body = ai_client.chat_text(prompts.WEEKLY_SYSTEM_PROMPT, user, max_tokens=2000)
    except Exception as e:
        log.error("周报生成失败: %s", e)
        return None

    md = (f"# {start} ~ {end} 周报\n\n{body.strip()}\n\n---\n"
          f"*由日报助手自动生成 · {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"weekly_{end}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    db.replace_report("weekly", f"{start}~{end} 周报", md, start, end)
    log.info("周报已生成: %s", path)
    return path


def generate_monthly_and_save(month: str = None, output_dir: str = None) -> str | None:
    """月报：独立产出 Timeline，给未来的自己（简历/述职素材）。"""
    import calendar
    if not month:
        month = db.biz_today()[:7]
    if not output_dir:
        output_dir = str(config.REPORT_DIR)

    entries = [e for e in memory.read_output_log() if e["date"][:7] == month]
    if not entries:
        log.info("月报跳过：%s 无素材链", month)
        return None

    log_text = "\n\n".join(f"[{e['date']}]\n{e['text']}" for e in entries)
    user = (f"【月份】{month}\n【本月素材链】\n{log_text}\n\n"
            "请生成月度复盘（Timeline + 数据结论 + 价值总结）。")
    try:
        body = ai_client.chat_text(prompts.MONTHLY_SYSTEM_PROMPT, user, max_tokens=2500)
    except Exception as e:
        log.error("月报生成失败: %s", e)
        return None

    md = (f"# {month} 月度复盘\n\n{body.strip()}\n\n---\n"
          f"*由日报助手自动生成 · {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"monthly_{month}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    last_day = calendar.monthrange(int(month[:4]), int(month[5:7]))[1]
    db.replace_report("monthly", f"{month} 月度复盘", md, f"{month}-01", f"{month}-{last_day:02d}")
    log.info("月报已生成: %s", path)
    return path


if __name__ == "__main__":
    p = generate_and_save()
    print(f"日报已生成: {p}" if p else "今日无素材，未生成")
