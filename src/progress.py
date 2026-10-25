"""P1 semantic progress signals. Persist hashes, never a second copy of answers."""
import hashlib
import json


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def progress_key(state):
    # Ignore timestamps, summaries, flags, changing prompts and computed outputs:
    # those can change without accepting any new taxpayer information.
    values = {key: value.get("value") if isinstance(value, dict) else value
              for key, value in state.get("user_inputs", {}).items()}
    documents = [{"doc_id": d["doc_id"], "form": d["form"], "boxes": d["boxes"]}
                 for d in sorted(state.get("documents", []), key=lambda d: d["doc_id"])]
    resolutions = [{"id": e["id"], "resolution": e.get("resolution")}
                   for e in state.get("escalations", []) if e.get("status") == "resolved"]
    return _hash({"intake": state.get("intake", {}), "user_inputs": values,
                  "documents": documents, "resolutions": resolutions})


def flag_keys(state):
    return [_hash({"id": f.get("id"), "type": f.get("type"), "excerpt": f.get("excerpt", "")})
            for f in state.get("flags", [])]


def guard_state(state, pair, window=10):
    key = progress_key(state)
    seen = state.get("progress_fingerprints", [])
    advanced = bool(seen) and key not in seen
    # A repeated old answer is not new progress; it cannot reset an oscillating loop.
    history = [] if advanced else state.get("stalled_handoff_history", state.get("handoff_history", []))
    stalled = 0 if advanced else state.get("handoffs_without_progress", 0)
    return {"progress_fingerprints": seen + ([key] if key not in seen else []),
            "stalled_handoff_history": (history + [pair])[-window:],
            "handoffs_without_progress": stalled + 1}
