from langgraph.graph import StateGraph, END
from typing import TypedDict


class AnalysisState(TypedDict):
    company: str
    corp_code: str
    financials: list
    report: str


def build_graph():
    # TODO Week 2-3: LangGraph 파이프라인 구성
    # data_agent -> analysis_agent -> report_agent
    graph = StateGraph(AnalysisState)
    return graph.compile()
