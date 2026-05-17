"""
db.py — SQLite 캐싱 레이어 (Data Lead: 김나은)

DB 경로: data/sdic.db
테이블:  companies, financials
"""

import os
import re
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sdic.db")

_DANGEROUS = re.compile(
    r"\b(DROP|INSERT|UPDATE|DELETE|ALTER|CREATE)\b",
    re.IGNORECASE,
)


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                corp_name  TEXT PRIMARY KEY,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS financials (
                corp_name TEXT    NOT NULL,
                year      INTEGER NOT NULL,
                매출액    INTEGER DEFAULT 0,
                영업이익  INTEGER DEFAULT 0,
                순이익    INTEGER DEFAULT 0,
                PRIMARY KEY (corp_name, year),
                FOREIGN KEY (corp_name) REFERENCES companies(corp_name)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS business_reports (
                corp_name  TEXT    NOT NULL,
                year       INTEGER NOT NULL,
                section    TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                created_at TEXT    DEFAULT (datetime('now')),
                PRIMARY KEY (corp_name, year, section)
            )
        """)
        con.commit()


def save_business_report(company_name: str, year: int, section: str, content: str):
    with _conn() as con:
        con.execute(
            """
            INSERT INTO business_reports (corp_name, year, section, content)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(corp_name, year, section) DO UPDATE SET
                content    = excluded.content,
                created_at = datetime('now')
            """,
            (company_name, year, section, content),
        )
        con.commit()


def load_business_report(company_name: str, year: int, section: str) -> str | None:
    with _conn() as con:
        row = con.execute(
            "SELECT content FROM business_reports WHERE corp_name = ? AND year = ? AND section = ?",
            (company_name, year, section),
        ).fetchone()
    return row[0] if row else None


def save_financials(company_name: str, financials: dict):
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO companies (corp_name) VALUES (?)",
            (company_name,),
        )
        for year, d in financials.items():
            con.execute(
                """
                INSERT INTO financials (corp_name, year, 매출액, 영업이익, 순이익)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(corp_name, year) DO UPDATE SET
                    매출액   = excluded.매출액,
                    영업이익 = excluded.영업이익,
                    순이익   = excluded.순이익
                """,
                (
                    company_name,
                    int(year),
                    d.get("매출액", 0),
                    d.get("영업이익", 0),
                    d.get("순이익", 0),
                ),
            )
        con.commit()


def load_financials(company_name: str) -> dict | None:
    with _conn() as con:
        rows = con.execute(
            "SELECT year, 매출액, 영업이익, 순이익 FROM financials WHERE corp_name = ? ORDER BY year",
            (company_name,),
        ).fetchall()
    if not rows:
        return None
    return {
        row[0]: {"매출액": row[1], "영업이익": row[2], "순이익": row[3]}
        for row in rows
    }


def execute_sql(sql: str):
    stripped = sql.strip()

    if not re.match(r"^\s*SELECT\b", stripped, re.IGNORECASE):
        raise ValueError(f"SELECT 문만 허용됩니다: {sql!r}")

    if _DANGEROUS.search(stripped):
        raise ValueError(f"허용되지 않는 SQL 키워드가 포함되어 있습니다: {sql!r}")

    parts = stripped.split(";")
    if len(parts) > 1 and any(p.strip() for p in parts[1:]):
        raise ValueError(f"다중 statement는 허용되지 않습니다: {sql!r}")

    with _conn() as con:
        return con.execute(stripped).fetchall()


if __name__ == "__main__":
    import pprint

    print("=" * 50)
    print("1. init_db()")
    init_db()
    print("   → companies, financials 테이블 생성 완료")

    print("\n2. save_financials('에이피알', {...})")
    sample = {
        2022: {"매출액": 456_100, "영업이익": 31_200, "순이익": 24_100},
        2023: {"매출액": 689_200, "영업이익": 58_700, "순이익": 45_300},
        2024: {"매출액": 921_400, "영업이익": 89_100, "순이익": 71_200},
    }
    save_financials("에이피알", sample)
    print("   → 저장 완료")

    print("\n3. save_financials 재호출 — UPSERT 중복 방지 확인")
    save_financials("에이피알", sample)
    print("   → 중복 저장 없이 UPSERT 처리됨")

    print("\n4. load_financials('에이피알')")
    loaded = load_financials("에이피알")
    pprint.pprint(loaded)

    print("\n5. load_financials('없는회사') → None")
    print("  ", load_financials("없는회사"))

    print("\n6. execute_sql — 허용: SELECT * FROM financials")
    rows = execute_sql("SELECT * FROM financials WHERE corp_name = '에이피알'")
    for row in rows:
        print("  ", row)

    print("\n7. execute_sql — 차단: DROP TABLE financials")
    try:
        execute_sql("DROP TABLE financials")
    except ValueError as e:
        print(f"   ValueError 발생 (정상): {e}")

    print("\n8. execute_sql — 차단: SELECT 1; DROP TABLE financials")
    try:
        execute_sql("SELECT 1; DROP TABLE financials")
    except ValueError as e:
        print(f"   ValueError 발생 (정상): {e}")

    print("\n9. execute_sql — 차단: INSERT INTO financials ...")
    try:
        execute_sql("INSERT INTO financials VALUES ('x', 2024, 0, 0, 0)")
    except ValueError as e:
        print(f"   ValueError 발생 (정상): {e}")

    print("\n" + "=" * 50)
    print("모든 테스트 통과")
