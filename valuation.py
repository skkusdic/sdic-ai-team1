"""DCF(Discounted Cash Flow) 시뮬레이션 계산 모듈.

입력:  get_dcf_inputs() 반환 dict (data.py)
출력:  가정(assumptions) + 5개년 추정(projection) + 기업가치(valuation)

금액 단위: 억원 (value_per_share만 원 단위)
"""

from __future__ import annotations


# ── 레거시 헬퍼 (기존 get_financials 형식 호환) ──────────────────────────

def calculate_cagr(financials: dict, metric: str = "매출액", years: int = 3) -> float:
    """최근 N개년 CAGR. 데이터 부족 시 0.0 반환."""
    sorted_years = sorted(financials.keys())
    if len(sorted_years) < 2:
        return 0.0
    recent = sorted_years[-min(years + 1, len(sorted_years)):]
    start_val = financials[recent[0]].get(metric, 0)
    end_val   = financials[recent[-1]].get(metric, 0)
    n = len(recent) - 1
    if start_val <= 0 or end_val <= 0 or n == 0:
        return 0.0
    return (end_val / start_val) ** (1 / n) - 1


def calculate_avg_op_margin(financials: dict, years: int = 3) -> float:
    """최근 N개년 평균 영업이익률. 기존 get_financials 형식."""
    sorted_years = sorted(financials.keys())[-years:]
    margins = []
    for yr in sorted_years:
        rev = financials[yr].get("매출액", 0)
        op  = financials[yr].get("영업이익", 0)
        if rev > 0:
            margins.append(op / rev)
    return sum(margins) / len(margins) if margins else 0.0


# ── 내부 헬퍼 (get_dcf_inputs 형식) ─────────────────────────────────────

def _cagr_from_income(income: dict, key: str = "revenue", years: int = 3) -> float | None:
    valid = sorted(y for y in income if income[y].get(key) is not None)
    if len(valid) < 2:
        return None
    recent = valid[-min(years + 1, len(valid)):]
    start  = income[recent[0]].get(key)
    end    = income[recent[-1]].get(key)
    n = len(recent) - 1
    if not start or not end or start <= 0 or end <= 0 or n == 0:
        return None
    return (end / start) ** (1 / n) - 1


def _avg_margin_from_income(income: dict, years: int = 3) -> float | None:
    sorted_years = sorted(income.keys())[-years:]
    margins = []
    for yr in sorted_years:
        rev = income[yr].get("revenue")
        op  = income[yr].get("operating_profit")
        if rev and op is not None and rev > 0:
            margins.append(op / rev)
    return sum(margins) / len(margins) if margins else None


# ── 핵심 함수 ────────────────────────────────────────────────────────────

def build_default_assumptions(dcf_inputs: dict) -> dict:
    """
    get_dcf_inputs() 결과를 받아 DCF 기본 가정 dict 생성.
    계산 불가 항목은 기본값 사용 + _build_warnings에 사유 기록.
    """
    warnings: list[str] = []

    income  = dcf_inputs.get("income_statement", {})
    bs      = dcf_inputs.get("balance_sheet", {})
    cf      = dcf_inputs.get("cash_flow", {})
    shares_data = dcf_inputs.get("shares", {})
    base_year   = dcf_inputs.get("company_info", {}).get("base_year", 2024)

    # ── 매출 성장률 ──────────────────────────────────────────────────────
    cagr = _cagr_from_income(income, "revenue", 3)
    if cagr is None:
        cagr = 0.05
        warnings.append("매출 CAGR 계산 불가 — 기본값 5% 사용")

    # ── 영업이익률 ───────────────────────────────────────────────────────
    margin = _avg_margin_from_income(income, 3)
    if margin is None:
        margin = 0.10
        warnings.append("평균 영업이익률 계산 불가 — 기본값 10% 사용")

    # ── 최신 연도 매출 (ratio 계산 기준) ─────────────────────────────────
    latest_revenue: float | None = None
    if income:
        latest_yr = max(income.keys())
        latest_revenue = income[latest_yr].get("revenue")

    # ── CAPEX ratio ──────────────────────────────────────────────────────
    cf_latest  = cf.get(base_year, {})
    capex_t    = cf_latest.get("capex_tangible")
    capex_i    = cf_latest.get("capex_intangible")
    if capex_t is not None and latest_revenue:
        capex_ratio = ((capex_t or 0) + (capex_i or 0)) / latest_revenue
    else:
        capex_ratio = 0.03
        warnings.append("CAPEX 데이터가 없어 기본 CAPEX ratio 3%를 사용했습니다.")

    # ── 감가상각 ratio (유형+무형 합산값 우선, 없으면 유형 단독) ────────────
    dep = cf_latest.get("depreciation_total") or cf_latest.get("depreciation")
    if dep is not None and latest_revenue:
        dep_ratio = dep / latest_revenue
    else:
        dep_ratio = 0.02
        warnings.append("감가상각비 데이터가 없어 기본 감가상각 ratio 2%를 사용했습니다.")

    # ── 순차입금 ─────────────────────────────────────────────────────────
    bs_latest  = bs.get(base_year, {})
    cash       = bs_latest.get("cash_and_cash_equivalents") or 0
    total_debt = (
        (bs_latest.get("short_term_borrowings")             or 0) +
        (bs_latest.get("current_portion_of_long_term_debt") or 0) +
        (bs_latest.get("long_term_borrowings")              or 0) +
        (bs_latest.get("bonds_payable")                     or 0) +
        (bs_latest.get("lease_liabilities")                 or 0)
    )
    net_debt = total_debt - cash

    # ── 주식 수 ──────────────────────────────────────────────────────────
    shares_outstanding = shares_data.get("shares_outstanding")
    shares_note = shares_data.get("source_note", "")
    if shares_outstanding is None:
        warnings.append("발행주식수가 없어 주당가치는 계산하지 않았습니다.")
    elif "미차감" in shares_note:
        warnings.append(f"주식수 출처: {shares_note} — 자기주식 차감값 확인 권장")

    # ── CAPM 참고 할인율 ─────────────────────────────────────────────────
    mm = dcf_inputs.get("market_metrics", {})
    capm_discount_rate = mm.get("capm_discount_rate")

    return {
        "revenue_growth_rate":  round(cagr, 4),
        "operating_margin":     round(margin, 4),
        "tax_rate":             0.24,
        "discount_rate":        0.09,           # 보수적 고정값 유지
        "capm_discount_rate":   capm_discount_rate,  # 참고값 (UI 선택용)
        "discount_rate_source": "conservative_default",
        "terminal_growth_rate": 0.015,
        "capex_ratio":          round(max(capex_ratio, 0), 4),
        "depreciation_ratio":   round(max(dep_ratio, 0), 4),
        "working_capital_ratio": 0.00,
        "net_debt":             round(net_debt, 1),
        "shares_outstanding":   shares_outstanding,
        "_build_warnings":      warnings,
    }


def calculate_dcf(dcf_inputs: dict, assumptions: dict) -> dict:
    """
    5개년 DCF 계산.

    Args:
        dcf_inputs:  get_dcf_inputs() 반환 dict
        assumptions: build_default_assumptions() 반환 dict (사용자 수정 가능)

    Returns:
        assumptions / projection / valuation / warnings / error
    """
    # build_default_assumptions가 심은 경고 수거
    warnings: list[str] = list(assumptions.pop("_build_warnings", []))

    income    = dcf_inputs.get("income_statement", {})
    base_year = dcf_inputs.get("company_info", {}).get("base_year", 2024)

    # ── 입력 검증 ────────────────────────────────────────────────────────
    if not income:
        return {"error": "매출 데이터가 없습니다. 기업명을 확인해주세요.",
                "warnings": warnings, "assumptions": assumptions}

    latest_yr    = max(income.keys())
    base_revenue = income[latest_yr].get("revenue")

    if not base_revenue or base_revenue <= 0:
        return {"error": "최신 연도 매출액이 없어 DCF 계산이 불가합니다.",
                "warnings": warnings, "assumptions": assumptions}

    g        = assumptions["revenue_growth_rate"]
    op_margin = assumptions["operating_margin"]
    tax_rate  = assumptions["tax_rate"]
    wacc      = assumptions["discount_rate"]
    tgr       = assumptions["terminal_growth_rate"]
    cap_r     = assumptions.get("capex_ratio", 0.03)
    dep_r     = assumptions.get("depreciation_ratio", 0.02)
    wc_r      = assumptions.get("working_capital_ratio", 0.00)
    net_debt  = assumptions.get("net_debt") or 0.0
    shares    = assumptions.get("shares_outstanding")

    if wacc <= tgr:
        return {
            "error": f"할인율({wacc:.1%})이 영구성장률({tgr:.1%}) 이하라 계산 불가합니다.",
            "warnings": warnings, "assumptions": assumptions,
        }

    # ── 5개년 추정 ───────────────────────────────────────────────────────
    projection: dict[int, dict] = {}
    cumulative_discount = 1.0
    pv_fcf_sum = 0.0
    prev_revenue = base_revenue

    for i in range(1, 6):
        revenue   = base_revenue * ((1 + g) ** i)
        op_profit = revenue * op_margin
        nopat     = op_profit * (1 - tax_rate)
        dep       = revenue * dep_r
        capex     = revenue * cap_r
        delta_wc  = (revenue - prev_revenue) * wc_r
        fcf       = nopat + dep - capex - delta_wc

        cumulative_discount *= (1 + wacc)
        pv_fcf     = fcf / cumulative_discount
        pv_fcf_sum += pv_fcf

        projection[i] = {
            "revenue":           round(revenue, 1),
            "operating_profit":  round(op_profit, 1),
            "nopat":             round(nopat, 1),
            "depreciation":      round(dep, 1),
            "capex":             round(capex, 1),
            "fcf":               round(fcf, 1),
            "pv_fcf":            round(pv_fcf, 1),
        }
        prev_revenue = revenue

    # ── Terminal Value & 기업가치 ─────────────────────────────────────────
    fcf5            = projection[5]["fcf"]
    terminal_value  = fcf5 * (1 + tgr) / (wacc - tgr)
    pv_tv           = terminal_value / cumulative_discount
    enterprise_value = pv_fcf_sum + pv_tv
    equity_value    = enterprise_value - net_debt

    value_per_share: int | None = None
    if shares and shares > 0:
        # 억원 → 원 변환 후 주식 수로 나눔
        value_per_share = round(equity_value * 100_000_000 / shares)

    return {
        "assumptions": assumptions,
        "projection":  projection,
        "valuation": {
            "terminal_value":      round(terminal_value, 1),
            "pv_terminal_value":   round(pv_tv, 1),
            "enterprise_value":    round(enterprise_value, 1),
            "net_debt":            round(net_debt, 1),
            "equity_value":        round(equity_value, 1),
            "shares_outstanding":  shares,
            "value_per_share":     value_per_share,
        },
        "warnings": warnings,
        "error":    None,
    }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    from data import get_dcf_inputs

    print("=" * 60)
    print("  DCF 시뮬레이션 테스트 — 에이피알")
    print("=" * 60)

    dcf_inputs  = get_dcf_inputs("에이피알")
    if not dcf_inputs:
        print("  데이터 수집 실패")
        sys.exit(1)

    assumptions = build_default_assumptions(dcf_inputs)
    result      = calculate_dcf(dcf_inputs, assumptions)

    print("\n[ 기본 가정 ]")
    asm = result.get("assumptions", {})
    print(f"  매출 성장률    : {asm.get('revenue_growth_rate', 0):.2%}")
    print(f"  영업이익률     : {asm.get('operating_margin', 0):.2%}")
    print(f"  할인율(WACC)   : {asm.get('discount_rate', 0):.2%}")
    print(f"  영구성장률     : {asm.get('terminal_growth_rate', 0):.2%}")
    print(f"  법인세율       : {asm.get('tax_rate', 0):.2%}")
    print(f"  CAPEX ratio    : {asm.get('capex_ratio', 0):.2%}")
    print(f"  감가상각 ratio : {asm.get('depreciation_ratio', 0):.2%}")
    print(f"  순차입금       : {asm.get('net_debt', 0):.1f}억원")

    print("\n[ 5개년 추정 ]")
    for yr, p in result.get("projection", {}).items():
        print(f"  {yr}년차: 매출 {p['revenue']:.0f}억 | FCF {p['fcf']:.0f}억 | PV_FCF {p['pv_fcf']:.0f}억")

    val = result.get("valuation", {})
    print("\n[ 기업가치 ]")
    print(f"  Terminal Value   : {val.get('terminal_value', 0):.0f}억원")
    print(f"  Enterprise Value : {val.get('enterprise_value', 0):.0f}억원")
    print(f"  순차입금         : {val.get('net_debt', 0):.0f}억원")
    print(f"  Equity Value     : {val.get('equity_value', 0):.0f}억원")
    vps = val.get("value_per_share")
    print(f"  주당 가치        : {vps:,}원" if vps else "  주당 가치        : None (주식수 없음)")

    print("\n[ 경고 ]")
    for w in result.get("warnings", []):
        print(f"  ⚠ {w}")

    print(f"\n[ 에러 ] {result.get('error')}")
    print("=" * 60)
