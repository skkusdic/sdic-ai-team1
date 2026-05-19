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
            return summarize_business_report(report_text, company, financials=financials)

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
        "아래 형식으로 재무 분석을 작성하세요.\n\n"
        "【작성 규칙】\n"
        "- 문체: '~임.', '~함.', '~됨.' 등 명사형 종결어로 간결하게 (절대 '~입니다' 사용 금지)\n"
        "- 중요한 수치는 **굵게** 표시 (예: **영업이익률 16.4%**)\n"
        "- 제목·헤더 출력 금지, 번호와 항목명도 출력 금지\n\n"
        f"1. 매출 추세: {min(financials)}~{latest_year}년 매출 성장 흐름\n"
        f"2. 수익성: 영업이익률(현재 **{op_margin}%**) 및 순이익률 변화\n"
        "3. 주요 변화: 전년 대비 가장 두드러진 변화와 시사점\n"
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
