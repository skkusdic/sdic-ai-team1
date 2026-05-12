import os
import sqlite3
import dart_fss as dart
from dotenv import load_dotenv

load_dotenv()
dart.set_api_key(os.getenv("DART_API_KEY"))
dart.enable_spinner(False)


def get_corp_codes(company_name: str) -> list:
    corp_list = dart.get_corp_list()
    results = corp_list.find_by_corp_name(company_name, exactly=True)
    if not results:
        results = corp_list.find_by_corp_name(company_name, exactly=False)
    if not results:
        raise ValueError(f"기업을 찾을 수 없습니다: {company_name}")
    return [r.corp_code for r in results]


# label → (표준키, 부호): 손실 표기는 -1로 부호 반전
_LABEL_MAP = {
    "매출액":          ("매출액",   1),
    "영업수익":        ("매출액",   1),  # IT 업종(카카오·네이버) 표기
    "영업이익":        ("영업이익",  1),
    "영업손실":        ("영업이익", -1),  # 적자 회사 표기
    "영업이익(손실)":  ("영업이익",  1),  # 괄호 병기 표기 — 값이 음수면 그대로 음수
    "당기순이익":      ("순이익",   1),
    "당기순손실":      ("순이익",  -1),  # 적자 회사 표기
    "당기순이익(손실)": ("순이익",   1),  # 괄호 병기 표기 — 값이 음수면 그대로 음수
}


def _fs_has_data(fs) -> bool:
    for key in ("cis", "is"):
        try:
            df = fs[key]
            if df is not None and not df.empty:
                return True
        except (KeyError, TypeError):
            pass
    return False


def get_financial_statements(corp_codes: list):
    # 동명 기업 여러 개 순차 시도, CFS 우선 → OFS 폴백
    for corp_code in corp_codes:
        for separate in (False, True):
            try:
                fs = dart.extract(
                    corp_code=corp_code,
                    bgn_de="20200101",
                    end_de="20251231",
                    report_tp="annual",
                    separate=separate,
                )
                if _fs_has_data(fs):
                    return fs
            except Exception:
                pass
    raise ValueError("재무제표를 가져올 수 없습니다.")


def _parse_dart_fs(fs) -> dict:
    df = fs["cis"]
    if df is None:
        df = fs["is"]
    if df is None:
        raise ValueError("손익계산서 데이터를 찾을 수 없습니다.")

    label_col = [c for c in df.columns if "label_ko" in str(c)][0]
    year_cols = {
        str(c[0])[:4]: c
        for c in df.columns
        if isinstance(c, tuple) and len(str(c[0])) >= 4 and str(c[0])[:4].isdigit()
    }

    result = {}
    for _, row in df.iterrows():
        label = str(row[label_col]).strip()
        if label not in _LABEL_MAP:
            continue
        key, sign = _LABEL_MAP[label]
        for year_str, col in year_cols.items():
            year = int(year_str)
            if year not in result:
                result[year] = {}
            val = row[col]
            result[year][key] = int(val // 100_000_000 * sign) if val == val else 0

    return {y: v for y, v in sorted(result.items()) if 2020 <= y <= 2024}


def _save_to_db(company_name: str, data: dict):
    con = sqlite3.connect("financials.db")
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS financials (
            company TEXT,
            year    INTEGER,
            매출액   INTEGER,
            영업이익  INTEGER,
            순이익   INTEGER,
            PRIMARY KEY (company, year)
        )
    """)
    for year, d in data.items():
        cur.execute("""
            INSERT OR REPLACE INTO financials (company, year, 매출액, 영업이익, 순이익)
            VALUES (?, ?, ?, ?, ?)
        """, (company_name, year, d.get("매출액"), d.get("영업이익"), d.get("순이익")))
    con.commit()
    con.close()


def get_financials(company_name: str) -> dict:
    try:
        corp_codes = get_corp_codes(company_name)
        fs = get_financial_statements(corp_codes)
        data = _parse_dart_fs(fs)
        if data:
            _save_to_db(company_name, data)
        return data
    except Exception as e:
        print(f"[data] {company_name} 재무 데이터 로드 실패: {e}")
        return {}


if __name__ == "__main__":
    data = get_financials("에이피알")
    if not data:
        print("데이터를 찾을 수 없습니다.")
    else:
        print(data)
