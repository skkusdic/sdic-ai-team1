"""SKKUSDIC AI 프로젝트 — Claude 호출 래퍼 (모델 잠금).

이 모듈은 Anthropic API를 호출하는 **유일한 진입점**입니다.
학회 비용 관리를 위해 모델은 claude-haiku-4-5로 강제 고정됩니다.

학생 코드는 절대 anthropic SDK를 직접 import하지 마세요.
이 모듈을 import해서 ask() 또는 ask_messages()만 쓰세요.

import 규칙:
    OK   : from claude_client import ask
    금지 : from anthropic import Anthropic
    금지 : import anthropic

CI(.github/workflows/model-check.yml)가 위 규칙을 자동 검증합니다.
"""
import os
from typing import Optional

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# 학회 비용 관리 정책 — 절대 변경 금지
_LOCKED_MODEL = "claude-haiku-4-5"

_client: Optional[Anthropic] = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY 미설정. .env 파일을 확인하세요."
            )
        _client = Anthropic(api_key=api_key)
    return _client


def ask(prompt: str, max_tokens: int = 600) -> str:
    """단일 프롬프트로 Claude 분석을 받는다.

    모델은 claude-haiku-4-5로 고정되어 있으며 변경할 수 없습니다.
    """
    client = _get_client()
    response = client.messages.create(
        model=_LOCKED_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def ask_messages(messages: list, max_tokens: int = 600) -> str:
    """여러 턴의 대화로 Claude 분석을 받는다."""
    client = _get_client()
    response = client.messages.create(
        model=_LOCKED_MODEL,
        max_tokens=max_tokens,
        messages=messages,
    )
    return response.content[0].text


if __name__ == "__main__":
    print(ask("2026년 한국 반도체 산업의 핵심 트렌드를 한 문장으로 요약해줘."))
