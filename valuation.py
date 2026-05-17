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


def _mad_outliers(
    indexed: list[tuple[int, float]],
    threshold_pp: float = 0.10,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """
    MAD(Median Absolute Deviation) 기반 이상치 감지.
    - n >= 4: 수정 Z점수(|0.6745*(xi-median)/MAD| > 3.0) 방식
    - n == 3: 중앙값 ± threshold_pp 고정 임계값 방식
    Returns: (filtered, excluded)  — excluded가 비어있으면 이상치 없음.
    최소 2개 유지 보장.
    """
    import statistics as _st
    n = len(indexed)
    if n < 3:
        return indexed, []

    values = [v for _, v in indexed]
    med    = _st.median(values)

    if n >= 4:
        mad = _st.median([abs(v - med) for v in values])
        if mad == 0:
            return indexed, []
        mod_z = [0.6745 * (v - med) / mad for v in values]
        filtered = [(k, v) for (k, v), mz in zip(indexed, mod_z) if abs(mz) <= 3.0]
        excluded = [(k, v) for (k, v), mz in zip(indexed, mod_z) if abs(mz) > 3.0]
    else:
        filtered = [(k, v) for k, v in indexed if abs(v - med) <= threshold_pp]
        excluded = [(k, v) for k, v in indexed if abs(v - med) > threshold_pp]

    if len(filtered) < 2:
        return indexed, []
    return filtered, excluded


def _avg_margin_from_income(income: dict, years: int = 5) -> tuple[float | None, list[str]]:
    """
    영업이익률 평균 + MAD 이상치 자동 제외.
    Returns: (avg_margin, exclusion_notes)
    """
    import statistics as _st

    sorted_years = sorted(income.keys())[-years:]
    year_margins: list[tuple[int, float]] = []
    for yr in sorted_years:
        rev = income[yr].get("revenue")
        op  = income[yr].get("operating_profit")
        if rev and op is not None and rev > 0:
            year_margins.append((yr, op / rev))

    if not year_margins:
        return None, []

    filtered, excluded = _mad_outliers(year_margins, threshold_pp=0.10)
    exclusion_notes: list[str] = []

    if excluded:
        values    = [m for _, m in year_margins]
        med       = _st.median(values)
        clean_avg = sum(m for _, m in filtered) / len(filtered)
        for yr, m in excluded:
            cause = ("업황 침체·대규모 일회성 손실 등 일시적 역풍"
                     if m < med else
                     "일회성 이익·자산 매각 등 일시적 순풍")
            exclusion_notes.append(
                f"[영업이익률 이상치 제외] {yr}년 영업이익률({m:.1%})이 "
                f"다른 연도 중위값({med:.1%}) 대비 크게 이탈한 이상치로 감지되었습니다 "
                f"({cause}). "
                f"이상치 제외 후 평균 영업이익률: {clean_avg:.1%}"
            )
        year_margins = filtered

    avg = sum(m for _, m in year_margins) / len(year_margins)
    return avg, exclusion_notes


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

    # 최근 3년 CAGR (endpoint 기반)
    recent = revenues[-min(4, len(revenues)):]
    n      = len(recent) - 1
    cagr   = (recent[-1] / recent[0]) ** (1 / n) - 1 if recent[0] > 0 else 0.0

    # 연도별 YoY 성장률
    yoy = []
    for i in range(1, len(revenues)):
        if revenues[i - 1] > 0:
            yoy.append((revenues[i] - revenues[i - 1]) / revenues[i - 1])
    volatile = (statistics.stdev(yoy) >= 0.25) if len(yoy) >= 2 else False

    # ── 성장률 이상치 탐지 ─────────────────────────────────────────────────
    # 업황 급락·반등처럼 특정 YoY 구간이 극단적으로 벗어날 때 정제 성장률 사용
    effective_cagr      = cagr
    growth_outlier_note = ""

    yoy_indexed = list(enumerate(yoy))   # [(0, g0), (1, g1), ...]
    clean_indexed, out_indexed = _mad_outliers(yoy_indexed, threshold_pp=0.15)

    if out_indexed:
        med_yoy        = statistics.median(yoy)
        effective_cagr = statistics.mean([g for _, g in clean_indexed])
        excluded_desc  = []
        for idx, g in out_indexed:
            if idx < len(sorted_years) and idx + 1 < len(sorted_years):
                y_from    = sorted_years[idx]
                y_to      = sorted_years[idx + 1]
                direction = "급락" if g < med_yoy else "급등"
                cause     = ("업황 침체·일회성 손실 등 일시적 역풍"
                             if g < med_yoy else
                             "인수합병·일회성 매출 급증 등 일시적 순풍")
                excluded_desc.append(f"{y_from}→{y_to}년 {g:.1%}({direction}·{cause})")
        growth_outlier_note = (
            f"[성장률 이상치 제외] {', '.join(excluded_desc)} 구간이 "
            f"다른 연도 성장률 중위값({med_yoy:.1%}) 대비 크게 벗어납니다. "
            f"일시적 이벤트로 판단하여 해당 구간을 제외했습니다. "
            f"정제 성장률({effective_cagr:.1%})을 DCF 시나리오 기준으로 사용합니다 "
            f"(원래 CAGR {cagr:.1%}은 참고용)."
        )

    tgr = terminal_growth_rate

    ec = effective_cagr  # 시나리오 계산에 사용할 정제 CAGR

    if ec > 0.30:
        profile = "high_growth_fade_down"
        if volatile:
            rates = [
                min(ec, 0.25),
                min(ec * 0.55, 0.18),
                min(ec * 0.38, 0.12),
                min(ec * 0.25, 0.08),
                min(ec * 0.15, 0.05),
            ]
            note = (f"정제 CAGR {ec:.1%}이 30%를 초과하고 연도별 변동성이 큽니다. "
                    "변동성 조정 보수 시나리오를 적용했습니다.")
        else:
            rates = [
                min(ec, 0.35),
                min(ec * 0.70, 0.25),
                min(ec * 0.50, 0.18),
                min(ec * 0.35, 0.12),
                min(ec * 0.25, 0.08),
            ]
            note = f"정제 CAGR {ec:.1%}이 30%를 초과해 고성장 정상화 시나리오를 적용했습니다."

    elif ec > 0.05:
        profile = "moderate_growth_convergence"
        if volatile:
            import statistics as _st
            med = _st.median(yoy) if yoy else ec
            base = min(med, ec * 0.80)
            rates = [
                base,
                base * 0.75,
                base * 0.55,
                base * 0.35,
                max(tgr, base * 0.20),
            ]
            note = (f"정제 CAGR {ec:.1%}이나 연도별 변동성이 큽니다. "
                    f"median 성장률({med:.1%}) 기반 보수 시나리오를 적용했습니다.")
        else:
            rates = [
                ec,
                ec * 0.75,
                ec * 0.55,
                ec * 0.35,
                max(tgr, ec * 0.20),
            ]
            note = f"정제 CAGR {ec:.1%} 기반으로 terminal growth 방향 점진 수렴을 적용했습니다."

    elif ec >= 0:
        profile = "low_growth_stable"
        rates   = [
            ec,
            max(ec * 0.90, tgr),
            max(ec * 0.75, tgr),
            max(ec * 0.60, tgr),
            tgr,
        ]
        note = f"정제 CAGR {ec:.1%} 기반 저성장 — terminal growth 방향 안정적 수렴을 적용했습니다."

    else:
        profile = "negative_growth_recovery"
        rates   = [
            ec,
            ec * 0.50,
            0.00,
            tgr,
            tgr,
        ]
        note = f"정제 CAGR {ec:.1%} 기반 역성장 — 0% 수렴 회복 시나리오를 적용했습니다."

    return {
        "profile":             profile,
        "historical_cagr":     round(cagr, 4),
        "effective_cagr":      round(effective_cagr, 4),
        "yearly_growth_rates": [round(r, 4) for r in rates],
        "volatile":            volatile,
        "note":                note,
        "growth_outlier_note": growth_outlier_note,
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

    kd = interest_exp / total_debt if total_debt > 0 else 0.0

    # Kd 비정상 감지: 이자비용이 총차입금을 초과하면 DART 계정 혼입 의심
    # (파생상품 손실·FX 비용 등이 이자비용에 합산되는 대기업 케이스)
    if kd > 0.20:
        return {
            "wacc":           round(capm_ke, 4),
            "cost_of_equity": capm_ke,
            "cost_of_debt":   round(kd, 4),
            "weight_equity":  round(w_e, 4),
            "weight_debt":    round(w_d, 4),
            "note": (
                f"Kd({kd:.1%})가 20%를 초과해 비정상치로 판단 "
                f"(이자비용에 파생상품 손실·FX 비용 등이 혼입됐을 가능성). "
                f"WACC = Ke({capm_ke:.2%})로 폴백."
            ),
        }

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

def get_auto_sensitivity_ranges(assumptions: dict) -> tuple[list[float], list[float]]:
    """
    기본 가정에서 민감도 분석 범위 자동 생성.
    - 할인율: 기준값 ±3×1.5%p (5%~18% 클램핑)
    - 성장률: 정제 CAGR × [0.5, 0.75, 1.0, 1.25, 1.5] (0% 하한)
    """
    base_dr = assumptions.get("discount_rate", 0.09)
    base_ec = (
        assumptions.get("effective_revenue_cagr")
        or assumptions.get("revenue_growth_rate")
        or 0.05
    )

    step = 0.015
    drs = sorted({
        round(max(0.05, min(0.18, base_dr + i * step)), 3)
        for i in (-2, -1, 0, 1, 2)
    })

    grs = sorted({
        round(max(0.0, base_ec * m), 4)
        for m in (0.50, 0.75, 1.00, 1.25, 1.50)
    })

    return grs, drs


def calculate_implied_discount_rate(
    dcf_inputs:     dict,
    assumptions:    dict,
    market_price:   float,
    bounds:         tuple[float, float] = (0.03, 0.40),
) -> dict:
    """
    역 DCF: 현재 주가에서 시장내재 할인율(WACC) 역산.
    이분법(binary search) 50회 반복.

    Args:
        market_price: 현재 주가 (원 단위)

    Returns:
        {
            "implied_discount_rate": float | None,
            "market_equity_value":   float (억원),
            "target_ev":             float (억원),
            "note":                  str,
        }
    """
    shares = assumptions.get("shares_outstanding")
    if not shares or shares <= 0 or market_price <= 0:
        return {"implied_discount_rate": None,
                "note": "주가 또는 주식수 없어 역산 불가"}

    market_equity_value = market_price * shares / 100_000_000   # 억원
    net_debt = assumptions.get("net_debt", 0) or 0
    target_ev = market_equity_value + net_debt

    def _ev(dr: float) -> float:
        asm = {k: v for k, v in assumptions.items() if k != "_build_warnings"}
        asm["discount_rate"] = dr
        r = calculate_dcf(dcf_inputs, asm)
        return r.get("valuation", {}).get("enterprise_value") or 0.0

    lo, hi = bounds
    ev_lo, ev_hi = _ev(lo), _ev(hi)

    if ev_lo < target_ev:
        return {
            "implied_discount_rate": None,
            "market_equity_value":   round(market_equity_value, 1),
            "target_ev":             round(target_ev, 1),
            "note": (
                f"최저 할인율({lo:.0%}) 적용 EV({ev_lo:,.0f}억)조차 "
                f"시장 EV({target_ev:,.0f}억)보다 낮습니다. "
                f"현재 성장 가정이 지나치게 보수적이거나 "
                f"시장이 성장 가정 외 프리미엄(브랜드·독점력 등)을 부여합니다."
            )
        }
    if ev_hi > target_ev:
        return {
            "implied_discount_rate": None,
            "market_equity_value":   round(market_equity_value, 1),
            "target_ev":             round(target_ev, 1),
            "note": (
                f"최고 할인율({hi:.0%}) 적용 EV({ev_hi:,.0f}억)도 "
                f"시장 EV({target_ev:,.0f}억)보다 높습니다. "
                f"성장 가정이 매우 공격적이거나 시장이 이 수준의 성장을 확신합니다."
            )
        }

    for _ in range(50):
        mid = (lo + hi) / 2
        if abs(hi - lo) < 1e-6:
            break
        if _ev(mid) > target_ev:
            lo = mid
        else:
            hi = mid

    implied = round((lo + hi) / 2, 4)
    ec   = assumptions.get("effective_revenue_cagr") or assumptions.get("revenue_growth_rate", 0)
    opm  = assumptions.get("operating_margin", 0)
    return {
        "implied_discount_rate": implied,
        "market_equity_value":   round(market_equity_value, 1),
        "target_ev":             round(target_ev, 1),
        "note": (
            f"현재 주가({market_price:,.0f}원) 기준 시장내재 WACC: {implied:.2%}. "
            f"DCF 성장 가정(정제 CAGR {ec:.1%}, OPM {opm:.1%})이 맞다면 "
            f"시장은 이 기업에 {implied:.2%}의 자본비용을 요구하는 셈입니다. "
            f"현재 설정 할인율({assumptions.get('discount_rate', 0):.2%})과의 차이가 크면 "
            f"성장 가정 또는 리스크 프리미엄을 재검토하세요."
        )
    }


def calculate_sensitivity(
    dcf_inputs:     dict,
    base_assumptions: dict,
    growth_rates:   list | None = None,
    discount_rates: list | None = None,
) -> dict:
    """
    성장률 × 할인율 조합별 VPS 매트릭스.
    범위 미제공 시 get_auto_sensitivity_ranges()로 자동 생성.

    Returns:
        {"growth_rates": [...], "discount_rates": [...], "matrix": {dr: {gr: vps}}}
    """
    if growth_rates is None or discount_rates is None:
        auto_grs, auto_drs = get_auto_sensitivity_ranges(base_assumptions)
        if growth_rates  is None:
            growth_rates  = auto_grs
        if discount_rates is None:
            discount_rates = auto_drs

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

    growth_info    = classify_growth_profile(income)
    company_events = dcf_inputs.get("company_events", {})  # {year: event_dict}

    if growth_info.get("volatile"):
        warnings.append(growth_info["note"])
    if growth_info.get("growth_outlier_note"):
        growth_out_note = growth_info["growth_outlier_note"]
        warnings.append(growth_out_note)
        # 성장률 이상치 연도에 대한 이벤트 근거 연결
        for yr, ev in company_events.items():
            if str(yr) in growth_out_note and ev.get("event_note"):
                tags_str = "·".join(ev["event_tags"]) if ev["event_tags"] else ""
                warnings.append(
                    f"  └ [{yr}년 공시/뉴스 근거 — 신뢰도 {ev['confidence']}] "
                    + (f"이벤트 유형: {tags_str}. " if tags_str else "")
                    + ev["event_note"]
                )

    # ── 영업이익률 ───────────────────────────────────────────────────────
    margin, margin_outlier_notes = _avg_margin_from_income(income)

    # 이상치 연도 경고에 DART/뉴스 이벤트 보조 근거 연결
    enriched_notes: list[str] = []
    for note in margin_outlier_notes:
        enriched_notes.append(note)
        # 경고 문구에서 연도 추출 후 이벤트 데이터 있으면 보조 설명 추가
        for yr, ev in company_events.items():
            if str(yr) in note and ev.get("event_note"):
                tags_str = "·".join(ev["event_tags"]) if ev["event_tags"] else ""
                enriched_notes.append(
                    f"  └ [{yr}년 공시/뉴스 근거 — 신뢰도 {ev['confidence']}] "
                    + (f"이벤트 유형: {tags_str}. " if tags_str else "")
                    + ev["event_note"]
                )
    warnings.extend(enriched_notes)

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
    else:
        dep_ratio = 0.02
        warnings.append(
            "감가상각비 자동 추출 실패: DART 현금흐름표에서 직접 분리된 항목이 없습니다. "
            "유형자산 장부가액 변동을 이용한 BS 역산은 M&A·자산처분·환율효과 등으로 "
            "왜곡될 수 있어 사용하지 않았습니다. "
            "현재 DCF에는 임시 가정값(매출 대비 2%)이 적용되었습니다. "
            "실제 감가상각비를 아는 경우 UI에서 직접 수정하세요."
        )

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

    # ── 할인율 결정 (우선순위: 실질 WACC > CAPM > 보수 기본값) ────────────
    _DR_MIN, _DR_MAX = 0.06, 0.18   # 합리적 할인율 범위
    effective_dr = 0.09
    dr_source    = "conservative_default"

    if full_wacc_result:
        wacc_val = full_wacc_result.get("wacc")
        if wacc_val and _DR_MIN <= wacc_val <= _DR_MAX:
            effective_dr = round(wacc_val, 4)
            dr_source    = "full_wacc"
        elif capm_discount_rate and _DR_MIN <= capm_discount_rate <= _DR_MAX:
            effective_dr = round(capm_discount_rate, 4)
            dr_source    = "capm_ke"
    elif capm_discount_rate and _DR_MIN <= capm_discount_rate <= _DR_MAX:
        effective_dr = round(capm_discount_rate, 4)
        dr_source    = "capm_ke"

    if dr_source == "conservative_default":
        warnings.append(
            "시장 데이터 없어 할인율 기본값 9%를 사용합니다. "
            "CAPM/WACC 계산이 가능하면 실질 자본비용으로 자동 교체됩니다."
        )

    return {
        "revenue_growth_rate":      round(growth_info["effective_cagr"], 4),
        "revenue_growth_rates":     growth_info["yearly_growth_rates"],
        "historical_revenue_cagr":  growth_info["historical_cagr"],
        "effective_revenue_cagr":   growth_info["effective_cagr"],
        "growth_profile":           growth_info["profile"],
        "growth_assumption_note":   growth_info["note"],
        "operating_margin":         round(margin, 4),
        "tax_rate":                 tax_rate_val,
        "discount_rate":            effective_dr,
        "capm_discount_rate":       capm_discount_rate,
        "full_wacc":                full_wacc_result,
        "discount_rate_source":     dr_source,
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

    # ── FCF 계산 방식 결정 ───────────────────────────────────────────────────
    # Method A (기본): FCF = NOPAT + D&A - CAPEX - ΔWC  (D&A 직접 추출 성공 시)
    # Method B (fallback): FCF = CFO - CAPEX  (D&A 직접 추출 실패 + CFO 가용 시)
    #   → CFO 기반 FCF margin을 매출 대비 비율로 환산해 미래 연도에 적용
    cf_data = dcf_inputs.get("cash_flow", {})
    cf_latest_yr = max(cf_data.keys()) if cf_data else None
    cf_latest = cf_data.get(cf_latest_yr, {}) if cf_latest_yr else {}

    da_available  = (cf_latest.get("depreciation_total") is not None
                     or cf_latest.get("depreciation") is not None)
    cfo           = cf_latest.get("cash_flow_from_operations")
    capex_raw     = (cf_latest.get("capex_tangible") or 0) + (cf_latest.get("capex_intangible") or 0)
    use_cfo_method = (not da_available) and (cfo is not None) and (capex_raw > 0) and (base_revenue > 0)

    fcf_margin: float | None = None  # CFO 방식 사용 시 FCF/매출 비율
    if use_cfo_method:
        base_fcf_cfo = cfo - capex_raw
        fcf_margin   = base_fcf_cfo / base_revenue
        warnings.append(
            f"D&A 직접 추출 실패 → CFO - CAPEX 방식으로 FCF 계산 "
            f"(CFO {cfo:,.0f}억, CAPEX {capex_raw:,.0f}억, FCF {base_fcf_cfo:,.0f}억, "
            f"FCF margin {fcf_margin:.2%}). "
            "D&A 추출 가능 시 Method A(NOPAT+D&A-CAPEX)로 전환하세요."
        )

    # ── 5개년 추정 (연도별 성장률 있으면 2-Stage, 없으면 단일값 fallback) ──
    projection: dict[int, dict] = {}
    cumulative_discount = 1.0
    pv_fcf_sum  = 0.0
    prev_revenue = base_revenue

    for i in range(1, 6):
        g_i      = g_yearly[i - 1] if g_yearly and len(g_yearly) >= i else g_single
        revenue  = prev_revenue * (1 + g_i)

        if use_cfo_method:
            # FCF = FCF_margin × 매출 (CFO 방식)
            fcf      = revenue * fcf_margin
            op_profit = revenue * op_margin
            nopat    = op_profit * (1 - tax_rate)
            dep      = None   # 미계산
            capex    = revenue * cap_r
            delta_wc = 0.0
        else:
            # FCF = NOPAT + D&A - CAPEX - ΔWC (기본 방식)
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
            "growth_rate":           round(g_i, 4),
            "revenue":               round(revenue, 1),
            "operating_profit":      round(op_profit, 1),
            "nopat":                 round(nopat, 1),
            "depreciation":          round(dep, 1) if dep is not None else None,
            "capex":                 round(capex, 1),
            "change_in_working_capital": round(delta_wc, 1),
            "fcf":                   round(fcf, 1),
            "pv_fcf":                round(pv_fcf, 1),
            "fcf_method":            "CFO-CAPEX" if use_cfo_method else "NOPAT+DA-CAPEX",
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

    company_name = sys.argv[1] if len(sys.argv) > 1 else "에이피알"
    print("=" * 65)
    print(f"  DCF 시뮬레이션 테스트 — {company_name}")
    print("=" * 65)

    dcf_inputs  = get_dcf_inputs(company_name)
    if not dcf_inputs:
        print("  데이터 수집 실패")
        sys.exit(1)

    assumptions = build_default_assumptions(dcf_inputs)
    result      = calculate_dcf(dcf_inputs, assumptions)
    asm         = result.get("assumptions", {})

    print("\n[ 기본 가정 ]")
    print(f"  성장 프로파일  : {asm.get('growth_profile')}")
    print(f"  역사적 CAGR    : {asm.get('historical_revenue_cagr', 0):.2%}")
    print(f"  정제 CAGR      : {asm.get('effective_revenue_cagr', 0):.2%}")
    rates = asm.get('revenue_growth_rates', [])
    print(f"  연도별 성장률  : {[f'{r:.1%}' for r in rates]}")
    print(f"  영업이익률     : {asm.get('operating_margin', 0):.2%}")
    _dr_src = asm.get('discount_rate_source', '')
    print(f"  할인율(WACC)   : {asm.get('discount_rate', 0):.2%}  [{_dr_src}]")
    print(f"  CAPM 참고값    : {asm.get('capm_discount_rate', 0):.2%}" if asm.get('capm_discount_rate') else "  CAPM 참고값    : N/A")
    _fw = asm.get('full_wacc') or {}
    if _fw.get('wacc'):
        print(f"  실질 WACC      : {_fw['wacc']:.2%}  ({_fw.get('note','')})")
    print(f"  영구성장률     : {asm.get('terminal_growth_rate', 0):.2%}")
    print(f"  CAPEX ratio    : {asm.get('capex_ratio', 0):.2%}")
    print(f"  감가상각 ratio : {asm.get('depreciation_ratio', 0):.2%}")
    print(f"  순차입금       : {asm.get('net_debt', 0):.1f}억원")

    print("\n[ 5개년 추정 ]")
    for yr, p in result.get("projection", {}).items():
        print(f"  {yr}년차 (g={p['growth_rate']:.1%}): 매출 {p['revenue']:.0f}억 | FCF {p['fcf']:.0f}억 | PV_FCF {p['pv_fcf']:.0f}억")

    val = result.get("valuation", {})
    print("\n[ 기업가치 ]")
    print(f"  Terminal Value   : {val.get('terminal_value', 0):,.0f}억원")
    print(f"  Enterprise Value : {val.get('enterprise_value', 0):,.0f}억원")
    print(f"  순차입금         : {val.get('net_debt', 0):,.0f}억원")
    print(f"  Equity Value     : {val.get('equity_value', 0):,.0f}억원")
    vps = val.get("value_per_share")
    print(f"  주당 가치 (DCF)  : {vps:,}원" if vps else "  주당 가치 (DCF)  : None (주식수 없음)")

    # ── 현재 주가 vs DCF 비교 ────────────────────────────────────────────
    mm = dcf_inputs.get("market_metrics", {})
    current_price = mm.get("current_price")
    if current_price and vps:
        ratio = current_price / vps
        print(f"  현재 주가        : {current_price:,}원  (DCF 대비 {ratio:.2f}배)")

    # ── 민감도 분석 (자동 범위) ───────────────────────────────────────────
    print("\n[ 민감도 분석 — 성장률 × 할인율 VPS(원) ]")
    asm_for_sens = build_default_assumptions(dcf_inputs)  # fresh copy
    sens = calculate_sensitivity(dcf_inputs, asm_for_sens)
    grs = sens["growth_rates"]
    drs = sens["discount_rates"]
    header = "  할인율\\성장률 |" + "".join(f" {g:.1%}  |" for g in grs)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for dr in drs:
        row_mark = " *" if abs(dr - asm.get("discount_rate", 0.09)) < 0.001 else "  "
        row = f"{row_mark} {dr:.2%}       |"
        for gr in grs:
            cell = sens["matrix"][dr].get(gr)
            row += f" {cell:>7,} |" if cell else "    N/A  |"
        print(row)
    print("  (* = 현재 사용 할인율)")

    # ── 역 DCF: 시장내재 할인율 ───────────────────────────────────────────
    if current_price:
        print("\n[ 역 DCF — 시장내재 할인율 ]")
        asm_rev = build_default_assumptions(dcf_inputs)
        implied = calculate_implied_discount_rate(dcf_inputs, asm_rev, current_price)
        idr = implied.get("implied_discount_rate")
        print(f"  시장내재 WACC    : {idr:.2%}" if idr else "  시장내재 WACC    : 역산 불가")
        print(f"  {implied.get('note', '')}")

    print("\n[ 경고 ]")
    for w in result.get("warnings", []):
        print(f"  ⚠ {w}")

    print(f"\n[ 에러 ] {result.get('error')}")
    print("=" * 65)
