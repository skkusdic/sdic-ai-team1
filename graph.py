from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from data import get_financials
from claude_client import ask


class State(TypedDict):
    company: str
    data: dict
    summary: str
    result: str
    analysis: str
    next: str


# supervisor
def supervisor_node(state: State) -> State:
    if not state.get("data"):
        print("[supervisor] → data_agent 호출")
        return {"next": "data_agent"}
    if not state.get("analysis"):
        print("[supervisor] → analysis_agent 호출")
        return {"next": "analysis_agent"}
    print("[supervisor] → 완료")
    return {"next": END}


def route(state: State) -> Literal["data_agent", "analysis_agent", "__end__"]:
    return state["next"]


# data_agent
def data_agent(state: State) -> State:
    company = state.get("company") or "에이피알"
    data = get_financials(company)
    summary_lines = [
        f"{year}년: 매출 {d['매출액']:,}백만원, 영업이익 {d['영업이익']:,}백만원, 순이익 {d['순이익']:,}백만원"
        for year, d in sorted(data.items())
    ]
    print(f"[data_agent] {company} 재무 데이터 로드 완료")
    return {"data": data, "summary": "\n".join(summary_lines), "next": ""}


# analysis_agent
def analysis_agent(state: State) -> State:
    company = state.get("company") or "에이피알"
    prompt = (
        f"{company} 재무 데이터:\n{state['summary']}\n\n"
        "위 데이터를 바탕으로 재무 상태를 한국어로 3~5문장으로 분석해줘. "
        "매출 추세, 수익성(영업이익률·순이익률), "
        "전년 대비 주요 변화를 포함해줘."
    )
    analysis = ask(prompt)
    print(f"\n=== Claude 재무 분석: {company} ===")
    print(analysis)
    return {"result": analysis, "analysis": analysis, "next": ""}


# pipeline
graph = StateGraph(State)
graph.add_node("supervisor", supervisor_node)
graph.add_node("data_agent", data_agent)
graph.add_node("analysis_agent", analysis_agent)

graph.set_entry_point("supervisor")
graph.add_conditional_edges("supervisor", route, {
    "data_agent": "data_agent",
    "analysis_agent": "analysis_agent",
    END: END,
})
graph.add_edge("data_agent", "supervisor")
graph.add_edge("analysis_agent", "supervisor")

pipeline = graph.compile()

if __name__ == "__main__":
    final_state = pipeline.invoke({
        "company": "에이피알",
        "data": {},
        "summary": "",
        "result": "",
        "analysis": "",
        "next": "",
    })
    print(final_state["analysis"])
