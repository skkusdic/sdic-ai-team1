from typing import TypedDict
from langgraph.graph import StateGraph, END
from data import get_financials
from claude_client import ask


class State(TypedDict):
    company: str
    data: dict
    summary: str
    result: str
    analysis: str


def load_data(state: State) -> State:
    state["data"] = get_financials(state["company"])
    return state


def process_data(state: State) -> State:
    data = state["data"]
    summary_lines = [
        f"{year}년: 매출 {d['매출액']:,}백만원, 영업이익 {d['영업이익']:,}백만원, 순이익 {d['순이익']:,}백만원"
        for year, d in sorted(data.items())
    ]
    state["summary"] = "\n".join(summary_lines)
    state["result"] = "데이터 처리 완료"
    return state


def analyze(state: State) -> State:
    prompt = (
        f"{state['company']} 재무 데이터:\n{state['summary']}\n\n"
        "위 데이터를 바탕으로 재무 상태를 한국어로 3~5문장으로 분석해줘. "
        "매출 추세, 수익성, 영업이익률을 포함해줘."
    )
    state["analysis"] = ask(prompt)
    state["result"] = "분석 완료"
    return state


graph = StateGraph(State)
graph.add_node("load_data", load_data)
graph.add_node("process_data", process_data)
graph.add_node("analyze", analyze)
graph.set_entry_point("load_data")
graph.add_edge("load_data", "process_data")
graph.add_edge("process_data", "analyze")
graph.add_edge("analyze", END)

pipeline = graph.compile()

if __name__ == "__main__":
    final_state = pipeline.invoke({"company": "에이피알", "data": {}, "summary": "", "result": "", "analysis": ""})
    print(final_state["analysis"])
