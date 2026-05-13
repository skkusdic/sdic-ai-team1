import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data import get_financials
from db import init_db, load_financials, save_financials

init_db()


def run_data_agent(state: dict) -> dict:
    company = state.get("company", "")

    cached = load_financials(company)
    if cached:
        print(f"[data_agent] 캐시 히트 (DB): {company}")
        return {**state, "financials": cached, "data_source": "cache", "next_agent": "analysis_agent"}

    print(f"[data_agent] 캐시 미스 → DART 호출: {company}")
    financials = get_financials(company)
    if financials:
        save_financials(company, financials)

    return {**state, "financials": financials, "data_source": "dart", "next_agent": "analysis_agent"}


if __name__ == "__main__":
    import pprint
    mock_state = {"request": "에이피알 재무", "company": "에이피알"}
    result = run_data_agent(mock_state)
    pprint.pprint(result)
