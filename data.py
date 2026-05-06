import os
import sqlite3
import dart_fss as dart
from dotenv import load_dotenv

load_dotenv()
dart.set_api_key(os.getenv("DART_API_KEY"))
dart.enable_spinner(False)


def get_corp_code(company_name: str) -> str:
    corp_list = dart.get_corp_list()
    results = corp_list.find_by_corp_name(company_name, exactly=True)
    if not results:
        results = corp_list.find_by_corp_name(company_name, exactly=False)
    if not results:
        raise ValueError(f"기업을 찾을 수 없습니다: {company_name}")
    return results[0].corp_code


def get_financial_statements(corp_code: str):
    return dart.extract(
        corp_code=corp_code,
        bgn_de="20210101",
        report_tp="annual",
        separate=True,
    )


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

    target_labels = {"매출액", "영업이익", "당기순이익"}
    label_map = {"당기순이익": "순이익"}

    result = {}
    for _, row in df.iterrows():
        label = str(row[label_col]).strip()
        if label not in target_labels:
            continue
        key = label_map.get(label, label)
        for year_str, col in year_cols.items():
            year = int(year_str)
            if year not in result:
                result[year] = {}
            val = row[col]
            result[year][key] = int(val // 1_000_000) if val == val else 0

    return {y: v for y, v in sorted(result.items()) if 2021 <= y <= 2025}


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
        corp_code = get_corp_code(company_name)
        fs = get_financial_statements(corp_code)
        data = _parse_dart_fs(fs)
        if data:
            _save_to_db(company_name, data)
        return data
    except Exception:
        return {}


if __name__ == "__main__":
    data = get_financials("에이피알")
    if not data:
        print("데이터를 찾을 수 없습니다.")
    else:
        print(data)
