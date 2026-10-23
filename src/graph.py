"""P1 LangGraph topology; injectable agents keep workstreams independent."""
from copy import deepcopy

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from src.human import apply_resolution
from src.orchestration import orchestrate
from src.state import AGENT_FIELDS, GraphState, validate_update


def build_graph(checkpointer, agents):
    missing = set(AGENT_FIELDS) - set(agents)
    if missing:
        raise ValueError(f"Missing agent adapters: {sorted(missing)}")
    builder = StateGraph(GraphState)
    builder.add_node("orchestrator", orchestrate)

    def wrapped(name):
        def node(state):
            # Copies enforce read-only shared state, even if an adapter mutates its input.
            update = validate_update(name, agents[name](deepcopy(state)))
            return update | {"last_agent": name}
        return node

    for name in ("intake", "rules", "computation", "review"):
        builder.add_node(name, wrapped(name))
        builder.add_edge(name, "orchestrator")

    def fan_out(state):
        # Each worker gets a single document; the documents reducer joins all writes.
        return [Send("extraction", {"work_state": state, "upload": upload})
                for upload in state.get("uploads", [])] or "aggregate"

    def extract(task):
        snapshot = deepcopy(task["work_state"])
        snapshot["uploads"] = [deepcopy(task["upload"])]
        update = validate_update("extraction", agents["extraction"](snapshot))
        records = update.get("documents", [])
        if len(records) != 1 or records[0]["doc_id"] != task["upload"]["doc_id"]:
            raise ValueError("Extraction must return exactly its assigned document ID")
        return update

    def human(state):
        record = next(e for e in state["escalations"] if e["id"] == state["pending_escalation"])
        payload = interrupt({"type": "staff_resolution", "escalation": record})
        return apply_resolution(state, payload)

    builder.add_node("dispatch", lambda state: {})
    builder.add_conditional_edges("dispatch", fan_out, ["extraction", "aggregate"])
    builder.add_node("extraction", extract)
    builder.add_edge("extraction", "aggregate")
    builder.add_node("aggregate", lambda state: {"last_agent": "extraction"})
    builder.add_edge("aggregate", "orchestrator")
    builder.add_node("human", human)
    builder.add_edge("human", "orchestrator")
    builder.add_edge(START, "orchestrator")
    destinations = {name: name for name in ["intake", "rules", "computation", "review",
                                            "dispatch", "human", "orchestrator"]}
    builder.add_conditional_edges("orchestrator", lambda state: state["next_agent"],
                                  destinations | {"end": END})
    return builder.compile(checkpointer=checkpointer)
