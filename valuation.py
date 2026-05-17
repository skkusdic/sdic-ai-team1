"""DCF(Discounted Cash Flow) 시뮬레이션 계산 모듈.

모든 금액 단위: 억원
주당 가치 단위: 원
"""

from __future__ import annotations


def _normalize(financials: dict) -> dict:
    """연도 키를 정수로 통일."""
    return {int(float(k)): v for k, v in financials.items()}


def calculate_cagr(financials: dict, metric: str = "매출액", years: int = 3) -> float:
    """최근 N개년 CAGR 계산. 데이터 부족 시 0.0 반환."""
    sorted_years = sorted(financials.keys())
    if len(sorted_years) < 2:
        return 0.0

    recent = sorted_years[-min(years + 1, len(sorted_years)):]
    start_val = financials[recent[0]].get(metric, 0)
    end_val = financials[recent[-1]].get(metric, 0)
    n = len(recent) - 1

    if start_val <= 0 or end_val <= 0 or n == 0:
        return 0.0

    return (end_val / start_val) ** (1 / n) - 1


def calculate_avg_op_margin(financials: dict, years: int = 3) -> float:
    """최근 N개년 평균 영업이익률 계산."""
    sorted_years = sorted(financials.keys())
    recent = sorted_years[-years:]

    margins = []
    for yr in recent:
        revenue = financials[yr].get("매출액", 0)
        op_profit = financials[yr].get("영업이익", 0)
        if revenue > 0:
            margins.append(op_profit / revenue)

    return sum(margins) / len(margins) if margins else 0.0


def calculate_dcf(financial_data: dict, assumptions: dict) -> dict:
    """
    DCF 시뮬레이션 계산.

    Args:
        financial_data: {연도: {"매출액": ..., "영업이익": ..., "순이익": ...}} (억원)
        assumptions: {
            "revenue_growth_rate": float,   # 매출 성장률 (예: 0.10 = 10%)
            "op_margin":           float,   # 영업이익률 (예: 0.15 = 15%)
            "tax_rate":            float,   # 법인세율  (예: 0.22 = 22%)
            "discount_rate":       float,   # 할인율/WACC (예: 0.10)
            "terminal_growth_rate":float,   # 영구성장률 (예: 0.02)
            "net_debt":            float,   # 순차입금 (억원, 음수면 순현금)
            "shares_outstanding":  float,   # 발행주식수 (만 주)
        }

    Returns: {
        "projections": [{"year": int, "revenue": float, "op_profit": float, "fcf": float, "pv_fcf": float}],
        "terminal_value": float,
        "pv_terminal_value": float,
        "enterprise_value": float,
        "equity_value": float,
        "value_per_share": float,   # 원 단위
        "assumptions_used": dict,
    }
    """
    g = assumptions["revenue_growth_rate"]
    op_margin = assumptions["op_margin"]
    tax_rate = assumptions["tax_rate"]
    wacc = assumptions["discount_rate"]
    tgr = assumptions["terminal_growth_rate"]
    net_debt = assumptions.get("net_debt", 0.0)
    shares = assumptions.get("shares_outstanding", 1.0)  # 만 주

    # 기준 매출: 가장 최근 연도 매출액
    financial_data = _normalize(financial_data)
    if financial_data:
        latest_year = max(financial_data.keys())
        base_revenue = financial_data[latest_year].get("매출액", 0)
    else:
        base_revenue = 0

    projections = []
    cumulative_discount = 1.0
    pv_fcf_sum = 0.0

    for i in range(1, 6):  # 1~5년차
        revenue = base_revenue * ((1 + g) ** i)
        op_profit = revenue * op_margin
        nopat = op_profit * (1 - tax_rate)  # FCF 근사값 (CAPEX/운전자본 변동 미반영)

        cumulative_discount *= (1 + wacc)
        pv_fcf = nopat / cumulative_discount

        projections.append({
            "year": latest_year + i if financial_data else i,
            "revenue": round(revenue, 1),
            "op_profit": round(op_profit, 1),
            "fcf": round(nopat, 1),
            "pv_fcf": round(pv_fcf, 1),
        })
        pv_fcf_sum += pv_fcf

    # Terminal Value (Gordon Growth Model)
    fcf_year5 = projections[-1]["fcf"]
    if wacc <= tgr:
        terminal_value = 0.0  # 할인율 ≤ 영구성장률이면 계산 불가
    else:
        terminal_value = fcf_year5 * (1 + tgr) / (wacc - tgr)

    pv_terminal_value = terminal_value / cumulative_discount

    enterprise_value = pv_fcf_sum + pv_terminal_value
    equity_value = enterprise_value - net_debt
    # shares_outstanding: 만 주 → 억원/만주 = 만원/주 → ×10000 = 원/주
    value_per_share = (equity_value / shares) * 10_000 if shares > 0 else 0.0

    return {
        "projections": projections,
        "terminal_value": round(terminal_value, 1),
        "pv_terminal_value": round(pv_terminal_value, 1),
        "enterprise_value": round(enterprise_value, 1),
        "equity_value": round(equity_value, 1),
        "value_per_share": round(value_per_share),
        "assumptions_used": assumptions,
    }


def build_default_assumptions(financial_data: dict) -> dict:
    """재무 데이터에서 기본 가정값 자동 계산."""
    return {
        "revenue_growth_rate": round(calculate_cagr(financial_data, "매출액", 3), 4),
        "op_margin": round(calculate_avg_op_margin(financial_data, 3), 4),
        "tax_rate": 0.22,
        "discount_rate": 0.10,
        "terminal_growth_rate": 0.02,
        "net_debt": 0.0,
        "shares_outstanding": 1000.0,  # 만 주 (UI에서 입력받아야 함)
    }
