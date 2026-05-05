"""
data.py — DART API + SQLite 데이터 레이어 (Data Lead: 김나은)

담당: 기업 재무 데이터 수집 및 SQLite 저장
"""

import os
from dotenv import load_dotenv

load_dotenv()
DART_API_KEY = os.getenv("DART_API_KEY")

# TODO: dart-fss 연동
# import dart_fss as dart
# dart.set_api_key(DART_API_KEY)

MOCK_DATA = {
    "에이피알": {
        2022: {"매출액": 456_100, "영업이익": 31_200, "순이익": 24_100},
        2023: {"매출액": 689_200, "영업이익": 58_700, "순이익": 45_300},
        2024: {"매출액": 921_400, "영업이익": 89_100, "순이익": 71_200},
    }
}


def get_financials(company: str) -> dict:
    """
    기업의 연도별 재무 데이터를 반환한다.

    Parameters
    ----------
    company : str
        기업명 (예: "에이피알")

    Returns
    -------
    dict
        {연도: {"매출액": int, "영업이익": int, "순이익": int}, ...}
        단위: 백만 원
    """
    # TODO: dart-fss 연동 — 아래 mock 블록을 실제 API 호출로 교체
    # corp_code = get_corp_code(company)
    # rows = get_financial_statements(corp_code)
    # return _parse_dart_rows(rows)

    if company not in MOCK_DATA:
        return {}

    return MOCK_DATA[company]


def get_corp_code(company_name: str) -> str:
    # TODO: DART-FSS로 기업 코드 조회
    pass


def get_financial_statements(corp_code: str) -> list:
    # TODO: DART-FSS로 재무제표 조회
    pass


def _fmt(amount: int) -> str:
    return f"{amount:,} 백만 원"


if __name__ == "__main__":
    target = "에이피알"
    result = get_financials(target)

    if not result:
        print(f"[오류] '{target}' 데이터를 찾을 수 없습니다.")
    else:
        print(f"\n{'=' * 52}")
        print(f"    {target} 연도별 재무 현황  (단위: 백만 원)")
        print(f"{'=' * 52}")
        print(f"{'연도':^6} | {'매출액':>14} | {'영업이익':>12} | {'순이익':>12}")
        print(f"{'-' * 52}")
        for year in sorted(result):
            d = result[year]
            print(
                f"{year:^6} | {_fmt(d['매출액']):>14} | "
                f"{_fmt(d['영업이익']):>12} | {_fmt(d['순이익']):>12}"
            )
        print(f"{'=' * 52}\n")
