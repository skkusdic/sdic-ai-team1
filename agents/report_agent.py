import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# report.py의 generate_report()를 사용 (Report Lead 담당)
from report import generate_report


def run_report_agent(state: dict) -> dict:
    company    = state.get("company", "기업")
    financials = state.get("financials", {})
    analysis   = state.get("analysis", "")

    pdf_path = generate_report(company, financials, analysis)
    return {**state, "pdf_path": pdf_path}


def embed_text(text: str) -> list:
    pass  # TODO: 4주차에 OpenAI embeddings로 구현


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    mock_state = {
        "company": "에이피알",
        "financials": {
            2021: {"매출액": 149883, "영업이익": 18234, "순이익": 14102},
            2022: {"매출액": 198210, "영업이익": 24501, "순이익": 19800},
            2023: {"매출액": 241560, "영업이익": 31200, "순이익": 25600},
            2024: {"매출액": 289000, "영업이익": 38900, "순이익": 31200},
            2025: {"매출액": 320000, "영업이익": 42000, "순이익": 34500},
        },
        "analysis": """\
1. 주요 사업 영역
에이피알(APR)은 뷰티·패션 브랜드 포트폴리오를 운영하는 글로벌 K뷰티 기업입니다.
피부 관리 디바이스, 스킨케어, 색조 화장품 등 다양한 카테고리를 보유하고 있습니다.

2. 핵심 제품·서비스
메디큐브, 에이프릴스킨, 포맨트, 아떼, NONFICTION 등 다수의 독립 브랜드를 운영합니다.
특히 메디큐브 AGE-R 시리즈는 홈케어 뷰티 디바이스 시장에서 높은 인지도를 확보하고 있습니다.

3. 고객 및 시장
MZ세대를 핵심 타깃으로 하는 글로벌 K뷰티 시장을 공략하고 있습니다.
일본, 미국, 동남아시아를 중심으로 해외 소비자 기반을 빠르게 확장 중입니다.

4. 성장 전략
글로벌 시장 확장 및 디지털 채널 강화를 통해 지속 성장을 추구합니다.
D2C 비중을 높여 수익성을 개선하고 있습니다.
""",
    }

    print("보고서 생성 시작...")
    result = run_report_agent(mock_state)
    print(f"PDF 생성 완료: {result['pdf_path']}")
    print(f"파일 존재 여부: {os.path.exists(result['pdf_path'])}")
