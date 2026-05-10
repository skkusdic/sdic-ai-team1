import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_client import ask


def analyze(financials: dict) -> str:
    rows = "\n".join(
        f"{year}년: 매출 {d.get('매출액', 0):,}백만원, 영업이익 {d.get('영업이익', 0):,}백만원, 순이익 {d.get('순이익', 0):,}백만원"
        for year, d in sorted(financials.items())
    )

    latest_year = max(financials.keys())
    latest = financials[latest_year]
    revenue = latest.get("매출액", 0)
    op_profit = latest.get("영업이익", 0)
    op_margin = round(op_profit / revenue * 100, 1) if revenue else 0

    prompt = (
        f"다음은 어떤 기업의 {min(financials)}~{latest_year}년 연결재무제표 요약입니다 (단위: 백만원).\n"
        f"{rows}\n\n"
        f"이 기업의 영업이익률은 {op_margin}%로 시작하는 문장으로, "
        "매출 추세, 수익성(영업이익률·순이익률), 전년 대비 주요 변화를 포함해서 "
        "한국어로 3~5문장으로 분석해줘."
    )
    return ask(prompt)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    mock = {
        2021: {"매출액": 228867, "영업이익": 8535,   "순이익": 12548},
        2022: {"매출액": 398593, "영업이익": 43612,  "순이익": 27450},
        2023: {"매출액": 524059, "영업이익": 104946, "순이익": 81918},
        2024: {"매출액": 723000, "영업이익": 118397, "순이익": 107095},
        2025: {"매출액": 1528295,"영업이익": 354121, "순이익": 289938},
    }
    print(analyze(mock))
