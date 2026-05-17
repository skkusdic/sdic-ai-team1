"""재무 데이터 분석 파이프라인 모듈.

Pipeline Lead 담당: 데이터를 받아서 분석 가능한 결과물로 변환.
모든 금액 단위: 억원
"""

from __future__ import annotations
from claude_client import ask
from data import get_financials
from db import init_db, load_financials, save_financials


def normalize_financials(financials: dict) -> dict:
    """연도 키를 정수로 통일. str/float/int 모두 허용."""
    return {int(float(k)): v for k, v in financials.items()}


def calculate_financial_ratios(financial_data: dict) -> dict:
    financial_data = normalize_financials(financial_data)
    """
    연도별 수익성 지표 계산.

    Args:
        financial_data: {연도: {"매출액": ..., "영업이익": ..., "순이익": ...}}

    Returns: {
        연도: {
            "영업이익률": float,   # %
            "순이익률":   float,   # %
        },
        ...
    }
    """
    result = {}
    for year, d in sorted(financial_data.items()):
        revenue = d.get("매출액", 0)
        op_profit = d.get("영업이익", 0)
        net_income = d.get("순이익", 0)

        result[year] = {
            "영업이익률": round(op_profit / revenue * 100, 1) if revenue else None,
            "순이익률":   round(net_income / revenue * 100, 1) if revenue else None,
        }

    return result


def calculate_growth_rates(financial_data: dict) -> dict:
    financial_data = normalize_financials(financial_data)
    """
    연도별 YoY 성장률 및 전체 CAGR 계산.

    Args:
        financial_data: {연도: {"매출액": ..., "영업이익": ..., "순이익": ...}}

    Returns: {
        "yoy": {
            연도: {"매출액YoY": float, "영업이익YoY": float, "순이익YoY": float},
            ...
        },
        "cagr": {
            "매출액_3y": float,
            "매출액_5y": float,
            "영업이익_3y": float,
        }
    }
    """
    sorted_years = sorted(financial_data.keys())

    # YoY 성장률
    yoy = {}
    for i, yr in enumerate(sorted_years):
        if i == 0:
            yoy[yr] = {"매출액YoY": None, "영업이익YoY": None, "순이익YoY": None}
            continue

        prev = financial_data[sorted_years[i - 1]]
        curr = financial_data[yr]

        def growth(cur_val, prev_val):
            if prev_val and prev_val != 0:
                return round((cur_val - prev_val) / abs(prev_val) * 100, 1)
            return None

        yoy[yr] = {
            "매출액YoY":   growth(curr.get("매출액", 0),   prev.get("매출액", 0)),
            "영업이익YoY": growth(curr.get("영업이익", 0), prev.get("영업이익", 0)),
            "순이익YoY":   growth(curr.get("순이익", 0),   prev.get("순이익", 0)),
        }

    # CAGR 계산 헬퍼
    def cagr(metric: str, n: int) -> float | None:
        if len(sorted_years) <= n:
            return None
        start_val = financial_data[sorted_years[-n - 1]].get(metric, 0)
        end_val = financial_data[sorted_years[-1]].get(metric, 0)
        if start_val <= 0 or end_val <= 0:
            return None
        return round(((end_val / start_val) ** (1 / n) - 1) * 100, 1)

    return {
        "yoy": yoy,
        "cagr": {
            "매출액_3y":   cagr("매출액", 3),
            "매출액_5y":   cagr("매출액", 5),
            "영업이익_3y": cagr("영업이익", 3),
        },
    }


def build_analysis_pipeline(company_name: str) -> dict:
    """
    기업명 하나로 전체 분석 결과물 생성.

    1. 재무 데이터 조회 (캐시 → DART 순)
    2. 수익성 지표 계산
    3. 성장률 계산
    4. Claude 분석 텍스트 생성

    Args:
        company_name: 기업명 (예: "에이피알", "삼성전자")

    Returns: {
        "company": str,
        "financials": dict,
        "ratios": dict,
        "growth": dict,
        "analysis": str,
        "data_source": "cache" | "dart" | "none",
    }
    """
    init_db()

    # 1. 데이터 조회
    financials = load_financials(company_name)
    data_source = "cache"

    if not financials:
        financials = get_financials(company_name)
        data_source = "dart"
        if financials:
            save_financials(company_name, financials)

    if not financials:
        financials = {}

    financials = normalize_financials(financials)

    if not financials:
        return {
            "company": company_name,
            "financials": {},
            "ratios": {},
            "growth": {},
            "analysis": f"{company_name}의 재무 데이터를 찾을 수 없습니다.",
            "data_source": "none",
        }

    # 2-3. 지표 계산
    ratios = calculate_financial_ratios(financials)
    growth = calculate_growth_rates(financials)

    # 4. Claude 분석
    analysis = _generate_analysis(company_name, financials, ratios, growth)

    return {
        "company": company_name,
        "financials": financials,
        "ratios": ratios,
        "growth": growth,
        "analysis": analysis,
        "data_source": data_source,
    }


def _generate_analysis(
    company_name: str,
    financials: dict,
    ratios: dict,
    growth: dict,
) -> str:
    """DART 재무 데이터 기반 Claude 분석 텍스트 생성."""
    sorted_years = sorted(financials.keys())
    latest = sorted_years[-1]

    rows = "\n".join(
        f"{yr}년: 매출 {financials[yr].get('매출액', 0):,}억, "
        f"영업이익률 {ratios[yr]['영업이익률']}%, "
        f"순이익률 {ratios[yr]['순이익률']}%, "
        f"매출YoY {growth['yoy'][yr]['매출액YoY']}%"
        for yr in sorted_years
    )

    cagr_3y = growth["cagr"].get("매출액_3y")
    cagr_str = f"{cagr_3y}%" if cagr_3y is not None else "계산불가"

    prompt = (
        f"아래는 {company_name}의 DART 공시 기반 재무 데이터입니다.\n\n"
        f"{rows}\n\n"
        f"최근 3년 매출 CAGR: {cagr_str}\n\n"
        "위 데이터만을 근거로, 이 기업의 매출 성장 추이, 수익성 변화, "
        "주목할 점을 3~5문장으로 분석하세요. "
        "데이터에 없는 외부 사실은 추정하거나 언급하지 마세요."
    )
    return ask(prompt, max_tokens=500)
