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

def classify_growth_profile(
    income: dict,
    terminal_growth_rate: float = 0.015,
    company_events: dict | None = None,
) -> dict:
    """
    DART 매출 데이터 기반 룰 분류로 5개년 성장률 시나리오 자동 생성.
    AI 판단 없이 숫자 기준만 사용.

    company_events: get_dcf_inputs()의 company_events dict (선택).
        제공 시 MAD 이상치 연도에 대해 DART 공시 태그를 확인해
        M&A·영업양수도 등 일회성 이벤트가 확인된 구간만 제외함.
        이벤트 근거 없는 이상치는 구조적 성장으로 간주해 제외하지 않음.

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

    # ── 성장률 이상치 탐지 (이벤트 근거 연동) ─────────────────────────────
    # M&A·영업양수도 등 일회성 이벤트가 확인된 구간만 제외.
    # 이벤트 근거 없는 이상치(구조적 고성장 가능성)는 제외하지 않음.
    _ONEOFF_REVENUE_TAGS = {"합병/분할", "영업양수도"}

    effective_cagr             = cagr
    growth_outlier_note        = ""
    structural_growth_confirmed = False  # 이상치가 구조적 성장이면 True → volatile caps 완화

    yoy_indexed = list(enumerate(yoy))
    clean_indexed, out_indexed = _mad_outliers(yoy_indexed, threshold_pp=0.15)

    if out_indexed:
        med_yoy = statistics.median(yoy)
        confirmed_oneoff: list[tuple[int, float]] = []
        structural_kept:  list[tuple[int, float]] = []

        for idx, g in out_indexed:
            yr_to = sorted_years[idx + 1] if idx + 1 < len(sorted_years) else None
            ev    = (company_events or {}).get(yr_to, {})
            conf  = ev.get("confidence", "none")
            tags  = set(ev.get("event_tags", []))
            is_oneoff = conf in ("high", "medium") and bool(tags & _ONEOFF_REVENUE_TAGS)
            (confirmed_oneoff if is_oneoff else structural_kept).append((idx, g))

        # 일회성 확인 구간만 제외하고 effective_cagr 재계산
        if confirmed_oneoff:
            truly_clean    = [x for x in yoy_indexed if x not in confirmed_oneoff]
            effective_cagr = statistics.mean([g for _, g in truly_clean]) if truly_clean else cagr
            excl_descs = []
            for idx, g in confirmed_oneoff:
                y_from = sorted_years[idx]
                y_to   = sorted_years[idx + 1] if idx + 1 < len(sorted_years) else "?"
                ev     = (company_events or {}).get(y_to, {})
                cause  = "·".join(t for t in set(ev.get("event_tags", [])) & _ONEOFF_REVENUE_TAGS) or "일회성 이벤트"
                direction = "급락" if g < med_yoy else "급등"
                excl_descs.append(f"{y_from}→{y_to}년 {g:.1%}({direction}·{cause})")
            growth_outlier_note = (
                f"[성장률 이상치 제외] {', '.join(excl_descs)} 구간에서 "
                f"일회성 이벤트(M&A·영업양수도)가 확인되어 제외했습니다. "
                f"정제 성장률({effective_cagr:.1%}) 사용 (원래 CAGR {cagr:.1%})."
            )

        # 이벤트 근거 없는 이상치 → 구조적 성장으로 간주, CAGR 유지 + caps 완화
        structural_growth_confirmed = bool(structural_kept)
        if structural_kept:
            kept_descs = []
            for idx, g in structural_kept:
                y_from    = sorted_years[idx]
                y_to      = sorted_years[idx + 1] if idx + 1 < len(sorted_years) else "?"
                direction = "급락" if g < med_yoy else "급등"
                kept_descs.append(f"{y_from}→{y_to}년 {g:.1%}({direction})")
            kept_note = (
                f"[구조적 성장 유지] {', '.join(kept_descs)} 구간이 통계적 이상치이나 "
                f"M&A·영업양수도 등 일회성 이벤트 근거가 없어 제외하지 않습니다 "
                f"(CAGR {effective_cagr:.1%} 유지)."
            )
            growth_outlier_note = "\n".join(filter(None, [growth_outlier_note, kept_note]))

    tgr = terminal_growth_rate

    ec = effective_cagr  # 시나리오 계산에 사용할 정제 CAGR

    if ec > 0.30:
        profile = "high_growth_fade_down"
        # volatile이더라도 구조적 성장 확인 시 보수 caps 완화 (non-volatile 기준 적용)
        use_conservative = volatile and not structural_growth_confirmed
        if use_conservative:
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
            if volatile and structural_growth_confirmed:
                note = (f"정제 CAGR {ec:.1%}이 30%를 초과하고 변동성이 있으나 "
                        "구조적 성장(이벤트 근거 없는 이상치)으로 판단해 완화된 caps를 적용했습니다.")
            else:
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
        "profile":                    profile,
        "historical_cagr":            round(cagr, 4),
        "effective_cagr":             round(effective_cagr, 4),
        "yearly_growth_rates":        [round(r, 4) for r in rates],
        "volatile":                   volatile,
        "structural_growth_confirmed": structural_growth_confirmed,
        "note":                       note,
        "growth_outlier_note":        growth_outlier_note,
    }


def generate_growth_scenarios(
    growth_profile: dict,
    terminal_growth_rate: float = 0.015,
) -> dict:
    """
    classify_growth_profile() 결과를 받아 Bear / Base / Bull 성장률 리스트 생성.
    Base = effective_cagr 기반 합리적 경로 (classify_growth_profile과 독립 계산).
    Bear = Base 대비 보수적 압축. Bull = Base 대비 낙관적 확장.
    모든 숫자는 기업별 effective_cagr과 profile에서 자동 계산 — 고정값 없음.
    """
    profile  = growth_profile.get("profile", "moderate_growth_convergence")
    ec       = growth_profile.get("effective_cagr") or 0.05
    volatile = growth_profile.get("volatile", False)
    tgr      = terminal_growth_rate

    if profile == "high_growth_fade_down":
        if volatile:
            bear_g = [
                min(ec * 0.35, 0.15),
                min(ec * 0.25, 0.10),
                min(ec * 0.15, 0.07),
                min(ec * 0.10, 0.05),
                tgr,
            ]
            base_g = [
                min(ec * 0.70, 0.40),
                min(ec * 0.55, 0.28),
                min(ec * 0.40, 0.18),
                min(ec * 0.28, 0.12),
                min(ec * 0.18, 0.08),
            ]
            bull_g = [
                min(ec * 0.90, 0.60),
                min(ec * 0.72, 0.45),
                min(ec * 0.55, 0.30),
                min(ec * 0.38, 0.20),
                min(ec * 0.25, 0.12),
            ]
            bear_note = "고성장+고변동성 — 성장 급소멸·경쟁 심화 시나리오"
            base_note = "고성장+고변동성 — 합리적 fade-down 기준 시나리오"
            bull_note = "고성장+고변동성 — 변동성 완화·성장 지속 시나리오"
        else:
            bear_g = [
                min(ec * 0.45, 0.20),
                min(ec * 0.32, 0.14),
                min(ec * 0.20, 0.09),
                min(ec * 0.12, 0.06),
                tgr,
            ]
            base_g = [
                min(ec * 0.70, 0.40),
                min(ec * 0.55, 0.28),
                min(ec * 0.40, 0.18),
                min(ec * 0.28, 0.12),
                min(ec * 0.18, 0.08),
            ]
            bull_g = [
                min(ec * 0.90, 0.60),
                min(ec * 0.75, 0.45),
                min(ec * 0.58, 0.32),
                min(ec * 0.42, 0.22),
                min(ec * 0.28, 0.14),
            ]
            bear_note = "고성장 — 성장 조기 정상화·업황 악화 시나리오"
            base_note = "고성장 — 점진적 fade-down 기준 시나리오"
            bull_note = "고성장 — 성장 모멘텀 유지·시장 확대 시나리오"

    elif profile == "moderate_growth_convergence":
        bear_g = [
            max(ec * 0.50, tgr),
            max(ec * 0.38, tgr),
            max(ec * 0.25, tgr),
            tgr,
            tgr,
        ]
        base_g = [
            ec,
            max(ec * 0.80, tgr),
            max(ec * 0.60, tgr),
            max(ec * 0.40, tgr),
            max(ec * 0.25, tgr),
        ]
        bull_g = [
            min(ec * 1.25, 0.35),
            min(ec * 1.10, 0.28),
            ec,
            max(tgr, ec * 0.75),
            max(tgr, ec * 0.45),
        ]
        bear_note = "중성장 — 수요 둔화·비용 압박 보수 시나리오"
        base_note = "중성장 — 현재 성장률 점진 수렴 기준 시나리오"
        bull_note = "중성장 — 시장점유율 확대·수익성 개선 낙관 시나리오"

    elif profile == "low_growth_stable":
        bear_g = [
            max(ec * 0.50, tgr * 0.8),
            tgr,
            tgr,
            tgr,
            tgr,
        ]
        base_g = [
            max(ec, tgr),
            max(ec * 0.90, tgr),
            max(ec * 0.80, tgr),
            max(ec * 0.70, tgr),
            tgr,
        ]
        bull_g = [
            min(max(ec * 1.80, 0.06), 0.12),
            min(max(ec * 1.50, 0.05), 0.10),
            min(max(ec * 1.25, 0.04), 0.08),
            min(max(ec * 1.05, 0.03), 0.06),
            tgr,
        ]
        bear_note = "저성장 — 경기 침체·구조적 성장 한계 시나리오"
        base_note = "저성장 — 현재 성장률 유지·안정 수렴 기준 시나리오"
        bull_note = "저성장 — 신사업·수출 확대 회복 시나리오"

    elif profile == "negative_growth_recovery":
        bear_g = [
            ec,
            ec * 0.75,
            ec * 0.50,
            0.00,
            tgr,
        ]
        base_g = [
            ec * 0.50,
            0.00,
            tgr,
            tgr,
            tgr,
        ]
        bull_g = [
            0.00,
            tgr,
            tgr * 1.5,
            tgr * 1.5,
            tgr,
        ]
        bear_note = "역성장 — 구조적 침체 지속·회복 지연 시나리오"
        base_note = "역성장 — 완만한 회복 기준 시나리오"
        bull_note = "역성장 — 빠른 회복·사업 전환 성공 시나리오"

    else:  # insufficient_data
        bear_g = [max(tgr, 0.015)] * 5
        base_g = [0.05, 0.04, 0.03, 0.02, tgr]
        bull_g = [0.08, 0.07, 0.06, 0.05, tgr]
        bear_note = "데이터 부족 — 보수적 기본값 시나리오"
        base_note = "데이터 부족 — 중간 기본값 시나리오"
        bull_note = "데이터 부족 — 낙관적 기본값 시나리오"

    return {
        "bear": {
            "label":        "Bear",
            "growth_rates": [round(g, 4) for g in bear_g],
            "note":         bear_note,
        },
        "base": {
            "label":        "Base",
            "growth_rates": [round(g, 4) for g in base_g],
            "note":         base_note,
        },
        "bull": {
            "label":        "Bull",
            "growth_rates": [round(g, 4) for g in bull_g],
            "note":         bull_note,
        },
    }


# ── 실질 WACC 계산 ───────────────────────────────────────────────────────

def calculate_full_wacc(
    dcf_inputs: dict,
    capm_ke: float,
    tax_rate: float = 0.24,
    base_rate: float | None = None,
) -> dict:
    """
    정식 WACC: Ke × (E/V) + Kd × (1-t) × (D/V)
    Kd = 이자비용 / 총차입금 (리스부채 제외 — IFRS 16 운영 부채)
    Kd > 20% 비정상 시: ECOS 기준금리 + 200bp credit spread로 안정화.
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
        if base_rate is not None:
            # ECOS 기준금리 + 200bp credit spread로 Kd 안정화
            kd_stable = round(base_rate + 0.02, 4)
            wacc_stable = capm_ke * w_e + kd_stable * (1 - tax_rate) * w_d
            return {
                "wacc":           round(wacc_stable, 4),
                "cost_of_equity": capm_ke,
                "cost_of_debt":   kd_stable,
                "weight_equity":  round(w_e, 4),
                "weight_debt":    round(w_d, 4),
                "note": (
                    f"Kd({kd:.1%}) 비정상 (DART 이자비용에 FX·파생 혼입 의심) "
                    f"→ ECOS 기준금리({base_rate:.2%}) + 200bp = {kd_stable:.2%}로 안정화. "
                    f"WACC = Ke {capm_ke:.2%} × {w_e:.1%} + Kd {kd_stable:.2%} × (1-t) × {w_d:.1%}"
                ),
            }
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


# ── ROIC / 신뢰도 분석 ────────────────────────────────────────────────────

def calculate_roic(dcf_inputs: dict, assumptions: dict) -> dict:
    """
    연도별 ROIC(투자자본수익률) 계산 및 WACC 스프레드 분석.

    ROIC  = NOPAT / Invested Capital
    IC    = Total Equity + Net Financial Debt  (IFRS 16 리스부채 제외)
    NOPAT = 영업이익 × (1 − 유효세율)
    Spread = ROIC − WACC  (양수 = 가치 창출, 음수 = 가치 파괴)

    Returns:
        {
            "roic_by_year": {year: float},
            "latest_roic":  float | None,
            "avg_roic":     float | None,
            "wacc":         float,
            "spread":       float | None,
            "verdict":      str,
            "verdict_note": str,
            "ic_by_year":   {year: float},   # 억원
        }
    """
    inc     = dcf_inputs.get("income_statement", {})
    bs      = dcf_inputs.get("balance_sheet", {})
    wacc    = assumptions.get("discount_rate", 0.09)
    tax     = assumptions.get("tax_rate", 0.24)

    roic_by_year: dict[int, float] = {}
    ic_by_year:   dict[int, float] = {}

    for yr in sorted(inc.keys()):
        inc_y = inc.get(yr, {})
        bs_y  = bs.get(yr, {})

        op = inc_y.get("operating_profit")
        if op is None:
            continue

        total_equity = bs_y.get("total_equity") or 0
        fin_debt = (
            (bs_y.get("short_term_borrowings")             or 0) +
            (bs_y.get("current_portion_of_long_term_debt") or 0) +
            (bs_y.get("long_term_borrowings")              or 0) +
            (bs_y.get("bonds_payable")                     or 0)
        )
        cash     = bs_y.get("cash_and_cash_equivalents") or 0
        net_debt = fin_debt - cash
        ic       = total_equity + net_debt

        if ic <= 0:
            continue

        nopat = op * (1 - tax)
        # 단위 통일: op는 백만원, ic도 백만원 → 비율 계산
        roic_by_year[yr] = round(nopat / ic, 4)
        ic_by_year[yr]   = round(ic / 100, 1)   # 백만원 → 억원 (표시용)

    if not roic_by_year:
        return {
            "roic_by_year": {},
            "latest_roic":  None,
            "avg_roic":     None,
            "wacc":         round(wacc, 4),
            "spread":       None,
            "verdict":      "계산 불가",
            "verdict_note": "투자자본 계산에 필요한 재무제표 데이터가 부족합니다.",
            "ic_by_year":   {},
        }

    avg_roic    = sum(roic_by_year.values()) / len(roic_by_year)
    latest_roic = list(roic_by_year.values())[-1]
    spread      = avg_roic - wacc

    if spread > 0.05:
        verdict = "강한 가치 창출"
        verdict_note = (
            f"평균 ROIC({avg_roic:.1%})가 WACC({wacc:.1%})를 {spread:.1%}p 상회합니다. "
            "자본비용을 크게 웃도는 수익을 창출하는 고품질 기업입니다."
        )
    elif spread > 0.01:
        verdict = "가치 창출"
        verdict_note = (
            f"평균 ROIC({avg_roic:.1%})가 WACC({wacc:.1%})를 {spread:.1%}p 상회합니다. "
            "자본비용 이상의 수익을 꾸준히 창출하고 있습니다."
        )
    elif spread > -0.01:
        verdict = "손익분기"
        verdict_note = (
            f"평균 ROIC({avg_roic:.1%})와 WACC({wacc:.1%})가 거의 같습니다. "
            "가치 창출이 제한적이며 경쟁 심화 또는 자본 비효율 가능성이 있습니다."
        )
    elif spread > -0.05:
        verdict = "가치 파괴 (소폭)"
        verdict_note = (
            f"평균 ROIC({avg_roic:.1%})가 WACC({wacc:.1%})에 미치지 못합니다. "
            "자본비용을 회수하지 못하고 있어 장기 지속성에 주의가 필요합니다."
        )
    else:
        verdict = "가치 파괴"
        verdict_note = (
            f"평균 ROIC({avg_roic:.1%})가 WACC({wacc:.1%})를 {abs(spread):.1%}p 크게 하회합니다. "
            "투자자본 대비 수익성이 심각하게 낮습니다."
        )

    return {
        "roic_by_year": roic_by_year,
        "latest_roic":  round(latest_roic, 4),
        "avg_roic":     round(avg_roic, 4),
        "wacc":         round(wacc, 4),
        "spread":       round(spread, 4),
        "verdict":      verdict,
        "verdict_note": verdict_note,
        "ic_by_year":   ic_by_year,
    }


def calculate_dcf_confidence(dcf_inputs: dict, result: dict, assumptions: dict) -> dict:
    """
    DCF 결과 신뢰도 점수 (0~100점).

    채점 3개 카테고리:
    - 데이터 완전성  (30점): D&A 추출 품질, CAPEX 존재, 재무제표 연수
    - 이익 예측 가능성 (40점): OPM 변동성, 매출 성장 일관성
    - 모델 품질      (30점): FCF 방법론, WACC 출처

    Returns:
        {
            "score":      int (0~100),
            "grade":      str ("A"/"B"/"C"/"D"),
            "grade_note": str,
            "details": [
                {"category": str, "item": str, "max_pts": int,
                 "earned_pts": int, "ok": bool, "note": str},
                ...
            ],
        }
    """
    import statistics as _st

    inc     = dcf_inputs.get("income_statement", {})
    cf      = dcf_inputs.get("cash_flow", {})
    base_yr = dcf_inputs.get("company_info", {}).get("base_year", 2024)
    cf_l    = cf.get(base_yr, {})

    score   = 0
    details: list[dict] = []

    # ── 1. 데이터 완전성 (30점) ──────────────────────────────────────────
    fcf_method = result.get("fcf_method", "")

    # D&A 추출 품질 (10점)
    if fcf_method == "NOPAT_DA_CAPEX_CF_DIRECT":
        score += 10
        details.append({"category": "데이터 완전성", "item": "D&A 직접 추출 (CF 직접)",
                         "max_pts": 10, "earned_pts": 10, "ok": True,
                         "note": "현금흐름표에서 D&A를 직접 추출했습니다."})
    elif fcf_method == "NOPAT_DA_CAPEX_XBRL":
        score += 7
        details.append({"category": "데이터 완전성", "item": "D&A XBRL 주석 추출",
                         "max_pts": 10, "earned_pts": 7, "ok": True,
                         "note": "XBRL 주석에서 D&A를 fallback 추출했습니다."})
    else:
        details.append({"category": "데이터 완전성", "item": "D&A 미추출 (CFO-CAPEX 방식)",
                         "max_pts": 10, "earned_pts": 0, "ok": False,
                         "note": "D&A를 분리하지 못해 FCF 정밀도가 낮습니다."})

    # CAPEX 데이터 존재 (10점)
    has_capex = (
        cf_l.get("capex_tangible")   is not None or
        cf_l.get("capex_intangible") is not None
    )
    if has_capex:
        score += 10
        details.append({"category": "데이터 완전성", "item": "CAPEX 데이터 확보",
                         "max_pts": 10, "earned_pts": 10, "ok": True,
                         "note": "유형/무형 CAPEX를 DART에서 직접 확인했습니다."})
    else:
        details.append({"category": "데이터 완전성", "item": "CAPEX 데이터 없음",
                         "max_pts": 10, "earned_pts": 0, "ok": False,
                         "note": "CAPEX를 추정값(매출 대비 비율)으로 사용했습니다."})

    # 재무제표 연수 (10점)
    n_rev = len([y for y in inc if inc[y].get("revenue") is not None])
    if n_rev >= 5:
        score += 10
        details.append({"category": "데이터 완전성", "item": f"재무 데이터 {n_rev}개년",
                         "max_pts": 10, "earned_pts": 10, "ok": True,
                         "note": "5개년 이상 데이터로 CAGR 신뢰도가 높습니다."})
    elif n_rev >= 3:
        score += 5
        details.append({"category": "데이터 완전성", "item": f"재무 데이터 {n_rev}개년",
                         "max_pts": 10, "earned_pts": 5, "ok": False,
                         "note": "최소 기준(3개년)은 충족하나 추세 신뢰도가 제한됩니다."})
    else:
        details.append({"category": "데이터 완전성", "item": f"재무 데이터 {n_rev}개년",
                         "max_pts": 10, "earned_pts": 0, "ok": False,
                         "note": "데이터가 부족해 CAGR 및 이익률 계산이 불안정합니다."})

    # ── 2. 이익 예측 가능성 (40점) ───────────────────────────────────────
    # OPM 안정성 (20점)
    margins = []
    for yr, d in inc.items():
        rev = d.get("revenue")
        op  = d.get("operating_profit")
        if rev and rev > 0 and op is not None:
            margins.append(op / rev)

    if len(margins) >= 3:
        opm_std = _st.stdev(margins)
        if opm_std < 0.04:
            score += 20
            details.append({"category": "이익 예측 가능성", "item": f"OPM 안정 (σ={opm_std:.1%})",
                             "max_pts": 20, "earned_pts": 20, "ok": True,
                             "note": "영업이익률 변동이 매우 작아 미래 수익 예측이 용이합니다."})
        elif opm_std < 0.08:
            score += 13
            details.append({"category": "이익 예측 가능성", "item": f"OPM 보통 (σ={opm_std:.1%})",
                             "max_pts": 20, "earned_pts": 13, "ok": False,
                             "note": "영업이익률 변동이 다소 있어 예측 불확실성이 존재합니다."})
        elif opm_std < 0.15:
            score += 6
            details.append({"category": "이익 예측 가능성", "item": f"OPM 불안정 (σ={opm_std:.1%})",
                             "max_pts": 20, "earned_pts": 6, "ok": False,
                             "note": "영업이익률 변동이 커서 이익률 가정의 불확실성이 높습니다."})
        else:
            details.append({"category": "이익 예측 가능성", "item": f"OPM 매우 불안정 (σ={opm_std:.1%})",
                             "max_pts": 20, "earned_pts": 0, "ok": False,
                             "note": "영업이익률 변동이 극심해 DCF 이익 가정 신뢰도가 낮습니다."})
    else:
        score += 8
        details.append({"category": "이익 예측 가능성", "item": "OPM 데이터 부족",
                         "max_pts": 20, "earned_pts": 8, "ok": False,
                         "note": "OPM 연도가 부족해 안정성 평가가 불가합니다."})

    # 매출 성장 일관성 (20점)
    revenues = sorted(
        [(y, inc[y]["revenue"]) for y in inc if inc[y].get("revenue")],
        key=lambda x: x[0],
    )
    if len(revenues) >= 3:
        yoy = [
            (revenues[i][1] - revenues[i-1][1]) / revenues[i-1][1]
            for i in range(1, len(revenues))
            if revenues[i-1][1] > 0
        ]
        rev_std = _st.stdev(yoy) if len(yoy) >= 2 else 0.0
        if rev_std < 0.10:
            score += 20
            details.append({"category": "이익 예측 가능성", "item": f"매출 성장 일관 (σ={rev_std:.1%})",
                             "max_pts": 20, "earned_pts": 20, "ok": True,
                             "note": "매출 성장률 변동이 작아 미래 성장률 예측 신뢰도가 높습니다."})
        elif rev_std < 0.25:
            score += 12
            details.append({"category": "이익 예측 가능성", "item": f"매출 성장 보통 (σ={rev_std:.1%})",
                             "max_pts": 20, "earned_pts": 12, "ok": False,
                             "note": "매출 성장률 변동이 다소 있습니다."})
        else:
            score += 5
            details.append({"category": "이익 예측 가능성", "item": f"매출 성장 고변동 (σ={rev_std:.1%})",
                             "max_pts": 20, "earned_pts": 5, "ok": False,
                             "note": "매출 변동성이 높아 성장률 가정의 불확실성이 큽니다."})
    else:
        score += 8
        details.append({"category": "이익 예측 가능성", "item": "매출 데이터 부족",
                         "max_pts": 20, "earned_pts": 8, "ok": False,
                         "note": "매출 연도가 부족해 성장 일관성 평가가 불가합니다."})

    # ── 3. 모델 품질 (30점) ─────────────────────────────────────────────
    # FCF 방법론 (20점)
    if fcf_method == "NOPAT_DA_CAPEX_CF_DIRECT":
        score += 20
        details.append({"category": "모델 품질", "item": "FCF = NOPAT+D&A−CAPEX (최고신뢰)",
                         "max_pts": 20, "earned_pts": 20, "ok": True,
                         "note": "D&A를 직접 분리한 정밀 FCF 계산 방식입니다."})
    elif fcf_method == "NOPAT_DA_CAPEX_XBRL":
        score += 14
        details.append({"category": "모델 품질", "item": "FCF = NOPAT+D&A−CAPEX (XBRL fallback)",
                         "max_pts": 20, "earned_pts": 14, "ok": True,
                         "note": "XBRL 주석 D&A를 사용한 준정밀 FCF 방식입니다."})
    elif fcf_method == "CFO_CAPEX":
        score += 8
        details.append({"category": "모델 품질", "item": "FCF = 영업현금흐름−CAPEX",
                         "max_pts": 20, "earned_pts": 8, "ok": False,
                         "note": "D&A 미분리로 인해 유지/성장 CAPEX 구분이 불가합니다."})
    else:
        details.append({"category": "모델 품질", "item": "FCF = 저신뢰도 proxy",
                         "max_pts": 20, "earned_pts": 0, "ok": False,
                         "note": "D&A·CFO 모두 추출 불가 — 결과를 참고값으로만 활용하세요."})

    # WACC 출처 (10점)
    dr_source = assumptions.get("discount_rate_source", "conservative_default")
    if dr_source == "full_wacc":
        score += 10
        details.append({"category": "모델 품질", "item": "WACC: D/E 가중 정식 계산",
                         "max_pts": 10, "earned_pts": 10, "ok": True,
                         "note": "자기자본·타인자본 비중을 반영한 정식 WACC입니다."})
    elif dr_source == "capm_ke":
        score += 7
        details.append({"category": "모델 품질", "item": "WACC: CAPM β 실측 계산",
                         "max_pts": 10, "earned_pts": 7, "ok": True,
                         "note": "β를 실제 주가 데이터로 산출한 CAPM 기반 할인율입니다."})
    else:
        score += 2
        details.append({"category": "모델 품질", "item": "WACC: 기본값 사용",
                         "max_pts": 10, "earned_pts": 2, "ok": False,
                         "note": "시장 데이터 없어 보수적 기본값(9%)을 사용했습니다."})

    # ── 4. Terminal Value 집중도 (보너스 카테고리, 최대 -10점 패널티) ────────
    val_block = result.get("valuation", {})
    pv_tv     = val_block.get("pv_terminal_value") or 0
    ev        = val_block.get("enterprise_value")  or 1
    tv_ratio  = pv_tv / ev

    if tv_ratio >= 0.80:
        score -= 10
        details.append({
            "category":   "모델 품질",
            "item":       f"Terminal Value 집중도 과다 ({tv_ratio:.0%})",
            "max_pts":    0, "earned_pts": -10, "ok": False,
            "note": (
                f"EV의 {tv_ratio:.0%}가 5년 이후 추정값(TV)에서 나옵니다. "
                "WACC·TGR 가정 1pp 변동에 결과가 크게 흔들리므로 상대가치(PER/PBR) 병행 필수."
            ),
        })
    elif tv_ratio >= 0.65:
        score -= 4
        details.append({
            "category":   "모델 품질",
            "item":       f"Terminal Value 집중도 주의 ({tv_ratio:.0%})",
            "max_pts":    0, "earned_pts": -4, "ok": False,
            "note": f"EV의 {tv_ratio:.0%}가 TV 기반. 할인율 민감도를 확인하세요.",
        })
    else:
        details.append({
            "category":   "모델 품질",
            "item":       f"Terminal Value 집중도 양호 ({tv_ratio:.0%})",
            "max_pts":    0, "earned_pts": 0, "ok": True,
            "note": "TV 비중이 적정 수준으로 5개년 FCF의 기여도가 충분합니다.",
        })

    score = max(0, score)   # 음수 방지
    grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"
    grade_note = {
        "A": "높은 신뢰도 — 핵심 데이터가 충분히 확보됐습니다.",
        "B": "보통 신뢰도 — 일부 가정이 불완전하나 참고 가능합니다.",
        "C": "낮은 신뢰도 — 결과 해석 시 보수적으로 접근하세요.",
        "D": "매우 낮은 신뢰도 — 단순 방향성 참고값으로만 활용하세요.",
    }[grade]

    return {
        "score":      score,
        "grade":      grade,
        "grade_note": grade_note,
        "details":    details,
        "tv_ratio":   round(tv_ratio, 3),
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

    company_events = dcf_inputs.get("company_events", {})  # {year: event_dict}
    growth_info    = classify_growth_profile(income, company_events=company_events)

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
    dep_source = "cf_direct"
    if dep is not None and latest_revenue:
        dep_ratio = dep / latest_revenue
    else:
        # D&A 직접 추출 실패 → 비현금조정 합계는 D&A가 아니므로 proxy로 사용 안 함.
        # FCF 계산은 calculate_dcf()에서 CFO-CAPEX fallback으로 처리됨.
        # 여기서는 UI/assumptions 표시용 임시값만 설정.
        dep = None
        dep_ratio = 0.02
        dep_source = "default_2pct_ui_only"
        warnings.append(
            "D&A 직접 추출 실패: 비현금조정 합계는 D&A가 아니므로 proxy로 사용하지 않습니다 "
            "(외환손익·평가손익·충당금 등이 혼입). "
            "FCF 계산은 CFO - CAPEX 방식으로 전환됩니다."
        )

    # ── CAPEX 과다 투자 감지 — D&A 직접 추출 성공 시에만 비교 가능 ────────────
    if dep is not None and capex_t is not None and latest_revenue:
        total_capex = (capex_t or 0) + (capex_i or 0)
        if total_capex > dep * 2.5:
            growth_capex_est = total_capex - dep
            warnings.append(
                f"CAPEX({total_capex:,.0f}억)이 추정 D&A({dep:,.0f}억)의 "
                f"{total_capex/dep:.1f}배 — 성장 투자 집중 구간으로 판단됩니다. "
                f"성장 CAPEX 추정({growth_capex_est:,.0f}억)은 미래 수익 창출을 위한 것이나, "
                f"현재 DCF는 전체 CAPEX를 비용으로 처리하므로 FCF가 과소 계산될 수 있습니다. "
                f"FCF = CFO - CAPEX 방식의 현재 결과는 보수적 하한선으로 해석하세요."
            )

    # ── 순차입금 ─────────────────────────────────────────────────────────
    bs_latest  = bs.get(base_year, {})
    cash       = bs_latest.get("cash_and_cash_equivalents") or 0
    # IFRS 16 리스부채는 운영 부채(임차료 회계 처리)로 금융 차입금과 성격이 달라 제외
    total_debt = (
        (bs_latest.get("short_term_borrowings")             or 0) +
        (bs_latest.get("current_portion_of_long_term_debt") or 0) +
        (bs_latest.get("long_term_borrowings")              or 0) +
        (bs_latest.get("bonds_payable")                     or 0)
    )
    net_debt = total_debt - cash

    # ── 운전자본 비율 (NWC / 매출) ───────────────────────────────────────
    # 순운전자본 = (유동자산 - 현금) - (유동부채 - 단기차입금)
    cur_assets = bs_latest.get("current_assets")
    cur_liabs  = bs_latest.get("current_liabilities")
    cash_val   = bs_latest.get("cash_and_cash_equivalents") or 0
    st_debt    = (
        (bs_latest.get("short_term_borrowings")             or 0) +
        (bs_latest.get("current_portion_of_long_term_debt") or 0)
    )

    if cur_assets is not None and cur_liabs is not None and latest_revenue:
        nwc      = (cur_assets - cash_val) - (cur_liabs - st_debt)
        raw_wc   = nwc / latest_revenue
        # OPM 기반 sanity check: 고마진 기업은 공급자 우위로 WC 부담 낮음
        if margin is not None and margin > 0.15 and raw_wc > 0.12:
            wc_ratio = round(min(raw_wc, 0.12), 4)
            warnings.append(
                f"NWC ratio({raw_wc:.1%})가 높으나 OPM({margin:.1%})이 높은 고마진 구조이므로 "
                f"12%로 보수 조정했습니다 (공급자 우위·선수금 구조 가능성)."
            )
        elif raw_wc > 0.25:
            wc_ratio = round(min(raw_wc, 0.25), 4)
            warnings.append(f"NWC ratio({raw_wc:.1%}) 이상치 → 25% 상한 적용.")
        else:
            wc_ratio = round(max(-0.20, raw_wc), 4)
    else:
        # OPM 기반 스마트 fallback (BS 없을 때)
        _opm_fb  = margin if margin is not None else 0.10
        wc_ratio = 0.02 if _opm_fb > 0.20 else (0.03 if _opm_fb > 0.10 else 0.05)
        warnings.append(
            f"유동자산/유동부채 데이터 없어 OPM({_opm_fb:.1%}) 기반 "
            f"NWC ratio 추정값 {wc_ratio:.0%}를 사용합니다."
        )

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
    base_rate          = mm.get("macro", {}).get("base_rate")  # ECOS 기준금리

    full_wacc_result = None
    if capm_discount_rate:
        full_wacc_result = calculate_full_wacc(
            dcf_inputs, capm_discount_rate, tax_rate_val, base_rate=base_rate
        )

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
        "terminal_growth_rate":     {
            "high_growth_fade_down":        0.025,
            "moderate_growth_convergence":  0.020,
            "low_growth_stable":            0.015,
            "negative_growth_recovery":     0.010,
        }.get(growth_info["profile"], 0.020),
        "capex_ratio":              round(max(capex_ratio, 0), 4),
        "depreciation_ratio":       round(max(dep_ratio, 0), 4),
        "working_capital_ratio":    wc_ratio,
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
    # 호출자 dict를 변경하지 않기 위한 복사본 (pop 사이드이펙트 방지)
    assumptions = dict(assumptions)
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

    # ── FCF 계산 방식 결정 (3단계 우선순위) ────────────────────────────────
    # 1. NOPAT_DA_CAPEX_CF_DIRECT: CF에서 직접 D&A 추출 성공
    # 2. NOPAT_DA_CAPEX_XBRL:      CF 실패 + XBRL D&A confidence high/medium
    # 3. CFO_CAPEX:                 D&A 없음 + CFO/CAPEX 가용
    # 4. LOW_CONFIDENCE_PROXY:      핵심 데이터 모두 부족
    # noncash_adjustments는 절대 D&A로 사용하지 않음.

    da_direct   = (cf_latest.get("depreciation_total") is not None
                   or cf_latest.get("depreciation") is not None)
    xbrl_total  = cf_latest.get("xbrl_depreciation_total")
    xbrl_conf   = cf_latest.get("xbrl_da_confidence")           # high / medium / low / None
    da_xbrl     = (xbrl_total is not None and xbrl_conf in ("high", "medium"))

    cfo         = cf_latest.get("cash_flow_from_operations")
    capex_raw   = (cf_latest.get("capex_tangible") or 0) + (cf_latest.get("capex_intangible") or 0)

    # 실제 FCF 계산에 사용할 D&A 비율 결정
    if da_direct:
        fcf_method_key  = "NOPAT_DA_CAPEX_CF_DIRECT"
        use_cfo_method  = False
        fcf_margin      = None
    elif da_xbrl:
        fcf_method_key  = "NOPAT_DA_CAPEX_XBRL"
        use_cfo_method  = False
        fcf_margin      = None
        # XBRL D&A → dep_r 덮어쓰기 (per-revenue 비율로 환산)
        dep_r = xbrl_total / base_revenue
        warnings.append(
            f"CF D&A 직접 추출 실패 → XBRL D&A fallback 사용 "
            f"(합산 {xbrl_total:,}억, confidence={xbrl_conf}). "
            f"dep_ratio={dep_r:.2%}로 Method A 적용."
        )
    elif (cfo is not None) and (capex_raw > 0) and (base_revenue > 0):
        fcf_method_key  = "CFO_CAPEX"
        use_cfo_method  = True
        base_fcf_cfo    = cfo - capex_raw
        fcf_margin      = base_fcf_cfo / base_revenue
        warnings.append(
            f"D&A(CF/XBRL) 모두 불가 → CFO - CAPEX 방식으로 FCF 계산 "
            f"(CFO {cfo:,.0f}억, CAPEX {capex_raw:,.0f}억, "
            f"FCF {base_fcf_cfo:,.0f}억, margin {fcf_margin:.2%})."
        )
    else:
        fcf_method_key  = "LOW_CONFIDENCE_PROXY"
        use_cfo_method  = False
        fcf_margin      = None
        warnings.append(
            "D&A(CF/XBRL) 및 CFO-CAPEX 모두 계산 불가. "
            "dep_ratio 기본값(2%)으로 추정하나 신뢰도가 낮습니다."
        )

    # ── fcf_methods_available: 가용 방식 전체 병기 ─────────────────────────
    # (UI에서 사용자가 방식을 선택할 수 있도록 모든 옵션을 반환)
    fcf_methods_available: dict[str, dict] = {}

    if da_direct:
        fcf_methods_available["nopat_da_capex_cf_direct"] = {
            "available":  True,
            "dep_ratio":  round(dep_r, 4),
            "confidence": "high",
            "note":       "CF 직접 추출 D&A 기반 Method A (가장 신뢰)",
        }
    if da_xbrl:
        fcf_methods_available["nopat_da_capex_xbrl"] = {
            "available":         True,
            "xbrl_total_eok":    xbrl_total,
            "dep_ratio":         round(xbrl_total / base_revenue, 4),
            "confidence":        xbrl_conf,
            "note":              f"XBRL D&A fallback Method A (confidence={xbrl_conf})",
        }
    if cfo is not None and capex_raw > 0:
        _cfo_fcf = cfo - capex_raw
        fcf_methods_available["cfo_capex"] = {
            "available":   True,
            "fcf_base_eok": round(_cfo_fcf, 1),
            "fcf_margin":  round(_cfo_fcf / base_revenue, 4) if base_revenue else None,
            "confidence":  "high" if da_xbrl else "medium",
            "note":        "CFO - CAPEX 실제 현금흐름 Method B",
        }

    # ── 성장률 Fade 조정 ─────────────────────────────────────────────────────
    # 슬라이더(g_single)가 DART 기본 1년차 비율(g_yearly[0])과 다르면
    # 비율을 비례 스케일해 fade shape를 보존하면서 슬라이더 의도를 반영.
    # g_yearly 자체가 없으면 g_single → TGR 방향 선형 fade 자동 생성.
    if g_yearly and len(g_yearly) >= 5:
        _first = g_yearly[0]
        if abs(_first) > 0.001 and abs(g_single - _first) / abs(_first) > 0.05:
            _scale = g_single / _first
            g_yearly = [round(max(-0.50, min(1.00, r * _scale)), 4) for r in g_yearly]
    elif not g_yearly:
        _g_end  = max(tgr + 0.005, g_single * 0.45)
        g_yearly = [round(g_single + (_g_end - g_single) * i / 4, 4) for i in range(5)]

    # ── 5개년 추정 (연도별 성장률 있으면 2-Stage, 없으면 단일값 fallback) ──
    # maintenance_capex_multiplier: Bear=1.20, Base=1.00, Bull=0.85
    # D&A 있을 때: FCF = NOPAT + D&A - maintenance_CAPEX - ΔWC
    # D&A 없을 때(CFO): FCF = CFO_margin × revenue (total CAPEX 이미 반영)
    maint_mult   = assumptions.get("maintenance_capex_multiplier", 1.00)
    projection: dict[int, dict] = {}
    cumulative_discount = 1.0
    pv_fcf_sum  = 0.0
    prev_revenue = base_revenue

    for i in range(1, 6):
        g_i      = g_yearly[i - 1] if g_yearly and len(g_yearly) >= i else g_single
        revenue  = prev_revenue * (1 + g_i)

        if use_cfo_method:
            # CFO 방식: D&A 없으므로 maintenance/growth 분리 불가 → total 사용
            fcf         = revenue * fcf_margin
            op_profit   = revenue * op_margin
            nopat       = op_profit * (1 - tax_rate)
            dep         = None
            total_capex      = revenue * cap_r
            maintenance_capex = total_capex
            growth_capex      = 0.0
            delta_wc    = 0.0
        else:
            op_profit   = revenue * op_margin
            nopat       = op_profit * (1 - tax_rate)
            dep         = revenue * dep_r
            total_capex       = revenue * cap_r
            maintenance_capex = min(total_capex, dep * maint_mult)
            growth_capex      = max(0.0, total_capex - maintenance_capex)
            delta_wc    = (revenue - prev_revenue) * wc_r
            fcf         = nopat + dep - maintenance_capex - delta_wc

        cumulative_discount *= (1 + wacc)
        pv_fcf     = fcf / cumulative_discount
        pv_fcf_sum += pv_fcf

        projection[i] = {
            "growth_rate":               round(g_i, 4),
            "revenue":                   round(revenue, 1),
            "operating_profit":          round(op_profit, 1),
            "nopat":                     round(nopat, 1),
            "depreciation":              round(dep, 1) if dep is not None else None,
            "total_capex":               round(total_capex, 1),
            "maintenance_capex":         round(maintenance_capex, 1),
            "growth_capex":              round(growth_capex, 1),
            "change_in_working_capital": round(delta_wc, 1),
            "fcf":                       round(fcf, 1),
            "pv_fcf":                    round(pv_fcf, 1),
            "fcf_method":                fcf_method_key,
        }
        prev_revenue = revenue

    # ── Terminal Value & 기업가치 ─────────────────────────────────────────
    fcf5 = projection[5]["fcf"]
    valuation_status: str = "valid"
    valuation_note:   str = ""

    if fcf5 <= 0:
        terminal_value  = 0.0
        pv_tv           = 0.0
        valuation_status = "invalid_negative_fcf"
        valuation_note  = (
            f"5년차 FCF({fcf5:,.0f}억)이 음수로 추정되어 Terminal Value가 산출되지 않습니다. "
            "역성장·고비용 구조가 지속되는 경우 DCF 계속가치 산정이 불안정합니다. "
            "이 기업은 DCF 단일값보다 시나리오/민감도 또는 상대가치법(PER/PBR)으로 "
            "보조 해석하는 것이 적절합니다."
        )
        warnings.append(valuation_note)
    else:
        terminal_value = fcf5 * (1 + tgr) / (wacc - tgr)
        pv_tv          = terminal_value / cumulative_discount

    enterprise_value = pv_fcf_sum + pv_tv

    if enterprise_value <= 0 and valuation_status == "valid":
        valuation_status = "invalid_negative_ev"
        valuation_note   = (
            f"추정 Enterprise Value({enterprise_value:,.0f}억)이 0 이하입니다. "
            "최근 FCF 흐름 기준으로 기업가치 산출이 불안정합니다. "
            "DCF 단일값보다 시나리오/민감도 또는 상대가치법(PER/PBR)으로 보조 해석하세요."
        )
        warnings.append(valuation_note)

    equity_value = enterprise_value - net_debt

    if equity_value <= 0 and valuation_status == "valid":
        valuation_status = "invalid_negative_equity"
        valuation_note   = (
            f"추정 Enterprise Value({enterprise_value:,.0f}억)이 순차입금({net_debt:,.0f}억)보다 낮아 "
            f"Equity Value가 음수({equity_value:,.0f}억)입니다. "
            "채권자 우선 변제 후 주주에게 돌아오는 잔여가치가 없는 구조입니다. "
            "DCF 단일값보다 시나리오/민감도 또는 상대가치법(PER/PBR)으로 보조 해석하세요."
        )
        warnings.append(valuation_note)

    # valuation_status == "valid"일 때만 VPS 산출. 비정상 케이스는 None 반환.
    value_per_share: int | None = None
    if shares and shares > 0 and valuation_status == "valid":
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
            "valuation_status":    valuation_status,
            "valuation_note":      valuation_note,
        },
        "fcf_method":            fcf_method_key,
        "fcf_methods_available": fcf_methods_available,
        "warnings": warnings,
        "error":    None,
    }


def calculate_dcf_scenarios(dcf_inputs: dict, base_assumptions: dict) -> dict:
    """
    Bear / Base / Bull 세 시나리오 DCF 계산.

    시나리오별 차등 가정:
      - 성장률: generate_growth_scenarios()로 프로파일 기반 자동 생성 (Base 독립 계산)
      - 영업이익률: Bear ×0.85 / Base 기준값 / Bull ×1.15 (배율 방식)
      - 할인율: CAPM 있을 때 Bear max(0.09, capm+1.5pp) / Base max(0.075, min(0.09, capm)) / Bull max(0.065, capm-1pp)
               CAPM 없을 때 Bear 10% / Base 9% / Bull 8%
      - TGR:   고성장/중성장 Bull 2.5%, 나머지 Bear 1.0% / Base 1.5% / Bull 2.0%
      - maintenance_capex_multiplier: Bear 1.20 / Base 1.00 / Bull 0.85

    base_assumptions는 변경하지 않음 (내부에서 복사본 사용).
    """
    income         = dcf_inputs.get("income_statement", {})
    mm             = dcf_inputs.get("market_metrics", {})
    company_events = dcf_inputs.get("company_events", {})

    growth_profile = classify_growth_profile(income, company_events=company_events)
    base_tgr       = base_assumptions.get("terminal_growth_rate", 0.015)
    scenarios_g    = generate_growth_scenarios(growth_profile, terminal_growth_rate=base_tgr)

    current_price = mm.get("current_price")
    base_margin   = base_assumptions.get("operating_margin", 0.10)
    capm_dr       = base_assumptions.get("capm_discount_rate")

    _DR_MIN, _DR_MAX = 0.065, 0.18
    profile = growth_profile.get("profile", "moderate_growth_convergence")

    # ── 시나리오별 할인율 ──────────────────────────────────────────────────
    # bear > base > bull 순서 보장: bear/bull은 항상 base 기준으로 spread
    if capm_dr:
        base_dr = round(min(_DR_MAX, max(_DR_MIN, capm_dr)), 4)
        bear_dr = round(min(_DR_MAX, base_dr + 0.015), 4)
        bull_dr = round(max(_DR_MIN, base_dr - 0.010), 4)
    else:
        bear_dr, base_dr, bull_dr = 0.10, 0.09, 0.08

    # ── 시나리오별 OPM (배율 방식) ────────────────────────────────────────
    bear_margin = round(max(0.0, base_margin * 0.85), 4)
    bull_margin = round(min(0.40, base_margin * 1.15), 4)

    # ── 시나리오별 Terminal Growth Rate ───────────────────────────────────
    if profile in ("high_growth_fade_down", "moderate_growth_convergence"):
        bear_tgr, s_base_tgr, bull_tgr = 0.010, 0.015, 0.025
    else:
        bear_tgr, s_base_tgr, bull_tgr = 0.010, 0.015, 0.020

    scenario_params = {
        "bear": {
            "growth_rates":               scenarios_g["bear"]["growth_rates"],
            "discount_rate":              bear_dr,
            "operating_margin":           bear_margin,
            "terminal_growth_rate":       bear_tgr,
            "maintenance_capex_multiplier": 1.20,
            "label":                      "Bear",
            "note":                       scenarios_g["bear"]["note"],
        },
        "base": {
            "growth_rates":               scenarios_g["base"]["growth_rates"],
            "discount_rate":              base_dr,
            "operating_margin":           base_margin,
            "terminal_growth_rate":       s_base_tgr,
            "maintenance_capex_multiplier": 1.00,
            "label":                      "Base",
            "note":                       scenarios_g["base"]["note"],
        },
        "bull": {
            "growth_rates":               scenarios_g["bull"]["growth_rates"],
            "discount_rate":              bull_dr,
            "operating_margin":           bull_margin,
            "terminal_growth_rate":       bull_tgr,
            "maintenance_capex_multiplier": 0.85,
            "label":                      "Bull",
            "note":                       scenarios_g["bull"]["note"],
        },
    }

    results: dict[str, dict] = {}
    for key, sp in scenario_params.items():
        asm = dict(base_assumptions)
        asm["_build_warnings"]              = []
        asm["revenue_growth_rates"]         = sp["growth_rates"]
        asm["revenue_growth_rate"]          = sp["growth_rates"][0]
        asm["discount_rate"]                = sp["discount_rate"]
        asm["operating_margin"]             = sp["operating_margin"]
        asm["terminal_growth_rate"]         = sp["terminal_growth_rate"]
        asm["maintenance_capex_multiplier"] = sp["maintenance_capex_multiplier"]

        dcf_res = calculate_dcf(dcf_inputs, asm)
        val     = dcf_res.get("valuation", {})
        vps     = val.get("value_per_share")

        gap = None
        if current_price and vps is not None and vps > 0:
            gap = round((vps - current_price) / current_price, 4)

        results[key] = {
            "label":                        sp["label"],
            "growth_rates":                 sp["growth_rates"],
            "discount_rate":                sp["discount_rate"],
            "operating_margin":             sp["operating_margin"],
            "terminal_growth_rate":         sp["terminal_growth_rate"],
            "maintenance_capex_multiplier": sp["maintenance_capex_multiplier"],
            "enterprise_value":             val.get("enterprise_value"),
            "equity_value":                 val.get("equity_value"),
            "value_per_share":              vps,
            "valuation_status":             val.get("valuation_status"),
            "current_price":                current_price,
            "valuation_gap":                gap,
            "note":                         sp["note"],
            "warnings":                     dcf_res.get("warnings", []),
            "error":                        dcf_res.get("error"),
        }

    return {
        "growth_profile": {
            "profile":         growth_profile.get("profile"),
            "historical_cagr": growth_profile.get("historical_cagr"),
            "effective_cagr":  growth_profile.get("effective_cagr"),
            "volatile":        growth_profile.get("volatile"),
            "note":            growth_profile.get("note"),
        },
        "scenarios": results,
    }


def diagnose_dcf_inputs(company_name: str) -> dict:
    """
    DCF 계산 전 입력값·중간 계산값 전체 진단.
    음수 주당가치 원인 분류에 사용.

    Returns: 진단 항목 dict (corp_name, fcf_method, valuation_status, ... 포함)
    """
    from data import get_dcf_inputs

    dcf_inputs = get_dcf_inputs(company_name)
    if not dcf_inputs:
        return {"error": f"{company_name} — 데이터 수집 실패"}

    ci   = dcf_inputs.get("company_info", {})
    inc  = dcf_inputs.get("income_statement", {})
    bs   = dcf_inputs.get("balance_sheet", {})
    cf   = dcf_inputs.get("cash_flow", {})
    mm   = dcf_inputs.get("market_metrics", {})
    base_yr = ci.get("base_year", 2024)

    inc_l = inc.get(base_yr, {})
    bs_l  = bs.get(base_yr, {})
    cf_l  = cf.get(base_yr, {})

    assumptions = build_default_assumptions(dcf_inputs)
    result      = calculate_dcf(dcf_inputs, assumptions)
    val         = result.get("valuation", {})
    proj        = result.get("projection", {})

    return {
        "company_name":              company_name,
        "corp_name":                 ci.get("corp_name"),
        "stock_code":                ci.get("stock_code"),
        "current_price":             mm.get("current_price"),
        # 손익계산서
        "revenue":                   inc_l.get("revenue"),
        "operating_profit":          inc_l.get("operating_profit"),
        "operating_margin":          (
            round(inc_l["operating_profit"] / inc_l["revenue"], 4)
            if inc_l.get("revenue") and inc_l.get("operating_profit") is not None
            else None
        ),
        # 현금흐름표
        "cash_flow_from_operations": cf_l.get("cash_flow_from_operations"),
        "capex_tangible":            cf_l.get("capex_tangible"),
        "capex_intangible":          cf_l.get("capex_intangible"),
        "depreciation_total":        cf_l.get("depreciation_total"),
        "depreciation":              cf_l.get("depreciation"),
        "noncash_adjustments":       cf_l.get("noncash_adjustments"),
        # FCF 계산 방식
        "fcf_method":                proj.get(1, {}).get("fcf_method"),
        # 5년 FCF 요약
        "fcf_by_year":               {yr: p["fcf"] for yr, p in proj.items()},
        # 대차대조표
        "total_debt":                (
            (bs_l.get("short_term_borrowings") or 0) +
            (bs_l.get("current_portion_of_long_term_debt") or 0) +
            (bs_l.get("long_term_borrowings") or 0) +
            (bs_l.get("bonds_payable") or 0)
        ),
        "cash":                      bs_l.get("cash_and_cash_equivalents"),
        "net_debt":                  val.get("net_debt"),
        "shares_outstanding":        val.get("shares_outstanding"),
        # 기업가치
        "terminal_value":            val.get("terminal_value"),
        "enterprise_value":          val.get("enterprise_value"),
        "equity_value":              val.get("equity_value"),
        "value_per_share":           val.get("value_per_share"),
        "valuation_status":          val.get("valuation_status"),
        "valuation_note":            val.get("valuation_note"),
        "warnings":                  result.get("warnings", []),
        "error":                     result.get("error"),
    }


def calculate_relative_valuation(dcf_inputs: dict, assumptions: dict) -> dict:
    """
    PER · PBR · EV/EBIT 기반 상대가치 분석.

    성장 프로파일별 한국 시장 평균 배수 범위를 레퍼런스로 적용해
    내재가치 범위(implied_vps_low ~ implied_vps_high)를 역산한다.

    Returns:
        {
            "current_per": float | None,
            "current_pbr": float | None,
            "current_ev_ebit": float | None,
            "profile":     str,
            "benchmarks":  {"per": [low, high], "pbr": [low, high], "ev_ebit": [low, high]},
            "implied": {
                "per":     {"low": int, "high": int},
                "pbr":     {"low": int, "high": int},
                "ev_ebit": {"low": int, "high": int},
            },
            "note": str,
        }
    """
    inc    = dcf_inputs.get("income_statement", {})
    bs     = dcf_inputs.get("balance_sheet",    {})
    mm     = dcf_inputs.get("market_metrics",   {})
    shares = assumptions.get("shares_outstanding")
    net_debt = assumptions.get("net_debt", 0) or 0

    cp  = mm.get("current_price")
    mkt_cap = (cp * shares / 1e8) if cp and shares else None   # 억원

    # 최신 연도 재무
    latest_yr     = max(inc.keys()) if inc else None
    net_income    = inc[latest_yr].get("net_income")    if latest_yr else None
    op_profit     = inc[latest_yr].get("operating_profit") if latest_yr else None
    total_equity  = bs.get(latest_yr, {}).get("total_equity") if latest_yr else None

    # ── 현재 배수 계산 ───────────────────────────────────────────────────
    current_per     = round(mkt_cap / net_income,    1) if mkt_cap and net_income  and net_income  > 0 else None
    current_pbr     = round(mkt_cap / total_equity,  2) if mkt_cap and total_equity and total_equity > 0 else None
    ev_market       = (mkt_cap + net_debt)               if mkt_cap is not None else None
    current_ev_ebit = round(ev_market / op_profit,   1) if ev_market is not None and op_profit and op_profit > 0 else None

    # ── 프로파일별 한국 시장 평균 배수 레퍼런스 ─────────────────────────
    profile = assumptions.get("growth_profile", "moderate_growth_convergence")
    _BENCH = {
        "high_growth_fade_down":       {"per": [25, 45], "pbr": [3.0, 7.0], "ev_ebit": [20, 35]},
        "moderate_growth_convergence": {"per": [15, 25], "pbr": [1.5, 4.0], "ev_ebit": [12, 20]},
        "low_growth_stable":           {"per": [10, 15], "pbr": [0.8, 1.8], "ev_ebit": [7,  12]},
        "negative_growth_recovery":    {"per": [8,  13], "pbr": [0.5, 1.2], "ev_ebit": [5,  10]},
        "insufficient_data":           {"per": [12, 22], "pbr": [1.0, 2.5], "ev_ebit": [8,  15]},
    }
    bench = _BENCH.get(profile, _BENCH["moderate_growth_convergence"])

    def _vps(equity_억: float | None) -> int | None:
        if equity_억 is None or not shares or shares <= 0:
            return None
        return int(equity_억 * 1e8 / shares)

    # ── 내재가치 범위 역산 ───────────────────────────────────────────────
    implied: dict = {}

    if net_income and net_income > 0 and shares:
        lo = _vps(net_income * bench["per"][0] - net_debt)
        hi = _vps(net_income * bench["per"][1] - net_debt)
        implied["per"] = {"low": lo, "high": hi}

    if total_equity and total_equity > 0 and shares:
        lo = _vps(total_equity * bench["pbr"][0])
        hi = _vps(total_equity * bench["pbr"][1])
        implied["pbr"] = {"low": lo, "high": hi}

    if op_profit and op_profit > 0 and shares:
        lo = _vps((op_profit * bench["ev_ebit"][0]) - net_debt)
        hi = _vps((op_profit * bench["ev_ebit"][1]) - net_debt)
        implied["ev_ebit"] = {"low": lo, "high": hi}

    # ── 종합 노트 ─────────────────────────────────────────────────────────
    note_parts = []
    if current_per:
        lo_b, hi_b = bench["per"]
        if current_per < lo_b:
            note_parts.append(f"PER {current_per:.1f}x는 동종 레퍼런스({lo_b}~{hi_b}x) 하단 이하 — 시장 Downside 반영 가능.")
        elif current_per > hi_b:
            note_parts.append(f"PER {current_per:.1f}x는 동종 레퍼런스({lo_b}~{hi_b}x) 상단 초과 — 성장 프리미엄 반영 상태.")
        else:
            note_parts.append(f"PER {current_per:.1f}x는 동종 레퍼런스({lo_b}~{hi_b}x) 내 — 적정 수준.")
    if not note_parts:
        note_parts.append("배수 계산에 필요한 데이터가 부족합니다.")

    return {
        "current_per":      current_per,
        "current_pbr":      current_pbr,
        "current_ev_ebit":  current_ev_ebit,
        "profile":          profile,
        "benchmarks":       bench,
        "implied":          implied,
        "note":             " ".join(note_parts),
    }


def explain_valuation_gap(dcf_inputs: dict, result: dict, assumptions: dict) -> str:
    """DCF 주당가치와 현재가 차이를 LLM이 자연어로 설명. 실패 시 빈 문자열 반환."""
    try:
        from claude_client import ask
    except ImportError:
        return ""

    company = dcf_inputs.get("company_info", {}).get("company_name", "해당 기업")
    current_price = dcf_inputs.get("market_metrics", {}).get("current_price")
    val = result.get("valuation", {})
    vps = val.get("value_per_share")

    if vps is None or not current_price or current_price <= 0:
        return ""

    gap_pct   = (vps - current_price) / current_price
    direction = "높습니다" if gap_pct > 0 else "낮습니다"

    ev       = val.get("enterprise_value") or 0
    pv_tv    = val.get("pv_terminal_value") or 0
    tv_ratio = pv_tv / ev if ev > 0 else None

    g        = assumptions.get("revenue_growth_rate", 0)
    wacc     = assumptions.get("discount_rate", 0)
    opm      = assumptions.get("operating_margin", 0)
    tgr      = assumptions.get("terminal_growth_rate", 0)
    gp       = assumptions.get("growth_profile", "")
    fcf_method = result.get("fcf_method", "")

    lines = [
        f"{company}의 DCF 분석 결과입니다.",
        f"",
        f"- 현재 주가: {current_price:,}원",
        f"- DCF 주당가치: {vps:,}원",
        f"- 차이: {gap_pct:+.1%} (DCF가 현재가보다 {abs(gap_pct):.1%} {direction})",
        f"- 모델 가정: 매출성장률 {g:.1%} / WACC {wacc:.1%} / OPM {opm:.1%} / TGR {tgr:.1%}",
    ]
    if tv_ratio is not None:
        lines.append(f"- 터미널 가치 비중: EV의 {tv_ratio:.0%}")
    if gp:
        lines.append(f"- 성장 프로파일: {gp}")
    if fcf_method == "LOW_CONFIDENCE_PROXY":
        lines.append("- FCF 추정 신뢰도: 낮음 (D&A·CAPEX 데이터 불완전)")

    lines += [
        "",
        "위 수치를 근거로, DCF 내재가치와 시장가격 사이에 이런 차이가 발생할 수 있는 이유를"
        " 투자자가 이해하기 쉬운 언어로 2~3문장으로 설명해주세요.",
        "재무 구조상의 이유(성장 기대치 차이, 무형자산·브랜드 프리미엄, 시장 심리, 터미널 가치 민감도 등)를 중심으로 서술하세요.",
        "'저평가'·'고평가' 단어는 쓰지 말고, Upside/Downside로 표현하세요.",
        "한국어로 작성하세요.",
    ]

    try:
        return ask("\n".join(lines), max_tokens=300)
    except Exception:
        return ""


def calculate_dcf_montecarlo(
    dcf_inputs:   dict,
    assumptions:  dict,
    n_simulations: int = 1000,
    growth_std:   float = 0.05,
    margin_std:   float = 0.03,
    wacc_std:     float = 0.015,
    seed:         int | None = None,
) -> dict:
    """
    Monte Carlo DCF: 성장률·OPM·WACC를 정규분포로 샘플링해 VPS 분포를 추정.

    Args:
        growth_std:  매출 성장률 표준편차 (기본 ±5pp)
        margin_std:  영업이익률 표준편차 (기본 ±3pp)
        wacc_std:    할인율 표준편차    (기본 ±1.5pp)

    Returns:
        {
            "n_simulations": int,       # 전체 시뮬레이션 수
            "valid_count":   int,       # VPS 계산 성공 수
            "p10": int, "p25": int, "p50": int, "p75": int, "p90": int,
            "mean": float, "std": float,
            "current_price": float | None,
            "upside_probability": float,   # VPS > 현재가 비율 (0~1)
            "histogram": {"bins": list[float], "counts": list[int]},
        }
    """
    try:
        import numpy as np
    except ImportError:
        return {"error": "numpy 미설치 — pip install numpy"}

    rng = np.random.default_rng(seed)
    base_g    = assumptions.get("revenue_growth_rate", 0.05)
    base_m    = assumptions.get("operating_margin", 0.10)
    base_wacc = assumptions.get("discount_rate", 0.09)
    current_price = dcf_inputs.get("market_metrics", {}).get("current_price")

    g_samples    = rng.normal(base_g,    growth_std, n_simulations)
    m_samples    = rng.normal(base_m,    margin_std, n_simulations)
    wacc_samples = rng.normal(base_wacc, wacc_std,   n_simulations)

    vps_list: list[int] = []
    for g_s, m_s, w_s in zip(g_samples, m_samples, wacc_samples):
        # 물리적 제약 적용
        g_s = float(np.clip(g_s, -0.30, 1.00))
        m_s = float(np.clip(m_s,  0.00, 0.60))
        w_s = float(np.clip(w_s,  0.04, 0.30))

        tgr = assumptions.get("terminal_growth_rate", 0.02)
        if w_s <= tgr:
            continue  # 이 조합은 계산 불가 — 스킵

        asm = {k: v for k, v in assumptions.items() if k != "_build_warnings"}
        asm["revenue_growth_rate"]  = g_s
        asm["revenue_growth_rates"] = None   # 단일값 강제 (fade는 calculate_dcf에서 자동 적용)
        asm["operating_margin"]     = m_s
        asm["discount_rate"]        = w_s

        r = calculate_dcf(dcf_inputs, asm)
        vps = r.get("valuation", {}).get("value_per_share")
        if vps is not None and vps > 0:
            vps_list.append(vps)

    if not vps_list:
        return {"error": "유효한 VPS 시뮬레이션이 없습니다.", "n_simulations": n_simulations}

    arr = np.array(vps_list, dtype=float)

    # 히스토그램 (20구간)
    counts, bin_edges = np.histogram(arr, bins=20)
    bin_centers = ((bin_edges[:-1] + bin_edges[1:]) / 2).tolist()

    upside_prob = (float(np.sum(arr > current_price)) / len(arr)) if current_price else None

    return {
        "n_simulations":    n_simulations,
        "valid_count":      len(vps_list),
        "p10":  int(np.percentile(arr, 10)),
        "p25":  int(np.percentile(arr, 25)),
        "p50":  int(np.percentile(arr, 50)),
        "p75":  int(np.percentile(arr, 75)),
        "p90":  int(np.percentile(arr, 90)),
        "mean": round(float(np.mean(arr))),
        "std":  round(float(np.std(arr))),
        "current_price":      current_price,
        "upside_probability": round(upside_prob, 3) if upside_prob is not None else None,
        "histogram": {
            "bins":   [round(b) for b in bin_centers],
            "counts": counts.tolist(),
        },
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
    vps    = val.get("value_per_share")
    v_stat = val.get("valuation_status", "valid")
    v_note = val.get("valuation_note", "")
    if vps is not None:
        print(f"  주당 가치 (DCF)  : {vps:,}원")
    elif v_stat != "valid":
        print(f"  주당 가치 (DCF)  : N/A [{v_stat}]")
        print(f"    └ {v_note}")
    else:
        print("  주당 가치 (DCF)  : N/A (주식수 없음)")

    # ── 현재 주가 vs DCF 비교 ────────────────────────────────────────────
    mm = dcf_inputs.get("market_metrics", {})
    current_price = mm.get("current_price")
    if current_price and vps is not None and vps > 0:
        ratio = current_price / vps
        print(f"  현재 주가        : {current_price:,}원  (DCF 대비 {ratio:.2f}배)")
    elif current_price:
        print(f"  현재 주가        : {current_price:,}원  (DCF 산출 부적합 — 상대가치 보조 해석 권장)")

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

    # ── Bear / Base / Bull 시나리오 ──────────────────────────────────────
    print("\n[ Bear / Base / Bull 시나리오 ]")
    asm_scenario = build_default_assumptions(dcf_inputs)
    scenario_res = calculate_dcf_scenarios(dcf_inputs, asm_scenario)
    gp = scenario_res["growth_profile"]
    print(f"  성장 프로파일: {gp['profile']}  (CAGR {gp['historical_cagr']:.2%} / 정제 {gp['effective_cagr']:.2%})")
    print(f"  {'시나리오':<6} | {'성장률(1~5년)':<40} | {'할인율':>6} | {'OPM':>6} | {'TGR':>5} | {'mCX':>5} | {'주당가치(원)':>12} | {'현재가 대비':>10}")
    print("  " + "-" * 115)
    for k in ("bear", "base", "bull"):
        s = scenario_res["scenarios"][k]
        rates_str = " ".join(f"{r:.1%}" for r in s["growth_rates"])
        vps_str   = f"{s['value_per_share']:>12,}" if s["value_per_share"] is not None else "         N/A"
        gap_str   = f"{s['valuation_gap']:>+.1%}" if s["valuation_gap"] is not None else "   N/A"
        stat_str  = f" [{s.get('valuation_status','valid')}]" if s.get("valuation_status") != "valid" else ""
        err_str   = f" ⚠{s['error']}" if s["error"] else ""
        tgr_str   = f"{s.get('terminal_growth_rate', 0):.1%}"
        mmt_str   = f"{s.get('maintenance_capex_multiplier', 1.0):.2f}"
        print(f"  {s['label']:<6} | {rates_str:<40} | {s['discount_rate']:>5.1%} | {s['operating_margin']:>5.1%} | {tgr_str:>4} | {mmt_str:>5} | {vps_str} | {gap_str}{stat_str}{err_str}")

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
