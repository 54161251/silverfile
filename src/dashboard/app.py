"""Kushim staff dashboard page (P7). Run through streamlit_app.py at the repository root.

Lists every return in progress or finished, queues the ones waiting on a human (HITL), and
lets a signed-in staff member resolve an escalation, which resumes the LangGraph session.
Everything shown is read from checkpoints; the only write is a ResumePayload (B7).
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import streamlit as st

from src.dashboard import auth, resolution
from src.dashboard.form_render import FILING_STATUS_LABELS, mask_ssn, render_form, render_page
from src.dashboard.pdf_fill import fill_pdf
from src.dashboard.previews import golden_previews
from src.dashboard.store import GROUPS, TZ, Store

DEFAULT_DB = "runtime/sessions.sqlite"
GROUP_ICONS = {"needs_staff": ":material/front_hand:", "waiting_taxpayer": ":material/hourglass_top:",
               "in_progress": ":material/sync:", "completed": ":material/task_alt:", "closed": ":material/block:"}
STYLE = """<style>
[data-testid="stMetricValue"]{font-variant-numeric:tabular-nums}
.sf-chip{display:inline-block;padding:2px 10px;border-radius:999px;font-size:0.85rem;font-weight:600;
 border:1px solid #d0d7de;margin-right:6px}
.sf-needs_staff{background:#fff1e5;border-color:#f0a35e;color:#8a4600}
.sf-waiting_taxpayer{background:#eef4ff;border-color:#8fb3f5;color:#1d4b9c}
.sf-in_progress{background:#f3f4f6;color:#374151}
.sf-completed{background:#e9f7ef;border-color:#7cc49a;color:#14622f}
.sf-closed{background:#f3f4f6;color:#6b7280}
</style>"""


def db_path() -> str:
    return os.getenv("SILVERFILE_DB", DEFAULT_DB)


def when(value: datetime | str | None) -> str:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if not value:
        return "—"
    return value.astimezone(TZ).strftime("%b %d, %Y %I:%M %p")


def masked(value):
    """Copy of state data with SSNs masked, for the raw-data expanders (R17)."""
    if isinstance(value, dict):
        return {k: mask_ssn(v) if k.lower().endswith("ssn") and v else masked(v) for k, v in value.items()}
    if isinstance(value, list):
        return [masked(v) for v in value]
    return value


def chip(group: str) -> str:
    return f'<span class="sf-chip sf-{group}">{GROUPS[group]}</span>'


def open_thread(thread_id: str | None) -> None:
    if thread_id:
        st.query_params["thread"] = thread_id
    else:
        st.query_params.pop("thread", None)


# --- Sidebar: staff sign-in ----------------------------------------------------------

def sidebar() -> auth.Staff | None:
    with st.sidebar:
        st.subheader("Kushim staff")
        staff = st.session_state.get("staff")
        if staff:
            st.success(f"Signed in as **{staff.staff_id}**", icon=":material/badge:")
            if st.button("Sign out", use_container_width=True):
                st.session_state.pop("staff")
                st.rerun()
        elif not auth.sign_in_available():
            st.info("Sign-in is off. Set SILVERFILE_STAFF_IDS and SILVERFILE_STAFF_PASSCODE in .env "
                    "to resolve escalations. Viewing is still available.", icon=":material/lock:")
        else:
            with st.form("sign_in", border=False):
                staff_id = st.text_input("Staff ID", placeholder="e.g. staff_jlee")
                passcode = st.text_input("Passcode", type="password")
                if st.form_submit_button("Sign in", use_container_width=True, type="primary"):
                    who = auth.authenticate(staff_id, passcode)
                    if who:
                        st.session_state["staff"] = who
                        st.rerun()
                    st.error("Staff ID or passcode not recognised.")
        st.divider()
        st.caption(f"Sessions database: `{db_path()}`")
        if st.button("Refresh", icon=":material/refresh:", use_container_width=True):
            st.rerun()
        st.caption("SilverFile prepares drafts only. It never files a return and never gives tax advice.")
    return st.session_state.get("staff")


# --- Overview -------------------------------------------------------------------------

def overview(store: Store) -> None:
    rows = store.summaries()
    counts = {g: sum(r.group == g for r in rows) for g in GROUPS}
    for column, (group, label) in zip(st.columns(len(GROUPS)), GROUPS.items()):
        column.metric(label, counts[group], border=True)

    queue_tab, all_tab, sample_tab = st.tabs([f"HITL queue ({counts['needs_staff']})", f"All returns ({len(rows)})",
                                              "Sample returns"])
    with queue_tab:
        queue = [r for r in rows if r.group == "needs_staff"]
        if not queue:
            st.success("Nothing is waiting for staff.", icon=":material/check_circle:")
        for row in queue:
            esc = row.pending
            with st.container(border=True):
                left, mid, right = st.columns([2, 5, 1.4], vertical_alignment="center")
                left.markdown(f"**{esc['code']} · {esc['kind']}**  \n`{row.thread_id}`")
                mid.markdown(f"{esc['reason']}  \n:gray[Raised by {esc['raised_by']} · {when(esc['created_at'])}]")
                if right.button("Open & resolve", key=f"q_{row.thread_id}", type="primary", use_container_width=True):
                    open_thread(row.thread_id)
                    st.rerun()
    with all_tab:
        if not rows:
            st.info("No sessions yet. Start one with `python run.py start --demo --thread-id demo-1` "
                    "(add `--hitl` for an escalation).", icon=":material/info:")
        else:
            table = [{"Return": r.thread_id, "Status": r.group_label, "Pipeline step": r.status,
                      "Filing status": FILING_STATUS_LABELS.get(r.filing_status, r.filing_status or "—"),
                      "Open escalations": ", ".join(r.open_codes) or "—", "Documents": r.documents,
                      "Lines": r.lines, "Mode": r.mode, "Last activity": when(r.updated_at)} for r in rows]
            event = st.dataframe(table, hide_index=True, use_container_width=True, on_select="rerun",
                                 selection_mode="single-row", key="returns_table")
            st.caption("Select a row to open the return.")
            if event.selection.rows:
                open_thread(rows[event.selection.rows[0]].thread_id)
                st.rerun()
    with sample_tab:
        samples()


@st.cache_data(show_spinner=False)
def _previews() -> list[dict]:
    return golden_previews()


def samples() -> None:
    st.caption("Computed live by the Computation agent from P2's golden test returns. Test data only, "
               "not taxpayer sessions; they never appear in the returns list.")
    previews = _previews()
    names = [p["name"] for p in previews]
    choice = st.selectbox("Sample return", names, format_func=lambda n: n.replace("_", " "))
    preview = previews[names.index(choice)]
    st.markdown(f"_{preview['description']}_")
    if preview["open_questions"]:
        st.warning("Computation is blocked until these are answered:\n\n"
                   + "\n".join(f"- `{q}`" for q in preview["open_questions"]), icon=":material/help:")
        return
    status = preview["state"].get("filing_status_validated")
    form_view(preview["lines"], preview["state"].get("intake", {}), status, f"sample-{choice}")


# --- Detail ---------------------------------------------------------------------------

def form_view(lines: dict, intake: dict, filing_status: str | None, name: str) -> None:
    meta = {"filing_status": filing_status, "title": f"Draft Form 1040-SR (2025) · {name}"}
    left, right, _ = st.columns([1, 1, 3])
    left.download_button("Download HTML", render_page(lines, intake, meta), file_name=f"{name}-1040sr-draft.html",
                         mime="text/html", icon=":material/download:", use_container_width=True)
    right.download_button("Download IRS PDF", fill_pdf(lines, intake, filing_status),
                          file_name=f"{name}-1040sr-DRAFT.pdf", mime="application/pdf",
                          icon=":material/picture_as_pdf:", use_container_width=True)
    st.html(render_form(lines, intake, meta))


def resolve_panel(store: Store, summary, staff) -> None:
    esc = summary.pending
    with st.container(border=True):
        st.markdown(f"#### :material/front_hand: Escalation {esc['id']} · {esc['code']} ({esc['kind']})")
        a, b = st.columns(2)
        a.markdown(f"**Reason**  \n{esc['reason']}")
        b.markdown(f"**Raised by** {esc['raised_by']} · {when(esc['created_at'])}")
        heard = resolution.taxpayer_message(esc["code"])
        if heard:
            st.markdown(f"**What the taxpayer heard**  \n> {heard}")
        if esc.get("evidence"):
            st.markdown("**Evidence**  \n" + "  \n".join(f"`{item}`" for item in esc["evidence"]))
        if not staff:
            st.warning("Sign in as Kushim staff (sidebar) to resolve this escalation.", icon=":material/lock:")
            return
        key = f"{summary.thread_id}_{esc['id']}"
        # No preselected option: closing a session must be a deliberate choice.
        option = st.radio("Decision", esc["options"], format_func=resolution.option_label, key=f"opt_{key}",
                          index=None)
        kind = resolution.override_kind(esc["code"], option) if option else None
        path, value = "", None
        if kind:
            path = st.text_input("Field to correct", value=resolution.suggested_path(esc), key=f"path_{key}",
                                 help="intake.<field> or user_inputs.<line>. Recorded as a human_resolution.")
            if kind == "filing_status":
                value = st.selectbox("Filing status", resolution.FILING_STATUSES,
                                     format_func=FILING_STATUS_LABELS.get, key=f"fs_{key}")
            else:
                text = st.text_input("Corrected amount (whole dollars)" if kind == "amount" else "Corrected value",
                                     key=f"val_{key}")
                if text:
                    try:
                        value = resolution.parse_value(path, text)
                    except ValueError as exc:
                        st.error(str(exc))
        note = st.text_area("Note for the audit record", key=f"note_{key}",
                            placeholder="What you checked and why you chose this option")
        if st.button("Resolve and resume", type="primary", icon=":material/play_arrow:", key=f"go_{key}"):
            try:
                if not option:
                    raise ValueError("Choose a decision first")
                payload = resolution.build_payload(esc, option, note, staff.staff_id, path, value)
                with st.spinner("Resuming the session…"):
                    after = store.resolve(summary.thread_id, payload, staff)
                st.session_state["flash"] = f"{esc['id']} resolved as “{resolution.option_label(option)}”. " \
                                            f"Return is now: {after.group_label}."
                st.rerun()
            except (ValueError, PermissionError) as exc:
                st.error(str(exc), icon=":material/error:")


def detail(store: Store, thread_id: str, staff) -> None:
    if st.button("All returns", icon=":material/arrow_back:"):
        open_thread(None)
        st.rerun()
    try:
        summary, state = store.state(thread_id)
    except KeyError:
        st.error(f"No session called `{thread_id}`.")
        return
    st.markdown(f"### Return `{thread_id}`")
    st.markdown(chip(summary.group) + f'<span class="sf-chip">step: {summary.status}</span>'
                + f'<span class="sf-chip">mode: {summary.mode}</span>', unsafe_allow_html=True)
    facts = [("Filing status", FILING_STATUS_LABELS.get(summary.filing_status, summary.filing_status or "—")),
             ("Documents", summary.documents), ("Lines computed", summary.lines),
             ("Last activity", when(summary.updated_at))]
    for column, (label, value) in zip(st.columns(len(facts)), facts):
        column.markdown(f":gray[{label}]  \n**{value}**")
    if flash := st.session_state.pop("flash", None):
        st.success(flash, icon=":material/check_circle:")
    if summary.pending:
        resolve_panel(store, summary, staff)
    elif summary.intake_fields:
        asked = f"\u201c{summary.question}\u201d  \n" if summary.question else ""
        st.info(f"Waiting for the taxpayer to answer: {asked}"
                + ", ".join(f"`{f}`" for f in summary.intake_fields), icon=":material/hourglass_top:")

    form_tab, esc_tab, doc_tab, rules_tab, trace_tab = st.tabs(
        ["Draft form", "Escalations", "Documents", "Rules & review", "Trace"])
    with form_tab:
        if state.get("lines"):
            form_view(state["lines"], state.get("intake", {}), summary.filing_status, thread_id)
        else:
            st.info("No line values yet. In demo mode the Computation step is a placeholder; the "
                    "Sample returns tab shows a fully computed draft.", icon=":material/info:")
    with esc_tab:
        escalation_log(state.get("escalations", []))
    with doc_tab:
        documents(state.get("documents", []))
    with rules_tab:
        left, right = st.columns(2)
        left.markdown("**Eligibility**")
        left.json(state.get("eligibility", {}), expanded=True)
        right.markdown("**Scope and schedules**")
        right.json({"scope": state.get("scope", {}), "schedules": state.get("schedules", {}),
                    "box_count_12d": state.get("box_count_12d")}, expanded=True)
        if state.get("citations"):
            st.markdown("**Citations**")
            st.dataframe(state["citations"], hide_index=True, use_container_width=True)
        st.markdown(f"**Review verdict:** {state.get('review_verdict') or '—'}")
        if state.get("review_findings"):
            st.dataframe(state["review_findings"], hide_index=True, use_container_width=True)
        with st.expander("Intake answers (SSNs masked)"):
            st.json(masked(state.get("intake", {})))
    with trace_tab:
        st.markdown(f"Review iterations: **{state.get('iterations', 0)}** · "
                    f"Total handoffs: **{state.get('total_handoffs', 0)}**")
        history = state.get("handoff_history", [])
        st.dataframe([{"#": i + 1, "From": a, "To": b} for i, (a, b) in enumerate(history)],
                     hide_index=True, use_container_width=True)


def escalation_log(escalations: list[dict]) -> None:
    if not escalations:
        st.caption("No escalations on this return.")
        return
    rows = []
    for e in escalations:
        res = e.get("resolution") or {}
        rows.append({"ID": e["id"], "Code": e["code"], "Kind": e["kind"], "Status": e["status"],
                     "Reason": e["reason"], "Raised": when(e.get("created_at")),
                     "Decision": resolution.option_label(res["option"]) if res.get("option") else "—",
                     "Staff": res.get("resolved_by", "—"), "Resolved": when(res.get("resolved_at")),
                     "Note": res.get("note", ""), "Overrides": json.dumps(res.get("overrides") or {}) or ""})
    st.dataframe(rows, hide_index=True, use_container_width=True)


def documents(docs: list[dict]) -> None:
    if not docs:
        st.caption("No documents extracted yet.")
        return
    for doc in docs:
        with st.container(border=True):
            st.markdown(f"**{doc['form']}** · `{doc['doc_id']}` · source: {doc.get('source_file') or '—'}")
            unverified = set(doc.get("unverified", []))
            st.dataframe([{"Box": box, "Value": value,
                           "Confidence": doc.get("confidence", {}).get(box),
                           "Needs confirmation": "yes" if box in unverified else ""}
                          for box, value in doc.get("boxes", {}).items()],
                         hide_index=True, use_container_width=True)
            if doc.get("flags"):
                st.warning("Flags: " + ", ".join(doc["flags"]))


def page() -> None:
    st.html(STYLE)
    staff = sidebar()
    st.title("SilverFile · Staff dashboard")
    store = Store(db_path())
    thread_id = st.query_params.get("thread")
    if thread_id:
        detail(store, thread_id, staff)
    else:
        overview(store)
