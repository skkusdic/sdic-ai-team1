"""
DCF 밸류에이션용 DART 데이터 수집 모듈
필요 항목: EBIT, Tax rate, Reinvestment, Cash, Debt, Minority interests, #shares, BE
"""

import os
import requests
from dotenv import load_dotenv
from data import _find_corp_code

load_dotenv(override=True)
DART_API_KEY = os.environ["DART_API_KEY"]


# ─────────────────────────────────────────
# 1. 재무제표 데이터 수집 (단일회사 전체 재무제표)
# ─────────────────────────────────────────
def get_financial_statements(corp_code: str, year: str) -> list:
    """
    DART fnlttSinglAcntAll API → 손익계산서 + 재무상태표 + 현금흐름표
    CFS(연결) 우선, 없으면 OFS(별도) 재시도
    """
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
    for fs_div in ("CFS", "OFS"):
        params = {
            "crtfc_key":  DART_API_KEY,
            "corp_code":  corp_code,
            "bsns_year":  year,
            "reprt_code": "11011",
            "fs_div":     fs_div,
        }
        res = requests.get(url, params=params, timeout=10).json()
        if res.get("status") == "000" and res.get("list"):
            return res["list"]
    return []


# ─────────────────────────────────────────
# 2. DCF에 필요한 항목만 파싱
# ─────────────────────────────────────────
def parse_dcf_inputs(statements: list) -> dict:
    """
    재무제표 리스트에서 DCF 계산에 필요한 항목 추출 (단위: 원)
    """
    TARGET = {
        # 손익계산서
        "영업이익":           "ebit",
        "영업이익(손실)":     "ebit",
        "법인세비용":         "tax_expense",
        "법인세차감전순이익": "pretax_income",
        # 재무상태표
        "현금및현금성자산":   "cash",
        "단기차입금":         "short_debt",
        "장기차입금":         "long_debt",
        "비지배지분":         "minority_interest",
        "자본총계":           "total_equity",
        # 현금흐름표
        "유형자산의취득":     "capex_raw",
        "감가상각비":         "depreciation",
        "운전자본의변동":     "delta_working_cap",
    }

    result = {}
    for item in statements:
        name = item.get("account_nm", "").replace(" ", "")
        if name in TARGET:
            key = TARGET[name]
            if key in result:
                continue
            try:
                val = int(str(item.get("thstrm_amount", "0")).replace(",", ""))
                result[key] = val
            except (ValueError, TypeError):
                result[key] = 0

    result["capex"] = abs(result.get("capex_raw", 0))
    result["total_debt"] = result.get("short_debt", 0) + result.get("long_debt", 0)
    return result


# ─────────────────────────────────────────
# 3. 발행주식수 조회
# ─────────────────────────────────────────
def get_shares_issued(corp_code: str, year: str) -> int:
    """DART 주식총수 현황 API → 보통주 발행주식수 반환"""
    url = "https://opendart.fss.or.kr/api/stockTotqySttus.json"
    params = {
        "crtfc_key":  DART_API_KEY,
        "corp_code":  corp_code,
        "bsns_year":  year,
        "reprt_code": "11011",
    }
    res = requests.get(url, params=params, timeout=10).json()
    for item in res.get("list", []):
        if "보통주" in item.get("se", ""):
            try:
                return int(str(item.get("istc_totqy", "0")).replace(",", ""))
            except (ValueError, TypeError):
                return 0
    return 0


# ─────────────────────────────────────────
# 4. DCF 입력값 계산
# ─────────────────────────────────────────
def compute_dcf_inputs(raw: dict) -> dict:
    """파싱된 원시 데이터 → DCF 모델에 바로 쓸 수 있는 값 (단위: 원)"""
    ebit         = raw.get("ebit", 0)
    tax_expense  = raw.get("tax_expense", 0)
    pretax       = raw.get("pretax_income", 0)
    capex        = raw.get("capex", 0)
    depreciation = raw.get("depreciation", 0)
    delta_wc     = raw.get("delta_working_cap", 0)

    tax_rate       = round(tax_expense / pretax, 4) if pretax else 0.25
    ebit_after_tax = ebit * (1 - tax_rate)
    reinvestment   = (capex - depreciation) + delta_wc
    fcff           = ebit_after_tax - reinvestment

    return {
        "ebit":              ebit,
        "tax_rate":          tax_rate,
        "ebit_1_t":          round(ebit_after_tax),
        "capex":             capex,
        "depreciation":      depreciation,
        "delta_wc":          delta_wc,
        "reinvestment":      round(reinvestment),
        "fcff":              round(fcff),
        "cash":              raw.get("cash", 0),
        "total_debt":        raw.get("total_debt", 0),
        "minority_interest": raw.get("minority_interest", 0),
        "book_equity":       raw.get("total_equity", 0),
        "shares_issued":     raw.get("shares_issued", 0),
    }


# ─────────────────────────────────────────
# 5. 메인 실행 함수
# ─────────────────────────────────────────
def get_dcf_data(company_name: str, year: str = "2024") -> dict:
    """
    기업명 입력 → DCF 밸류에이션 입력값 딕셔너리 반환 (단위: 원)

    사용 예:
        data = get_dcf_data("에이피알", "2024")
    """
    print(f"[1/4] {company_name} corp_code 조회 중...")
    corp_code = _find_corp_code(company_name)
    if not corp_code:
        raise ValueError(f"기업을 찾을 수 없습니다: {company_name}")

    print(f"[2/4] {year}년 재무제표 수집 중...")
    statements = get_financial_statements(corp_code, year)
    if not statements:
        raise ValueError(f"{company_name} {year}년 재무제표를 가져올 수 없습니다.")

    print(f"[3/4] DCF 항목 파싱 중...")
    raw = parse_dcf_inputs(statements)

    print(f"[4/4] 발행주식수 조회 중...")
    raw["shares_issued"] = get_shares_issued(corp_code, year)

    print("완료!")
    return compute_dcf_inputs(raw)


if __name__ == "__main__":
    data = get_dcf_data("에이피알", "2024")

    print("\n── DCF 입력값 ──────────────────────────")
    print(f"  EBIT           : {data['ebit']:>20,} 원")
    print(f"  Tax Rate       : {data['tax_rate']:>19.1%}")
    print(f"  EBIT(1-t)      : {data['ebit_1_t']:>20,} 원")
    print(f"  Reinvestment   : {data['reinvestment']:>20,} 원")
    print(f"  FCFF           : {data['fcff']:>20,} 원")
    print(f"────────────────────────────────────────")
    print(f"  Cash           : {data['cash']:>20,} 원")
    print(f"  Total Debt     : {data['total_debt']:>20,} 원")
    print(f"  Minority Int.  : {data['minority_interest']:>20,} 원")
    print(f"  Book Equity    : {data['book_equity']:>20,} 원")
    print(f"  Shares Issued  : {data['shares_issued']:>20,} 주")
    print(f"────────────────────────────────────────")
    print(f"\n※ ROC, RR, growth, WACC는 분석가가 직접 입력하세요.")
