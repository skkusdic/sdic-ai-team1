import re

import pandas as pd
from claude_client import ask
from db import execute_sql

_SCHEMA = """
테이블: financials
컬럼:
  corp_name  TEXT    -- 기업명
  year       INTEGER -- 연도 (2021~2025)
  매출액     INTEGER -- 단위: 백만원 (NULL 없음)
  영업이익   INTEGER -- 단위: 백만원 (음수 = 영업손실)
  순이익     INTEGER -- 단위: 백만원 (음수 = 순손실)
  매출원가   INTEGER -- 단위: 백만원 (NULL 가능 — 서비스·금융업 등)
  매출총이익 INTEGER -- 단위: 백만원 (NULL 가능 — 매출액 - 매출원가)
  판관비     INTEGER -- 단위: 백만원 (NULL 가능 — 판매비와관리비)
기본 키: (corp_name, year)

[직접 계산 가능한 지표 — 컬럼이 아니므로 SELECT에서 수식으로 계산]
  영업이익률(%)    : ROUND(영업이익 * 100.0 / 매출액, 2)      -- 매출액 > 0 조건 필수
  순이익률(%)      : ROUND(순이익   * 100.0 / 매출액, 2)      -- 매출액 > 0 조건 필수
  매출총이익률(%)  : ROUND(매출총이익 * 100.0 / 매출액, 2)    -- 매출총이익 IS NOT NULL AND 매출액 > 0
  매출원가율(%)    : ROUND(매출원가   * 100.0 / 매출액, 2)    -- 매출원가 IS NOT NULL AND 매출액 > 0
  판관비율(%)      : ROUND(판관비     * 100.0 / 매출액, 2)    -- 판관비 IS NOT NULL AND 매출액 > 0
  YoY 매출성장률(%): self JOIN으로 전년 대비 성장률 계산
"""

_EXAMPLES = """
[기본 조회]
Q: 에이피알의 연도별 매출액은?
SQL: SELECT year, 매출액 FROM financials WHERE corp_name = '에이피알' ORDER BY year

Q: 에이피알의 최근 5년 실적은?
SQL: SELECT year, 매출액, 영업이익, 순이익 FROM financials WHERE corp_name = '에이피알' ORDER BY year DESC LIMIT 5

Q: 에이피알 2023년 매출액은?
SQL: SELECT 매출액 FROM financials WHERE corp_name = '에이피알' AND year = 2023

[집계·통계]
Q: 에이피알의 5년 평균 매출액은?
SQL: SELECT ROUND(AVG(매출액)) AS 평균매출액 FROM financials WHERE corp_name = '에이피알'

Q: 에이피알의 영업이익 합계는?
SQL: SELECT SUM(영업이익) AS 영업이익합계 FROM financials WHERE corp_name = '에이피알'

Q: 에이피알의 최대·최소 순이익 연도는?
SQL: SELECT year, 순이익 FROM financials WHERE corp_name = '에이피알' ORDER BY 순이익 DESC

Q: 에이피알의 평균 판관비는?
SQL: SELECT ROUND(AVG(판관비)) AS 평균판관비 FROM financials WHERE corp_name = '에이피알' AND 판관비 IS NOT NULL

[수익성 지표]
Q: 에이피알의 연도별 영업이익률은?
SQL: SELECT year, ROUND(영업이익 * 100.0 / 매출액, 2) AS 영업이익률 FROM financials WHERE corp_name = '에이피알' AND 매출액 > 0 ORDER BY year

Q: 에이피알의 평균 영업이익률은?
SQL: SELECT ROUND(AVG(영업이익 * 100.0 / 매출액), 2) AS 평균영업이익률 FROM financials WHERE corp_name = '에이피알' AND 매출액 > 0

Q: 에이피알의 순이익률 추이는?
SQL: SELECT year, ROUND(순이익 * 100.0 / 매출액, 2) AS 순이익률 FROM financials WHERE corp_name = '에이피알' AND 매출액 > 0 ORDER BY year

Q: 에이피알의 매출원가율은?
SQL: SELECT year, ROUND(매출원가 * 100.0 / 매출액, 2) AS 매출원가율 FROM financials WHERE corp_name = '에이피알' AND 매출원가 IS NOT NULL AND 매출액 > 0 ORDER BY year

Q: 에이피알의 매출총이익률은?
SQL: SELECT year, ROUND(매출총이익 * 100.0 / 매출액, 2) AS 매출총이익률 FROM financials WHERE corp_name = '에이피알' AND 매출총이익 IS NOT NULL AND 매출액 > 0 ORDER BY year

Q: 에이피알의 판관비율은?
SQL: SELECT year, ROUND(판관비 * 100.0 / 매출액, 2) AS 판관비율 FROM financials WHERE corp_name = '에이피알' AND 판관비 IS NOT NULL AND 매출액 > 0 ORDER BY year

[성장률·추세]
Q: 에이피알의 연도별 매출 성장률은?
SQL: SELECT a.year, ROUND((a.매출액 - b.매출액) * 100.0 / b.매출액, 2) AS YoY매출성장률 FROM financials a JOIN financials b ON a.corp_name = b.corp_name AND a.year = b.year + 1 WHERE a.corp_name = '에이피알' ORDER BY a.year

Q: 에이피알의 영업이익 성장률은?
SQL: SELECT a.year, ROUND((a.영업이익 - b.영업이익) * 100.0 / ABS(b.영업이익), 2) AS YoY영업이익성장률 FROM financials a JOIN financials b ON a.corp_name = b.corp_name AND a.year = b.year + 1 WHERE a.corp_name = '에이피알' AND b.영업이익 != 0 ORDER BY a.year

Q: 에이피알의 매출이 가장 많이 늘어난 해는?
SQL: SELECT a.year, ROUND((a.매출액 - b.매출액) * 100.0 / b.매출액, 2) AS 성장률 FROM financials a JOIN financials b ON a.corp_name = b.corp_name AND a.year = b.year + 1 WHERE a.corp_name = '에이피알' ORDER BY 성장률 DESC LIMIT 1

[복합 분석]
Q: 에이피알의 연도별 매출액과 영업이익률을 함께 보여줘
SQL: SELECT year, 매출액, 영업이익, ROUND(영업이익 * 100.0 / 매출액, 2) AS 영업이익률 FROM financials WHERE corp_name = '에이피알' AND 매출액 > 0 ORDER BY year

Q: 영업이익이 가장 높은 연도와 낮은 연도는?
SQL: SELECT year, 영업이익, CASE WHEN 영업이익 = (SELECT MAX(영업이익) FROM financials WHERE corp_name = '에이피알') THEN '최고' ELSE '최저' END AS 구분 FROM financials WHERE corp_name = '에이피알' AND (영업이익 = (SELECT MAX(영업이익) FROM financials WHERE corp_name = '에이피알') OR 영업이익 = (SELECT MIN(영업이익) FROM financials WHERE corp_name = '에이피알'))

Q: 에이피알의 흑자/적자 연도는?
SQL: SELECT year, 순이익, CASE WHEN 순이익 >= 0 THEN '흑자' ELSE '적자' END AS 구분 FROM financials WHERE corp_name = '에이피알' ORDER BY year

Q: 에이피알의 매출 대비 비용 구조는?
SQL: SELECT year, 매출액, 매출원가, 판관비, ROUND(매출원가 * 100.0 / 매출액, 2) AS 매출원가율, ROUND(판관비 * 100.0 / 매출액, 2) AS 판관비율 FROM financials WHERE corp_name = '에이피알' AND 매출원가 IS NOT NULL AND 판관비 IS NOT NULL ORDER BY year
"""


def _generate_sql(query: str, company: str) -> str:
    """한국어 질문 → SELECT SQL 변환. 답 불가 시 'NO_DATA:' 접두사 반환."""
    prompt = (
        f"아래 SQLite 스키마와 예시를 참고해 질문을 SELECT 문으로 변환하세요.\n\n"
        f"[스키마]\n{_SCHEMA}\n"
        f"[예시]\n{_EXAMPLES}\n"
        f"[분석 기업] '{company}' — 반드시 WHERE corp_name = '{company}' 포함\n\n"
        f"[질문] {query}\n\n"
        "규칙:\n"
        "1. SELECT 문만 출력. 설명·주석·세미콜론·코드펜스 불필요.\n"
        "2. 스키마 컬럼으로 답할 수 없는 질문(예: 부채비율, PER 등)은 정확히 'NO_DATA: <이유 한 줄>' 형식으로만 답하세요.\n"
        "3. NULL 가능 컬럼(매출원가·매출총이익·판관비)은 반드시 IS NOT NULL 조건 추가.\n"
        "4. 나눗셈 시 매출액 > 0 조건으로 0 나누기 방지.\n"
        "5. AS 별칭을 붙여 컬럼명이 의미 있게 출력되도록 하세요."
    )
    raw = ask(prompt, max_tokens=350).strip()
    match = re.search(r"```(?:sql)?\n?(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    sql = match.group(1).strip() if match else raw
    return sql.rstrip(";").strip()


def _analysis_fallback(query: str, company: str) -> str | None:
    """DB 전체 데이터를 컨텍스트로 Claude에게 분석형 질문 답변 생성. 실패 시 None."""
    safe = company.replace("'", "''")
    fallback_sql = (
        f"SELECT year, 매출액, 영업이익, 순이익, 매출원가, 매출총이익, 판관비 "
        f"FROM financials WHERE corp_name = '{safe}' ORDER BY year"
    )
    try:
        cols, rows = execute_sql(fallback_sql)
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=cols)
        # 영업이익률 파생 컬럼 추가
        df["영업이익률(%)"] = df.apply(
            lambda r: round(float(r["영업이익"]) * 100.0 / float(r["매출액"]), 2)
            if r["매출액"] else None,
            axis=1,
        )
        context = df.to_string(index=False)
        return ask(
            f"{company}의 연도별 재무 데이터 (단위: 백만원):\n\n{context}\n\n"
            f"위 데이터를 근거로 다음 질문에 답하세요:\n{query}\n\n"
            "구체적 연도·수치를 인용하며 한국어로 간결하게 답하세요.",
            max_tokens=500,
        ).strip()
    except Exception:
        return None


def run_text2sql(query: str, company: str) -> tuple[str, pd.DataFrame | None, str | None, str | None]:
    """
    (sql, dataframe, error, analysis) 반환.
    - 스키마 범위 초과: ("", None, 안내메시지, None)
    - 분석형 질문: ("", None, None, Claude분석텍스트)
    - SQL 실행 실패: (sql, None, 오류메시지, None)
    - 성공: (sql, DataFrame, None, None)
    """
    # 쿼리 전 최신(OFS+새컬럼) 데이터 보장 — 구버전 캐시면 DART 재수집
    try:
        from data import get_financials as _ensure
        _ensure(company)
    except Exception:
        pass

    try:
        sql = _generate_sql(query, company)
    except Exception as e:
        return "", None, f"SQL 변환 실패: {e}", None

    # 스키마 한계로 답 불가 (부채비율·PER 등 DB에 없는 지표)
    if sql.upper().startswith("NO_DATA:"):
        return "", None, sql[8:].strip(), None

    # SQL이 아닌 자연어 → 분석형 질문으로 판단, DB 데이터 기반 Claude 답변
    if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
        analysis = _analysis_fallback(query, company)
        if analysis:
            return "", None, None, analysis
        return "", None, "현재 DB에는 매출액·영업이익·순이익·매출원가·매출총이익·판관비 데이터만 있습니다. 부채비율·PER·주가 등은 별도 탭을 이용해 주세요.", None

    try:
        cols, rows = execute_sql(sql)
        df = pd.DataFrame(rows, columns=cols if cols else None)
        return sql, df, None, None
    except ValueError as e:
        return sql, None, f"SQL 실행 거부: {e}", None
    except Exception as e:
        return sql, None, f"SQL 실행 실패: {e}", None


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    from db import init_db, save_financials
    init_db()

    sample = {
        "2020": {"매출액": 41568,  "영업이익": 1424,  "순이익": 1058,  "매출원가": 28000, "매출총이익": 13568, "판관비": 12144},
        "2021": {"매출액": 61377,  "영업이익": 5603,  "순이익": 16404, "매출원가": 41000, "매출총이익": 20377, "판관비": 14774},
        "2022": {"매출액": 71071,  "영업이익": 5825,  "순이익": -7360, "매출원가": 47000, "매출총이익": 24071, "판관비": 18246},
        "2023": {"매출액": 75532,  "영업이익": 6685,  "순이익": -18167,"매출원가": 49000, "매출총이익": 26532, "판관비": 19847},
        "2024": {"매출액": 77736,  "영업이익": 5749,  "순이익": 10798, "매출원가": 51000, "매출총이익": 26736, "판관비": 20987},
    }
    save_financials("카카오", sample)

    tests = [
        ("카카오의 5년 평균 매출액은?",          "카카오"),
        ("카카오의 연도별 영업이익률은?",          "카카오"),
        ("카카오의 매출 성장률 추이는?",           "카카오"),
        ("카카오의 매출원가율은?",                 "카카오"),
        ("카카오의 흑자/적자 연도는?",             "카카오"),
        ("카카오의 부채비율은?",                   "카카오"),  # NO_DATA 테스트
    ]

    for question, corp in tests:
        print(f"\n{'─'*60}")
        print(f"질문: {question}")
        sql, df, error, analysis = run_text2sql(question, corp)
        if analysis:
            print(f"분석: {analysis}")
        elif error:
            print(f"안내: {error}")
        else:
            print(f"SQL : {sql}")
            print(f"결과:\n{df.to_string(index=False)}")

    print(f"\n{'─'*60}")
    print("방어 테스트: INSERT 직접 전달")
    try:
        execute_sql("INSERT INTO financials VALUES ('x', 2020, 0, 0, 0, 0, 0, 0)")
        print("실패: ValueError가 발생했어야 함")
    except ValueError as e:
        print(f"통과: {e}")

    print(f"\n{'═'*60}")
    print("테스트 완료")
