import re
import sqlite3

import pandas as pd
from anthropic import Anthropic

from data import DB_PATH

_SCHEMA = """
테이블: financials
컬럼:
  company  TEXT    -- 기업명
  year     INTEGER -- 연도
  매출액   INTEGER -- 단위: 억원
  영업이익 INTEGER -- 단위: 억원
  순이익   INTEGER -- 단위: 억원
기본 키: (company, year)
"""


def _generate_sql(query: str, company: str) -> str:
    client = Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": (
                f"아래 SQLite 스키마를 참고해 질문을 SELECT 문으로 변환하세요.\n\n"
                f"스키마:\n{_SCHEMA}\n"
                f"현재 분석 기업: {company}\n"
                f"질문: {query}\n\n"
                "규칙:\n"
                "1. SELECT 문만 출력하세요 (설명 없이).\n"
                "2. WHERE 절에 반드시 company = '{company}' 조건을 포함하세요.\n"
                "3. 컬럼명에 한글이 포함된 경우 큰따옴표로 감싸세요."
            ),
        }],
    )
    raw = resp.content[0].text.strip()
    match = re.search(r"```(?:sql)?\n?(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else raw


def run_text2sql(query: str, company: str) -> tuple[str, pd.DataFrame | None, str | None]:
    """(sql, dataframe, error) 반환. 오류 시 dataframe=None, error=오류 메시지."""
    sql = _generate_sql(query, company)
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query(sql, conn)
        return sql, df, None
    except Exception as e:
        return sql, None, str(e)
