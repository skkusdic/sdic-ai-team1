import os
from dotenv import load_dotenv

load_dotenv()
DART_API_KEY = os.getenv("DART_API_KEY")


def get_corp_code(company_name: str) -> str:
    # TODO Week 2: DART-FSS로 기업 코드 조회
    pass


def get_financial_statements(corp_code: str) -> list:
    # TODO Week 2: DART-FSS로 재무제표 조회
    pass
