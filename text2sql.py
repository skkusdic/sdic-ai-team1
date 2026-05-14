import re

import pandas as pd
from claude_client import ask
from db import execute_sql

_SCHEMA = """
테이블: financials
컬럼:
  corp_name TEXT    -- 기업명
  year      INTEGER -- 연도
  매출액    INTEGER -- 단위: 억원
  영업이익  INTEGER -- 단위: 억원
  순이익    INTEGER -- 단위: 억원
기본 키: (corp_name, year)
"""

_EXAMPLES = """
예시1) 질문: 에이피알의 연도별 매출액은?
SQL: SELECT year, "매출액" FROM financials WHERE corp_name = '에이피알' ORDER BY year

예시2) 질문: 에이피알의 영업이익 합계는?
SQL: SELECT SUM("영업이익") FROM financials WHERE corp_name = '에이피알'

예시3) 질문: 에이피알의 최대 순이익과 최소 순이익은?
SQL: SELECT MAX("순이익"), MIN("순이익") FROM financials WHERE corp_name = '에이피알'
"""


def _generate_sql(query: str, company: str) -> str:
    """한국어 질문 → SELECT SQL 변환. 코드펜스·세미콜론 자동 제거."""
    prompt = (
        f"아래 SQLite 스키마와 예시를 참고해 질문을 SELECT 문으로 변환하세요.\n\n"
        f"[스키마]\n{_SCHEMA}\n"
        f"[예시]\n{_EXAMPLES}\n"
        f"[힌트] 현재 분석 기업: '{company}' — WHERE corp_name = '{company}' 조건 필수\n\n"
        f"[질문] {query}\n\n"
        "규칙: SELECT 문만 출력하세요. 설명·주석·세미콜론 불필요."
    )
    raw = ask(prompt, max_tokens=256).strip()
    # 코드펜스 제거
    match = re.search(r"```(?:sql)?\n?(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    sql = match.group(1).strip() if match else raw
    # 세미콜론 제거
    return sql.rstrip(";").strip()


def run_text2sql(query: str, company: str) -> tuple[str, pd.DataFrame | None, str | None]:
    """
    (sql, dataframe, error) 반환.
    - SQL 변환 실패: sql="", dataframe=None, error=오류 메시지
    - SQL 실행 실패: sql=생성된 SQL, dataframe=None, error=오류 메시지
    - 성공: sql=생성된 SQL, dataframe=결과, error=None
    """
    # 1단계: SQL 변환
    try:
        sql = _generate_sql(query, company)
    except Exception as e:
        return "", None, f"SQL 변환 실패: {e}"

    # 2단계: db.execute_sql로 안전 실행 (INSERT/DROP → ValueError)
    try:
        rows = execute_sql(sql)
        df = pd.DataFrame(rows)
        return sql, df, None
    except ValueError as e:
        return sql, None, f"SQL 실행 거부: {e}"
    except Exception as e:
        return sql, None, f"SQL 실행 실패: {e}"


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    from db import init_db, save_financials
    init_db()

    # 테스트용 데이터 삽입 (카카오 — 이미 DB에 있을 수 있음)
    sample = {
        "2020": {"매출액": 41568, "영업이익": 1424,  "순이익": 1058},
        "2021": {"매출액": 61377, "영업이익": 5603,  "순이익": 16404},
        "2022": {"매출액": 71071, "영업이익": 5825,  "순이익": -7360},
        "2023": {"매출액": 75532, "영업이익": 6685,  "순이익": -18167},
        "2024": {"매출액": 77736, "영업이익": 5749,  "순이익": 10798},
    }
    save_financials("카카오", sample)

    tests = [
        ("카카오의 5년 평균 매출액은?",          "카카오"),  # AVG
        ("카카오의 영업이익 합계는?",              "카카오"),  # SUM
        ("카카오의 최대 순이익과 최소 순이익은?",  "카카오"),  # MAX/MIN
    ]

    all_pass = True
    for question, corp in tests:
        print(f"\n{'─'*55}")
        print(f"질문: {question}")
        sql, df, error = run_text2sql(question, corp)
        print(f"SQL : {sql}")
        if error:
            print(f"오류: {error}")
            all_pass = False
        else:
            print(f"결과: {df.values.tolist()}")

    # INSERT/DROP 방어 테스트
    print(f"\n{'─'*55}")
    print("방어 테스트: INSERT 직접 전달")
    try:
        execute_sql("INSERT INTO financials VALUES ('x', 2020, 0, 0, 0)")
        print("실패: ValueError가 발생했어야 함")
        all_pass = False
    except ValueError as e:
        print(f"통과: {e}")

    print(f"\n{'─'*55}")
    print("방어 테스트: DROP 직접 전달")
    try:
        execute_sql("DROP TABLE financials")
        print("실패: ValueError가 발생했어야 함")
        all_pass = False
    except ValueError as e:
        print(f"통과: {e}")

    print(f"\n{'═'*55}")
    print("최종 결과:", "✓ 전체 통과" if all_pass else "✗ 일부 실패")
