import os
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def generate_report(company: str, financials: list) -> str:
    # TODO Week 3-4: Claude로 분석 리포트 생성
    pass
