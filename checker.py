"""自检 pass — 五条清单：规则查硬指标，AI 查软指标。

规则检查（零成本、确定性）：
  1. 四段齐全   2. 字数上限   3. 至少一处数字   4. 风险段带"下一步"   5. 空话黑名单
AI 检查（软指标）：写的是"做完了什么"吗 / 重点选对了吗
"""

import logging
import re

import ai_client
import prompt as prompts

log = logging.getLogger("checker")

REQUIRED_SECTIONS = ["今日重点进展", "问题与风险", "明日计划", "需要支持"]

# 空话黑名单（命中即要求重写）
FLUFF_WORDS = ["全力以赴", "积极配合", "认真完成", "持续跟进", "努力推进",
               "加班加点", "任劳任怨", "保质保量"]


def _plain_text(md: str) -> str:
    """去掉 markdown 标记后的纯文本（用于字数统计）。"""
    return re.sub(r"[#*`|>\-\s]", "", md)


def _extract_section(md: str, name: str) -> str:
    m = re.search(rf"^##\s*{re.escape(name)}\s*$(.*?)(?=^##\s|\Z)",
                  md, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def rule_check(body: str, max_chars: int = 500) -> list[str]:
    """规则自检，返回问题列表（空=通过）。"""
    issues = []

    for sec in REQUIRED_SECTIONS:
        if not _extract_section(body, sec):
            issues.append(f"缺少段落：{sec}")

    plain = _plain_text(body)
    n = len(plain)
    if n > max_chars:
        issues.append(f"正文超长：{n} 字 > {max_chars} 字上限")

    if not re.search(r"\d", plain):
        issues.append("正文没有任何数字/量化结果")

    risk = _extract_section(body, "问题与风险")
    if risk and risk not in ("今日无明显阻塞", "暂无"):
        # 逐条检查：每条非空内容应带"下一步"
        items = [ln.strip("- ").strip() for ln in risk.splitlines()
                 if ln.strip() and ln.strip() not in ("今日无明显阻塞",)]
        for i, item in enumerate(items, 1):
            if item and "下一步" not in item and "已做动作" not in item:
                issues.append(f"问题与风险第 {i} 条缺少「下一步」")
                break

    hits = [w for w in FLUFF_WORDS if w in plain]
    if hits:
        issues.append(f"含空话用词：{'、'.join(hits)}")

    return issues


def ai_check(body: str, analysis: dict) -> list[str]:
    """AI 自检（软指标）。AI 不可用时跳过（返回空），不阻塞流程。"""
    user = (
        f"【分析结论】\n{analysis}\n\n"
        f"【日报正文】\n{body}\n\n"
        "按 system 的五条检查输出 JSON。"
    )
    try:
        out = ai_client.chat_json(prompts.CHECK_SYSTEM_PROMPT, user, max_tokens=500)
        if out.get("pass"):
            return []
        return [f"AI 自检：{i}" for i in out.get("issues", [])] or ["AI 自检未通过（未给出具体问题）"]
    except Exception as e:
        log.warning("AI 自检失败（跳过）: %s", e)
        return []


def check(body: str, analysis: dict, max_chars: int = 500) -> list[str]:
    """规则 + AI 混合自检。"""
    return rule_check(body, max_chars) + ai_check(body, analysis)
