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


def get_financials(company_name: str) -> dict:
    # TODO: dart-fss 연동 — mock 블록을 실제 API 호출로 교체
    # corp_code = get_corp_code(company_name)
    # rows = get_financial_statements(corp_code)
    # return _parse_dart_rows(rows)
    return MOCK_DATA.get(company_name, {})


if __name__ == "__main__":
    data = get_financials("에이피알")

    if not data:
        print("데이터를 찾을 수 없습니다.")
    else:
        print("\n에이피알 연도별 재무 현황 (단위: 백만 원)")
        print("-" * 50)
        print(f"{'연도':^6} | {'매출액':>12} | {'영업이익':>10} | {'순이익':>10}")
        print("-" * 50)
        for year in sorted(data):
            d = data[year]
            print(f"{year:^6} | {d['매출액']:>12,} | {d['영업이익']:>10,} | {d['순이익']:>10,}")
        print("-" * 50)
