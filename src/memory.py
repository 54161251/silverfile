"""SQLite lifecycle and public session API for P3/P7 (one household per thread)."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from src.graph import build_graph
from src.human import apply_resolution
from src.state import validate_intake


class Sessions:
    def __init__(self, graph):
        self.graph = graph

    @staticmethod
    def config(thread_id):
        if not thread_id or len(thread_id) > 128:
            raise ValueError("Provide a thread_id between 1 and 128 characters")
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": 400,
                "max_concurrency": 8}

    def start(self, thread_id, inputs, mode="production"):
        config = self.config(thread_id)
        if self.graph.get_state(config).values:
            raise ValueError("Thread already exists; resume it or use a new thread_id")
        allowed = {"intake", "uploads", "user_inputs", "flags", "session_summary"}
        if set(inputs) - allowed:
            raise ValueError("Initial input contains internal state fields")
        if mode not in {"demo", "production"}:
            raise ValueError("Unknown execution mode")
        validate_intake(inputs)
        state = deepcopy(inputs) | {"session_id": thread_id, "mode": mode, "status": "intake",
                                   "last_agent": "start", "iterations": 0, "total_handoffs": 0}
        return self.graph.invoke(state, config)

    def resume(self, thread_id, payload):
        config = self.config(thread_id)
        snapshot = self.graph.get_state(config)
        if not snapshot.next:
            raise ValueError("Session is not waiting for input")
        # Validate before passing Command: raw input must not enter a checkpoint first.
        validate_intake(payload)
        if snapshot.values.get("status") == "awaiting_human":
            apply_resolution(snapshot.values, payload)
        return self.graph.invoke(Command(resume=payload), config)

    def snapshot(self, thread_id):
        return self.graph.get_state(self.config(thread_id))


@contextmanager
def open_sessions(path, agents):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(path)) as checkpointer:
        yield Sessions(build_graph(checkpointer, agents))
