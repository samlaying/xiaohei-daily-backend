"""AI client — OpenAI 兼容 local-proxy；视觉/文本双模型。"""

import logging
import json
import re
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
            timeout=120,
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
            model=config.AI_VISION_MODEL,
            messages=messages,
            max_tokens=1000,
            stream=False,
        )
        content = resp.choices[0].message.content.strip()
        log.info("AI response: %s", content[:120])
        return {
            "summary": content,
            "provider": "local-proxy",
            "model": config.AI_VISION_MODEL,
        }
    except Exception as e:
        log.error("AI vision call failed: %s", e)
        raise


def chat_text(system: str, user: str, max_tokens: int = 3000,
              model: str = None, temperature: float = 0.3) -> str:
    """通用文本调用（分析/生成/自检/周月报）。失败抛异常，由调用方降级。"""
    client = _get_client()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    resp = client.chat.completions.create(
        model=model or config.AI_TEXT_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=False,
    )
    return resp.choices[0].message.content.strip()


def extract_json(text: str) -> dict:
    """从模型输出中鲁棒地提取 JSON 对象（容忍代码块围栏和前后废话）。"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
    return json.loads(text)


def chat_json(system: str, user: str, max_tokens: int = 3000,
              model: str = None) -> dict:
    """文本调用并解析 JSON。解析失败抛异常。"""
    content = chat_text(system, user, max_tokens=max_tokens, model=model)
    return extract_json(content)
