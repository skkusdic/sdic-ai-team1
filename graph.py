from typing import TypedDict
from langgraph.graph import StateGraph, END
from data import get_financials


class State(TypedDict):
    data: dict
    result: str


def load_data(state: State) -> State:
    state["data"] = get_financials("에이피알")
    return state


def process_data(state: State) -> State:
    data = state["data"]
    latest_year = max(data.keys())
    d = data[latest_year]
    msg = (
        f"분석 준비 완료: 매출액 {d['매출액']:,}원, "
        f"영업이익 {d['영업이익']:,}원"
    )
    print(msg)
    state["result"] = msg
    return state


graph = StateGraph(State)
graph.add_node("load_data", load_data)
graph.add_node("process_data", process_data)
graph.set_entry_point("load_data")
graph.add_edge("load_data", "process_data")
graph.add_edge("process_data", END)

app = graph.compile()

if __name__ == "__main__":
    final_state = app.invoke({"data": {}, "result": ""})
