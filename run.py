"""P1 CLI: offline skeleton, snapshots, and durable resume. No filing operations."""
import argparse
import importlib
import json
import os
from pathlib import Path

from src.demo_agents import adapters, sample
from src.memory import open_sessions


def production_adapters():
    result, missing = {}, []
    for name in ["intake", "extraction", "rules", "computation", "review"]:
        try:
            module = importlib.import_module(f"src.agents.{name}")
            result[name] = module.run_interactive if name == "intake" else module.run
        except ModuleNotFoundError as exc:
            if exc.name != f"src.agents.{name}":
                raise
            missing.append(name)
    if missing:
        raise ValueError(f"Production adapters not implemented: {', '.join(missing)}. Use --demo for the routing skeleton.")
    return result


def summary(snapshot):
    state = snapshot.values
    return {"session_id": state.get("session_id"), "mode": state.get("mode"),
            "status": state.get("status"), "documents": len(state.get("documents", [])),
            "pending_escalation": state.get("pending_escalation") or None,
            "waiting_nodes": list(snapshot.next),
            "notice": "Routing demonstration only; no tax return calculated." if state.get("mode") == "demo" else "Draft only; never filed."}


def batch(args):
    """Spec 4.5: the 10-document batch with the context strategy on or off (src/batch.py)."""
    from src.agents.intake_briefing import BriefingFailed, model_name
    from src.batch import run_batch, save_run, write_metrics
    from src.dashboard.auth import load_env_file
    load_env_file()  # SILVERFILE_MODEL, ANTHROPIC_API_KEY (R6); real environment variables win
    from src.api_key import load_api_key
    if not args.estimate and not load_api_key():
        raise SystemExit("No API key found. Set ANTHROPIC_API_KEY, put it in .env or "
                         "api_key.txt, or run with --estimate.")
    strategy = "full_history" if args.no_context_strategy else "selective_recall"
    client = None
    if not args.estimate:
        import anthropic
        client = anthropic.Anthropic()
    try:
        rows = run_batch(strategy, client=client, estimate=args.estimate, session_id=args.thread_id)
    except BriefingFailed as exc:
        raise SystemExit(f"Batch stopped (E8): {exc}")
    save_run(strategy, rows, estimate=args.estimate, model=model_name())
    print(f"{strategy}: " + ", ".join(f"{row['input_tokens']:,}" for row in rows))
    print(f"Updated {write_metrics()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "resume", "status", "diagram", "batch"])
    parser.add_argument("--thread-id", default="silverfile-demo")
    parser.add_argument("--db", default=os.getenv("SILVERFILE_DB", "runtime/sessions.sqlite"))
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--hitl", action="store_true", help="Start the synthetic exploitation-review example")
    parser.add_argument("--input", type=Path, help="JSON initial input or resume payload")
    parser.add_argument("--no-context-strategy", action="store_true",
                        help="batch: resend the full history for every document (spec 4.5 baseline)")
    parser.add_argument("--estimate", action="store_true",
                        help="batch: no API call; estimate input tokens offline")
    args = parser.parse_args()
    if args.action == "batch":
        return batch(args)
    try:
        agents = adapters() if args.demo else production_adapters()
        with open_sessions(args.db, agents) as sessions:
            if args.action == "diagram":
                print(sessions.graph.get_graph().draw_mermaid())
                return
            if args.action == "start":
                inputs = json.loads(args.input.read_text(encoding="utf-8")) if args.input else sample(args.hitl)
                if not args.demo and not args.input:
                    raise ValueError("Production start requires --input")
                sessions.start(args.thread_id, inputs, mode="demo" if args.demo else "production")
            elif args.action == "resume":
                if not args.input:
                    raise ValueError("Resume requires --input with a JSON payload")
                saved_mode = sessions.snapshot(args.thread_id).values.get("mode")
                if saved_mode != ("demo" if args.demo else "production"):
                    raise ValueError("Resume with the same --demo setting used to start the session")
                sessions.resume(args.thread_id, json.loads(args.input.read_text(encoding="utf-8")))
            snapshot = sessions.snapshot(args.thread_id)
            if not snapshot.values:
                raise ValueError("Session not found")
            print(json.dumps(summary(snapshot), indent=2))
    except (ValueError, OSError) as exc:
        # No input contents or full persistent state are printed to the terminal.
        parser.exit(2, f"Cannot complete operation ({type(exc).__name__}); check inputs and integration setup.\n")


if __name__ == "__main__":
    main()
