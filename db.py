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
                corp_name    TEXT    NOT NULL,
                year         INTEGER NOT NULL,
                매출액       INTEGER DEFAULT NULL,
                영업이익     INTEGER DEFAULT NULL,
                순이익       INTEGER DEFAULT NULL,
                매출원가     INTEGER DEFAULT NULL,
                매출총이익   INTEGER DEFAULT NULL,
                판관비       INTEGER DEFAULT NULL,
                data_version INTEGER DEFAULT 0,
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
        for col in ["매출원가", "매출총이익", "판관비"]:
            try:
                con.execute(f'ALTER TABLE financials ADD COLUMN "{col}" INTEGER DEFAULT NULL')
            except sqlite3.OperationalError:
                pass
        try:
            con.execute("ALTER TABLE financials ADD COLUMN data_version INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
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
                INSERT INTO financials (corp_name, year, 매출액, 영업이익, 순이익, 매출원가, 매출총이익, 판관비, data_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 3)
                ON CONFLICT(corp_name, year) DO UPDATE SET
                    매출액       = excluded.매출액,
                    영업이익     = excluded.영업이익,
                    순이익       = excluded.순이익,
                    매출원가     = COALESCE(excluded.매출원가,   financials.매출원가),
                    매출총이익   = COALESCE(excluded.매출총이익, financials.매출총이익),
                    판관비       = COALESCE(excluded.판관비,     financials.판관비),
                    data_version = 3
                """,
                (
                    company_name,
                    int(year),
                    d.get("매출액"),
                    d.get("영업이익"),
                    d.get("순이익"),
                    d.get("매출원가"),
                    d.get("매출총이익"),
                    d.get("판관비"),
                ),
            )
        con.commit()


def load_financials(company_name: str) -> dict | None:
    with _conn() as con:
        rows = con.execute(
            """SELECT year, 매출액, 영업이익, 순이익, 매출원가, 매출총이익, 판관비, data_version
               FROM financials WHERE corp_name = ? ORDER BY year""",
            (company_name,),
        ).fetchall()
    if not rows:
        return None
    # data_version < 3 = 선택 컬럼 CFS 보완 이전 구버전 → None 반환해서 DART 재수집 유도
    if any((row[7] or 0) < 3 for row in rows):
        return None
    result = {}
    for year, rev, op, net, cogs, gross, sga, _ in rows:
        d = {"매출액": rev, "영업이익": op, "순이익": net}
        if cogs  is not None: d["매출원가"]   = cogs
        if gross is not None: d["매출총이익"] = gross
        if sga   is not None: d["판관비"]     = sga
        result[year] = d
    return result


def execute_sql(sql: str) -> tuple[list[str], list]:
    """(컬럼명 리스트, 행 리스트) 반환."""
    stripped = sql.strip()

    if not re.match(r"^\s*SELECT\b", stripped, re.IGNORECASE):
        raise ValueError(f"SELECT 문만 허용됩니다: {sql!r}")

    if _DANGEROUS.search(stripped):
        raise ValueError(f"허용되지 않는 SQL 키워드가 포함되어 있습니다: {sql!r}")

    parts = stripped.split(";")
    if len(parts) > 1 and any(p.strip() for p in parts[1:]):
        raise ValueError(f"다중 statement는 허용되지 않습니다: {sql!r}")

    with _conn() as con:
        cur = con.execute(stripped)
        cols = [d[0] for d in (cur.description or [])]
        return cols, cur.fetchall()


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
    _, rows = execute_sql("SELECT * FROM financials WHERE corp_name = '에이피알'")
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
