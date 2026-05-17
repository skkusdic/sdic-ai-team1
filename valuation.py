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


# ── 성장 프로파일 분류 ────────────────────────────────────────────────────

def classify_growth_profile(income: dict, terminal_growth_rate: float = 0.015) -> dict:
    """
    DART 매출 데이터 기반 룰 분류로 5개년 성장률 시나리오 자동 생성.
    AI 판단 없이 숫자 기준만 사용.

    분류 기준:
        CAGR > 30%  → high_growth_fade_down    (강한 fade-down)
        5~30%       → moderate_growth_convergence
        0~5%        → low_growth_stable
        < 0%        → negative_growth_recovery
        연도별 성장률 표준편차 >= 25%p → volatile=True
    """
    import statistics

    sorted_years = sorted(y for y in income if income[y].get("revenue") is not None)
    revenues = [income[y]["revenue"] for y in sorted_years if income[y].get("revenue")]

    if len(revenues) < 2:
        return {
            "profile":             "insufficient_data",
            "historical_cagr":     None,
            "yearly_growth_rates": [0.05] * 5,
            "volatile":            False,
            "note": "데이터 부족으로 기본 성장률 5%를 사용했습니다.",
        }

    # 최근 3년 CAGR
    recent = revenues[-min(4, len(revenues)):]
    n      = len(recent) - 1
    cagr   = (recent[-1] / recent[0]) ** (1 / n) - 1 if recent[0] > 0 else 0.0

    # 연도별 성장률 변동성
    yoy = []
    for i in range(1, len(revenues)):
        if revenues[i - 1] > 0:
            yoy.append((revenues[i] - revenues[i - 1]) / revenues[i - 1])
    volatile = (statistics.stdev(yoy) >= 0.25) if len(yoy) >= 2 else False

    tgr = terminal_growth_rate

    if cagr > 0.30:
        profile = "high_growth_fade_down"
        if volatile:
            # 변동성 큰 고성장: cap을 한 단계 더 강하게
            rates = [
                min(cagr, 0.25),
                min(cagr * 0.55, 0.18),
                min(cagr * 0.38, 0.12),
                min(cagr * 0.25, 0.08),
                min(cagr * 0.15, 0.05),
            ]
            note = (f"최근 CAGR {cagr:.1%}이 30%를 초과하고 연도별 변동성이 큽니다. "
                    "CAGR 직접 적용 금지 — 변동성 조정 보수 시나리오를 적용했습니다.")
        else:
            rates = [
                min(cagr, 0.35),
                min(cagr * 0.70, 0.25),
                min(cagr * 0.50, 0.18),
                min(cagr * 0.35, 0.12),
                min(cagr * 0.25, 0.08),
            ]
            note = f"최근 CAGR {cagr:.1%}이 30%를 초과해 고성장 정상화 시나리오를 적용했습니다."

    elif cagr > 0.05:
        profile = "moderate_growth_convergence"
        if volatile:
            # 변동성 큰 중성장: CAGR 대신 median 기반 cap 적용
            import statistics as _st
            med = _st.median(yoy) if yoy else cagr
            base = min(med, cagr * 0.80)
            rates = [
                base,
                base * 0.75,
                base * 0.55,
                base * 0.35,
                max(tgr, base * 0.20),
            ]
            note = (f"CAGR {cagr:.1%}이나 연도별 변동성이 큽니다. "
                    f"median 성장률({med:.1%}) 기반 보수 시나리오를 적용했습니다.")
        else:
            rates = [
                cagr,
                cagr * 0.75,
                cagr * 0.55,
                cagr * 0.35,
                max(tgr, cagr * 0.20),
            ]
            note = f"CAGR {cagr:.1%} 기반으로 terminal growth 방향 점진 수렴을 적용했습니다."

    elif cagr >= 0:
        profile = "low_growth_stable"
        rates   = [
            cagr,
            max(cagr * 0.90, tgr),
            max(cagr * 0.75, tgr),
            max(cagr * 0.60, tgr),
            tgr,
        ]
        note = f"저성장 기업({cagr:.1%})으로 terminal growth 방향 안정적 수렴을 적용했습니다."

    else:
        profile = "negative_growth_recovery"
        rates   = [
            cagr,
            cagr * 0.50,
            0.00,
            tgr,
            tgr,
        ]
        note = f"역성장 기업({cagr:.1%})으로 0% 수렴 회복 시나리오를 적용했습니다."

    return {
        "profile":             profile,
        "historical_cagr":     round(cagr, 4),
        "yearly_growth_rates": [round(r, 4) for r in rates],
        "volatile":            volatile,
        "note":                note,
    }


# ── 실질 WACC 계산 ───────────────────────────────────────────────────────

def calculate_full_wacc(dcf_inputs: dict, capm_ke: float, tax_rate: float = 0.24) -> dict:
    """
    정식 WACC: Ke × (E/V) + Kd × (1-t) × (D/V)
    Kd = 이자비용 / 총차입금 (리스부채 제외 — IFRS 16 운영 부채)
    순현금 기업(총차입금=0)이면 WACC = Ke 그대로 사용.
    """
    bs      = dcf_inputs.get("balance_sheet", {})
    income  = dcf_inputs.get("income_statement", {})
    base_yr = dcf_inputs.get("company_info", {}).get("base_year", 2024)

    bs_l = bs.get(base_yr, {})
    total_equity = bs_l.get("total_equity") or 0
    total_debt   = (
        (bs_l.get("short_term_borrowings")             or 0) +
        (bs_l.get("current_portion_of_long_term_debt") or 0) +
        (bs_l.get("long_term_borrowings")              or 0) +
        (bs_l.get("bonds_payable")                     or 0)
    )

    V = total_equity + total_debt
    if V <= 0:
        return {"wacc": capm_ke, "note": "자본 데이터 없어 WACC = Ke 사용"}

    w_e = total_equity / V
    w_d = total_debt   / V

    if total_debt <= 0:
        return {
            "wacc":           round(capm_ke, 4),
            "cost_of_equity": capm_ke,
            "cost_of_debt":   None,
            "weight_equity":  1.0,
            "weight_debt":    0.0,
            "note":           "무차입 기업 — WACC = CAPM 자기자본비용",
        }

    inc_l        = income.get(base_yr, {})
    interest_exp = inc_l.get("interest_expense")

    if interest_exp is None:
        return {
            "wacc":           round(capm_ke, 4),
            "cost_of_equity": capm_ke,
            "cost_of_debt":   None,
            "weight_equity":  round(w_e, 4),
            "weight_debt":    round(w_d, 4),
            "note":           "이자비용 데이터 없어 WACC = Ke (부채비용 미반영)",
        }

    kd   = interest_exp / total_debt if total_debt > 0 else 0.0
    wacc = capm_ke * w_e + kd * (1 - tax_rate) * w_d

    return {
        "wacc":           round(wacc, 4),
        "cost_of_equity": capm_ke,
        "cost_of_debt":   round(kd, 4),
        "weight_equity":  round(w_e, 4),
        "weight_debt":    round(w_d, 4),
        "note": (
            f"Ke {capm_ke:.2%} × {w_e:.1%} + Kd {kd:.2%} × (1-t) × {w_d:.1%}"
        ),
    }


# ── 민감도 분석 ───────────────────────────────────────────────────────────

def calculate_sensitivity(
    dcf_inputs:     dict,
    base_assumptions: dict,
    growth_rates:   list | None = None,
    discount_rates: list | None = None,
) -> dict:
    """
    성장률 × 할인율 조합별 VPS 매트릭스.
    단일 성장률(revenue_growth_rate)을 변화시켜 각 셀의 VPS를 계산.

    Returns:
        {"growth_rates": [...], "discount_rates": [...], "matrix": {dr: {gr: vps}}}
    """
    if growth_rates  is None:
        growth_rates  = [0.10, 0.20, 0.30, 0.40, 0.50]
    if discount_rates is None:
        discount_rates = [0.07, 0.09, 0.11]

    matrix: dict = {}
    for dr in discount_rates:
        row: dict = {}
        for gr in growth_rates:
            asm = {k: v for k, v in base_assumptions.items()
                   if k != "_build_warnings"}
            asm["revenue_growth_rate"]  = gr
            asm["revenue_growth_rates"] = None   # 민감도는 단일 성장률로
            asm["discount_rate"]        = dr
            result = calculate_dcf(dcf_inputs, asm)
            row[gr] = result.get("valuation", {}).get("value_per_share")
        matrix[dr] = row

    return {
        "growth_rates":  growth_rates,
        "discount_rates": discount_rates,
        "matrix":        matrix,
    }


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

    # ── 매출 성장률 (룰 기반 성장 프로파일 분류) ──────────────────────────
    cagr = _cagr_from_income(income, "revenue", 3)
    if cagr is None:
        cagr = 0.05
        warnings.append("매출 CAGR 계산 불가 — 기본값 5% 사용")

    growth_info = classify_growth_profile(income)
    if growth_info.get("volatile"):
        warnings.append(growth_info["note"])

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

    # ── 감가상각 ratio ───────────────────────────────────────────────────────
    dep = cf_latest.get("depreciation_total") or cf_latest.get("depreciation")
    if dep is not None and latest_revenue:
        dep_ratio = dep / latest_revenue
        if cf_latest.get("depreciation_estimated"):
            warnings.append("감가상각비를 DART CF에서 직접 조회할 수 없어 BS 유형자산 변동으로 역산했습니다.")
    else:
        dep_ratio = 0.02
        warnings.append("감가상각비 데이터가 없어 기본값 2%(매출 대비)를 사용했습니다.")

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

    # ── CAPM 참고 할인율 + 실질 WACC ────────────────────────────────────
    mm                 = dcf_inputs.get("market_metrics", {})
    capm_discount_rate = mm.get("capm_discount_rate")
    tax_rate_val       = 0.24

    full_wacc_result = None
    if capm_discount_rate:
        full_wacc_result = calculate_full_wacc(dcf_inputs, capm_discount_rate, tax_rate_val)

    return {
        "revenue_growth_rate":      round(cagr, 4),
        "revenue_growth_rates":     growth_info["yearly_growth_rates"],
        "historical_revenue_cagr":  growth_info["historical_cagr"],
        "growth_profile":           growth_info["profile"],
        "growth_assumption_note":   growth_info["note"],
        "operating_margin":         round(margin, 4),
        "tax_rate":                 tax_rate_val,
        "discount_rate":            0.09,
        "capm_discount_rate":       capm_discount_rate,
        "full_wacc":                full_wacc_result,
        "discount_rate_source":     "conservative_default",
        "terminal_growth_rate":     0.015,
        "capex_ratio":              round(max(capex_ratio, 0), 4),
        "depreciation_ratio":       round(max(dep_ratio, 0), 4),
        "working_capital_ratio":    0.00,
        "net_debt":                 round(net_debt, 1),
        "shares_outstanding":       shares_outstanding,
        "_build_warnings":          warnings,
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

    g_single   = assumptions["revenue_growth_rate"]   # 하위 호환 단일값
    g_yearly   = assumptions.get("revenue_growth_rates")  # 2-Stage 연도별 리스트
    op_margin  = assumptions["operating_margin"]
    tax_rate   = assumptions["tax_rate"]
    wacc       = assumptions["discount_rate"]
    tgr        = assumptions["terminal_growth_rate"]
    cap_r      = assumptions.get("capex_ratio", 0.03)
    dep_r      = assumptions.get("depreciation_ratio", 0.02)
    wc_r       = assumptions.get("working_capital_ratio", 0.00)
    net_debt   = assumptions.get("net_debt") or 0.0
    shares     = assumptions.get("shares_outstanding")

    if wacc <= tgr:
        return {
            "error": f"할인율({wacc:.1%})이 영구성장률({tgr:.1%}) 이하라 계산 불가합니다.",
            "warnings": warnings, "assumptions": assumptions,
        }

    # ── 5개년 추정 (연도별 성장률 있으면 2-Stage, 없으면 단일값 fallback) ──
    projection: dict[int, dict] = {}
    cumulative_discount = 1.0
    pv_fcf_sum  = 0.0
    prev_revenue = base_revenue

    for i in range(1, 6):
        g_i      = g_yearly[i - 1] if g_yearly and len(g_yearly) >= i else g_single
        revenue  = prev_revenue * (1 + g_i)
        op_profit = revenue * op_margin
        nopat    = op_profit * (1 - tax_rate)
        dep      = revenue * dep_r
        capex    = revenue * cap_r
        delta_wc = (revenue - prev_revenue) * wc_r
        fcf      = nopat + dep - capex - delta_wc

        cumulative_discount *= (1 + wacc)
        pv_fcf     = fcf / cumulative_discount
        pv_fcf_sum += pv_fcf

        projection[i] = {
            "growth_rate":       round(g_i, 4),
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
    print(f"  성장 프로파일  : {asm.get('growth_profile')}")
    print(f"  역사적 CAGR    : {asm.get('historical_revenue_cagr', 0):.2%}")
    rates = asm.get('revenue_growth_rates', [])
    print(f"  연도별 성장률  : {[f'{r:.1%}' for r in rates]}")
    print(f"  영업이익률     : {asm.get('operating_margin', 0):.2%}")
    print(f"  할인율(WACC)   : {asm.get('discount_rate', 0):.2%}")
    print(f"  CAPM 참고값    : {asm.get('capm_discount_rate', 0):.2%}" if asm.get('capm_discount_rate') else "  CAPM 참고값    : N/A")
    print(f"  영구성장률     : {asm.get('terminal_growth_rate', 0):.2%}")
    print(f"  법인세율       : {asm.get('tax_rate', 0):.2%}")
    print(f"  CAPEX ratio    : {asm.get('capex_ratio', 0):.2%}")
    print(f"  감가상각 ratio : {asm.get('depreciation_ratio', 0):.2%}")
    print(f"  순차입금       : {asm.get('net_debt', 0):.1f}억원")
    print(f"  성장 가정 노트 : {asm.get('growth_assumption_note')}")

    print("\n[ 5개년 추정 ]")
    for yr, p in result.get("projection", {}).items():
        print(f"  {yr}년차 (g={p['growth_rate']:.1%}): 매출 {p['revenue']:.0f}억 | FCF {p['fcf']:.0f}억 | PV_FCF {p['pv_fcf']:.0f}억")

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
