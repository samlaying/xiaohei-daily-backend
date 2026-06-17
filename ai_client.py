"""AI vision client — talks to Xiaomi Mimo (OpenAI-compatible)."""

import logging
from openai import OpenAI

import config
import prompt as prompts

log = logging.getLogger("ai_client")

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=config.AI_BASE_URL,
            api_key=config.AI_API_KEY,
            timeout=60,
        )
    return _client


def analyze_screenshot(data_url: str, app: str = None, window_title: str = None) -> dict:
    """
    Send a screenshot (as data URL) to the vision model.
    app/window_title: 前台应用上下文，帮助 AI 聚焦。
    Returns {"summary": str, "provider": str, "model": str}.
    """
    client = _get_client()

    messages = [
        {"role": "system", "content": prompts.SCREENSHOT_SYSTEM_PROMPT_ZH},
        {
            "role": "user",
            "content": [
                {"type": "text",
                 "text": prompts.build_screenshot_user_prompt(app, window_title)},
                {
                    "type": "image_url",
                    "image_url": {"url": data_url},
                },
            ],
        },
    ]

    try:
        resp = client.chat.completions.create(
            model=config.AI_MODEL,
            messages=messages,
            max_tokens=1000,
            stream=False,
        )
        content = resp.choices[0].message.content.strip()
        log.info("AI response: %s", content[:120])
        return {
            "summary": content,
            "provider": "xiaomi",
            "model": config.AI_MODEL,
        }
    except Exception as e:
        log.error("AI call failed: %s", e)
        raise


def generate_report(records_text: str, report_type: str = "daily",
                    date_range: str = "", job_title: str = "") -> str:
    """Generate a work report from records text."""
    client = _get_client()

    user_parts = []
    if job_title:
        user_parts.append(f"【岗位】{job_title}")
    type_label = {"daily": "日报", "weekly": "周报", "monthly": "月报"}.get(report_type, report_type)
    user_parts.append(f"【类型】{type_label}")
    if date_range:
        user_parts.append(f"【日期范围】{date_range}")
    user_parts.append(f"【工作记录】\n{records_text}")
    user_parts.append("请基于上面的记录生成一篇中文报告。")

    messages = [
        {"role": "system", "content": prompts.REPORT_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]

    try:
        resp = client.chat.completions.create(
            model=config.AI_MODEL,
            messages=messages,
            max_tokens=4000,
            stream=False,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.error("Report generation failed: %s", e)
        raise
