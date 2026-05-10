from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from data import get_financials
from claude_client import ask
from agents.analysis_agent import analyze
from report import generate_report


class State(TypedDict):
    request: str
    company: str
    next_agent: str
    financials: dict
    analysis: str
    result: str
    pdf_path: str


def supervisor_node(state: State) -> State:
    if not state.get("financials"):
        print("[supervisor] financials 없음 → data_agent 호출")
        return {"next_agent": "data_agent"}

    prompt = (
        f"사용자 요청: {state.get('request', '')}\n"
        f"현재 상태: financials=있음, analysis={'있음' if state.get('analysis') else '없음'}\n\n"
        "다음 중 다음에 호출할 에이전트를 정확히 한 단어로만 답해줘: "
        "data_agent / analysis_agent / report_agent"
    )
    decision = ask(prompt).strip().lower()

    if "data" in decision:
        next_agent = "data_agent"
    elif "report" in decision:
        next_agent = "report_agent"
    else:
        next_agent = "analysis_agent"

    print(f"[supervisor] Claude 판단 → {next_agent}")
    return {"next_agent": next_agent}


def route_supervisor(state: State) -> Literal["data_agent", "analysis_agent", "report_agent", "__end__"]:
    return state.get("next_agent", "__end__")


def data_agent_node(state: State) -> State:
    company = state.get("company", "")
    print(f"[data_agent] {company} 데이터 로드 중...")
    financials = get_financials(company)
    if financials:
        print(f"[data_agent] 로드 완료: {sorted(financials.keys())}년도")
    else:
        print("[data_agent] 데이터 없음 → END")
    return {"financials": financials}


def no_data_node(state: State) -> State:
    print("[no_data] 데이터를 찾을 수 없습니다.")
    return {"result": "데이터를 찾을 수 없습니다"}


def route_data_agent(state: State) -> Literal["analysis_agent", "no_data"]:
    if state.get("financials"):
        return "analysis_agent"
    return "no_data"


def analysis_agent_node(state: State) -> State:
    company = state.get("company", "")
    print(f"[analysis_agent] {company} 분석 중...")
    analysis = analyze(state["financials"])
    print("[analysis_agent] 분석 완료")
    return {"analysis": analysis, "result": analysis}


def report_agent_node(state: State) -> State:
    company = state.get("company", "")
    print(f"[report_agent] {company} PDF 생성 중...")
    pdf_path = generate_report(company, state.get("financials", {}), state.get("analysis", ""))
    print(f"[report_agent] PDF 생성 완료: {pdf_path}")
    return {"pdf_path": pdf_path}


graph = StateGraph(State)
graph.add_node("supervisor", supervisor_node)
graph.add_node("data_agent", data_agent_node)
graph.add_node("no_data", no_data_node)
graph.add_node("analysis_agent", analysis_agent_node)
graph.add_node("report_agent", report_agent_node)

graph.set_entry_point("supervisor")
graph.add_conditional_edges("supervisor", route_supervisor, {
    "data_agent": "data_agent",
    "analysis_agent": "analysis_agent",
    "report_agent": "report_agent",
    "__end__": END,
})
graph.add_conditional_edges("data_agent", route_data_agent, {
    "analysis_agent": "analysis_agent",
    "no_data": "no_data",
})
graph.add_edge("no_data", END)
graph.add_edge("analysis_agent", "report_agent")
graph.add_edge("report_agent", END)

pipeline = graph.compile()

if __name__ == "__main__":
    import pprint
    final_state = pipeline.invoke({
        "request": "에이피알 재무 분석해줘",
        "company": "에이피알",
        "next_agent": "",
        "financials": {},
        "analysis": "",
        "result": "",
        "pdf_path": "",
    })
    pprint.pprint({k: v for k, v in final_state.items() if k != "financials"})
