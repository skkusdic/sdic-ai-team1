import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data import get_business_report_text
from rag import summarize_business_report
from claude_client import ask


def analyze(financials: dict, company: str = "") -> str:
    """
    DART 사업보고서 원문을 우선 사용해 핵심 요약.
    원문을 가져오지 못하면 재무 수치 기반 분석으로 fallback.
    """
    if company:
        report_text = get_business_report_text(company)
        if report_text:
            return summarize_business_report(report_text, company)

    # fallback: 재무 수치 기반 분석
    rows = "\n".join(
        f"{year}년: 매출 {d.get('매출액', 0):,}억원, 영업이익 {d.get('영업이익', 0):,}억원, 순이익 {d.get('순이익', 0):,}억원"
        for year, d in sorted(financials.items())
    )
    latest_year = max(financials.keys())
    latest = financials[latest_year]
    revenue = latest.get("매출액", 0)
    op_profit = latest.get("영업이익", 0)
    op_margin = round(op_profit / revenue * 100, 1) if revenue else 0

    prompt = (
        f"다음은 어떤 기업의 {min(financials)}~{latest_year}년 연결재무제표 요약입니다 (단위: 억원).\n"
        f"{rows}\n\n"
        f"이 기업의 영업이익률은 {op_margin}%로 시작하는 문장으로, "
        "매출 추세, 수익성(영업이익률·순이익률), 전년 대비 주요 변화를 포함해서 "
        "한국어로 3~5문장으로 분석해줘."
    )
    return ask(prompt)


def analysis_agent(state: dict) -> dict:
    company = state.get("company", "")
    print(f"[analysis_agent] {company} 사업보고서 분석 중...")
    result = analyze(state["financials"], company=company)
    print("[analysis_agent] 분석 완료")
    return {"analysis": result, "result": result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(analyze({}, company="에이피알"))
