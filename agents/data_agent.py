import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data import get_financials

_cache: dict = {}


def run_data_agent(state: dict) -> dict:
    company = state.get("company", "")
    if company in _cache:
        print(f"[data_agent] 캐시 히트: {company}")
        financials = _cache[company]
    else:
        financials = get_financials(company)
        if financials:
            _cache[company] = financials
    return {**state, "financials": financials, "next_agent": "analysis_agent"}


if __name__ == "__main__":
    import pprint
    mock_state = {"request": "에이피알 재무", "company": "에이피알"}
    result = run_data_agent(mock_state)
    pprint.pprint(result)
