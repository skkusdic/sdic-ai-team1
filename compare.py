"""두 기업 재무 데이터 비교 모듈.

모든 금액 단위: 억원
"""

from __future__ import annotations
from claude_client import ask
from data import get_financials
from db import init_db, load_financials, save_financials


def _fetch(company_name: str) -> dict:
    """캐시 → DART 순으로 재무 데이터 조회."""
    init_db()
    cached = load_financials(company_name)
    if cached:
        return cached
    financials = get_financials(company_name)
    if financials:
        save_financials(company_name, financials)
    return financials or {}


def _compute_metrics(financials: dict) -> dict:
    """연도별 재무 데이터에 영업이익률·순이익률·YoY 성장률 추가."""
    result = {}
    sorted_years = sorted(financials.keys())

    for i, yr in enumerate(sorted_years):
        d = financials[yr]
        revenue = d.get("매출액", 0)
        op_profit = d.get("영업이익", 0)
        net_income = d.get("순이익", 0)

        op_margin = round(op_profit / revenue * 100, 1) if revenue else None
        net_margin = round(net_income / revenue * 100, 1) if revenue else None

        prev_revenue = financials[sorted_years[i - 1]].get("매출액", 0) if i > 0 else 0
        yoy_growth = (
            round((revenue - prev_revenue) / prev_revenue * 100, 1)
            if prev_revenue > 0 else None
        )

        result[yr] = {
            "매출액": revenue,
            "영업이익": op_profit,
            "순이익": net_income,
            "영업이익률": op_margin,
            "순이익률": net_margin,
            "매출YoY": yoy_growth,
        }

    return result


def compare_companies(base_company: str, peer_company: str) -> dict:
    """
    두 기업명을 받아 재무 데이터를 조회하고 비교.

    Args:
        base_company: 기준 기업명 (예: "에이피알")
        peer_company: 비교 기업명 (예: "카카오")

    Returns: {
        "base": {"name": str, "metrics": dict},
        "peer": {"name": str, "metrics": dict},
        "common_years": list,
        "latest_summary": dict,   # 최근 연도 핵심 지표 비교
        "ai_summary": str,        # Claude 3줄 요약
    }
    """
    base_financials = _fetch(base_company)
    peer_financials = _fetch(peer_company)

    base_name = base_company
    peer_name = peer_company

    base_metrics = _compute_metrics(base_financials)
    peer_metrics = _compute_metrics(peer_financials)

    common_years = sorted(set(base_metrics) & set(peer_metrics))

    # 최근 연도 핵심 지표 비교
    latest_summary = {}
    if common_years:
        latest = common_years[-1]
        b = base_metrics[latest]
        p = peer_metrics[latest]
        latest_summary = {
            "year": latest,
            "매출액":     {"base": b["매출액"],     "peer": p["매출액"]},
            "영업이익":   {"base": b["영업이익"],   "peer": p["영업이익"]},
            "순이익":     {"base": b["순이익"],     "peer": p["순이익"]},
            "영업이익률": {"base": b["영업이익률"], "peer": p["영업이익률"]},
            "순이익률":   {"base": b["순이익률"],   "peer": p["순이익률"]},
        }

    ai_summary = _generate_summary(
        base_name, base_metrics,
        peer_name, peer_metrics,
        common_years,
    )

    return {
        "base": {"name": base_name, "metrics": base_metrics},
        "peer": {"name": peer_name, "metrics": peer_metrics},
        "common_years": common_years,
        "latest_summary": latest_summary,
        "ai_summary": ai_summary,
    }


def _generate_summary(
    base_name: str, base_metrics: dict,
    peer_name: str, peer_metrics: dict,
    common_years: list,
) -> str:
    """DART 재무 데이터에 근거한 3줄 비교 요약 생성."""
    if not common_years:
        return "공통 연도 데이터가 없어 비교 요약을 생성할 수 없습니다."

    def fmt(metrics: dict) -> str:
        lines = []
        for yr in common_years:
            m = metrics[yr]
            lines.append(
                f"{yr}년: 매출 {m['매출액']:,}억, 영업이익률 {m['영업이익률']}%, "
                f"순이익률 {m['순이익률']}%, 매출YoY {m['매출YoY']}%"
            )
        return "\n".join(lines)

    prompt = (
        f"아래는 DART 공시 기반 재무 데이터입니다.\n\n"
        f"[{base_name}]\n{fmt(base_metrics)}\n\n"
        f"[{peer_name}]\n{fmt(peer_metrics)}\n\n"
        "위 데이터만을 근거로, 두 기업의 수익성·성장성·규모를 비교하는 요약을 "
        "정확히 3문장으로 작성하세요. "
        "데이터에 없는 사실은 추정하거나 언급하지 마세요."
    )
    return ask(prompt, max_tokens=300)
