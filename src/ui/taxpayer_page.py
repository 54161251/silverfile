"""Taxpayer page: one Intake question at a time (P7 UI for docs/P1_INTAKE_HANDOFF.md).

Contract with P3's Intake: when the session pauses with {"type": "intake", "question", "fields"},
show `question`; send the reply as sessions.resume(thread_id, {"answer": text}). Answers are
screened for SSNs first (src/ui/answers.py). When staff must step in, the taxpayer sees only
the neutral sentence from P5's escalation catalog, never the internal reason.

Accessibility (spec §4.3): one question per screen, 20 px text, high contrast, a labelled
answer box with a real Send button, the question announced to screen readers, a one-tap
"I'm not sure", and a session code so a visit can stop on Tuesday and resume on Friday with a
summary of what was already covered.
"""
from __future__ import annotations

import html
import secrets
from copy import deepcopy

import streamlit as st

from src.agents import intake as intake_agent
from src.agents.intake import QUESTIONS, field_path
from src.dashboard.app import db_path
from src.dashboard.resolution import taxpayer_message
from src.dashboard.store import Store, agents_for
from src.demo_agents import sample
from src.memory import open_sessions
from src.ui.answers import screen

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I/L to misread
NOT_SURE = "I'm not sure"
STYLE = """<style>
.stMainBlockContainer{max-width:820px}
.stMainBlockContainer p,.stMainBlockContainer li,.stMainBlockContainer label,
.stMainBlockContainer textarea,.stMainBlockContainer input,.stMainBlockContainer button{font-size:20px !important}
.stMainBlockContainer textarea{line-height:1.5}
.sf-question{font-size:26px;line-height:1.45;font-weight:600;color:#1b1f24;background:#f3f6f9;
 border-left:6px solid #1f4e79;border-radius:6px;padding:18px 20px;margin:8px 0 16px}
.sf-code{font-family:ui-monospace,Consolas,monospace;font-size:24px;letter-spacing:2px;font-weight:700}
.sf-said{color:#424a53;margin:2px 0 10px 0}
</style>"""
DONE_TEXT = ("Thank you. You’ve answered everything we need for now. A Kushim preparer will check "
             "your draft return and contact you. SilverFile never files a return for you.")
CLOSED_TEXT = "Thank you. One of our specialists will contact you to finish your return."
PLAIN_VALUES = {"single": "Single", "mfj": "Married, filing together", "mfs": "Married, filing separately",
                "hoh": "Head of household", "qss": "Widowed (qualifying surviving spouse)",
                "direct_deposit": "Direct deposit", "check": "Mailed check", "taxpayer": "Your own",
                "joint": "Joint", "spouse": "Your spouse's", "other": "Someone else's", "unknown": "Not sure",
                True: "Yes", False: "No"}


def plain_label(question: dict) -> str:
    """Intake's own wording for a question (intake.LABELS), else the field name."""
    label = getattr(intake_agent, "LABELS", {}).get(field_path(question))
    label = label or question["field"].replace("_", " ")
    return label[:1].upper() + label[1:]


def plain_value(path: str, value) -> str:
    if path.endswith(".ssn"):
        return f"XXX-XX-{str(value)[-4:]}"  # R17: never show a full SSN back
    if isinstance(value, (bool, str)) and value in PLAIN_VALUES:
        return PLAIN_VALUES[value]
    return str(value)


def new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"SF-{raw[:4]}-{raw[4:]}"


def normalise_code(text: str) -> str:
    return "-".join(part for part in (text or "").upper().replace(" ", "-").split("-") if part)


def starter_inputs() -> dict:
    """Synthetic household documents for the demo, with every answer Intake asks removed.

    Uploads can only be attached when a session starts. Until P4's W-2 upload lands, the page
    starts from P1's synthetic sample and lets Intake ask its own questions. New questions in
    intake.QUESTIONS are removed automatically.
    """
    inputs = deepcopy(sample())
    for question in QUESTIONS:
        parts = field_path(question).split(".")[1:]
        cursor = inputs["intake"]
        for part in parts[:-1]:
            cursor = cursor.get(part, {})
        cursor.pop(parts[-1], None)
    return inputs


def session_mode() -> str:
    try:
        agents_for("production")
        return "production"
    except ValueError:
        return "demo"  # some production agents are not merged yet


def _value(intake: dict, path: str):
    cursor = intake
    for part in path.split(".")[1:]:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(part)
    return cursor


def covered(intake: dict) -> list[tuple[str, str]]:
    """Plain-language list of answers already recorded, for a returning visitor."""
    rows = []
    for question in QUESTIONS:
        path = field_path(question)
        value = _value(intake, path)
        if value not in (None, ""):
            rows.append((plain_label(question), plain_value(path, value)))
    return rows


def waiting(snapshot) -> dict | None:
    for task in snapshot.tasks or ():
        for item in getattr(task, "interrupts", ()) or ():
            if isinstance(item.value, dict):
                return item.value
    return None


def send_answer(thread_id: str, mode: str, text: str) -> None:
    with open_sessions(db_path(), agents_for(mode)) as sessions:
        sessions.resume(thread_id, {"answer": text})


def start_screen() -> None:
    st.markdown("We’ll ask you a few questions about your 2025 tax return, **one at a time**. "
                "There are no wrong answers, and you can say “I’m not sure” at any point.")
    if st.button("Start a new return", type="primary", icon=":material/play_arrow:"):
        code, mode = new_code(), session_mode()
        with st.spinner("Getting your first question…"):
            with open_sessions(db_path(), agents_for(mode)) as sessions:
                sessions.start(code, starter_inputs(), mode=mode)
        st.session_state.update(sf_thread=code, sf_transcript=[], sf_new=True)
        st.rerun()
    st.divider()
    with st.form("resume", border=False):
        typed = st.text_input("Continue a saved return: type your session code", placeholder="SF-XXXX-XXXX")
        if st.form_submit_button("Continue", icon=":material/history:"):
            code = normalise_code(typed)
            try:
                Store(db_path()).state(code)
            except (KeyError, ValueError):
                st.error("We couldn’t find that code. Please check it and try again, or start a new return.")
            else:
                st.session_state.update(sf_thread=code, sf_transcript=[], sf_new=False)
                st.rerun()


def conversation(thread_id: str) -> None:
    try:
        summary, state = Store(db_path()).state(thread_id)
    except KeyError:
        st.session_state.pop("sf_thread", None)
        st.rerun()
    with open_sessions(db_path(), agents_for(summary.mode)) as sessions:
        pause = waiting(sessions.snapshot(thread_id))

    st.markdown(f'Your session code: <span class="sf-code">{html.escape(thread_id)}</span>',
                unsafe_allow_html=True)
    st.caption("Write this code down. You can close this page and use it to continue later.")
    done = covered(state.get("intake", {}))
    if done and not st.session_state.get("sf_new"):
        with st.expander("What we have so far", expanded=True):
            st.markdown("\n".join(f"- **{label}:** {value}" for label, value in done))
    for said in st.session_state.get("sf_transcript", []):
        st.markdown(f"**{said['question']}**")
        st.markdown(f'<p class="sf-said">You said: {html.escape(said["answer"])}</p>', unsafe_allow_html=True)
    if notice := st.session_state.pop("sf_notice", None):
        st.info(notice, icon=":material/shield:")

    if pause and pause.get("type") == "intake":
        question = pause.get("question") or "Please answer the next question."
        if pause.get("summary"):
            st.caption(pause["summary"])
        st.html(f'<div class="sf-question" role="status" aria-live="polite">{html.escape(question)}</div>')
        with st.form("answer", clear_on_submit=True, border=False):
            text = st.text_area("Your answer", height=110, key="sf_answer")
            send, unsure = st.columns(2)
            pressed_send = send.form_submit_button("Send answer", type="primary", use_container_width=True)
            pressed_unsure = unsure.form_submit_button(NOT_SURE, use_container_width=True)
        if pressed_send or pressed_unsure:
            checked = screen(NOT_SURE if pressed_unsure else text, pause.get("fields"))
            if checked.send is None:
                st.error(checked.notice, icon=":material/error:")
                return
            with st.spinner("Saving your answer…"):
                send_answer(thread_id, summary.mode, checked.send)
            st.session_state.setdefault("sf_transcript", []).append({"question": question, "answer": checked.shown})
            st.session_state["sf_new"] = True
            if checked.notice:
                st.session_state["sf_notice"] = checked.notice
            st.rerun()
    elif pause and pause.get("type") == "staff_resolution":
        message = taxpayer_message(pause["escalation"]["code"]) or "A colleague will look at this before we continue."
        st.info(f"{message} You can close this page; we’ll be in touch, and your code keeps your place.",
                icon=":material/support_agent:")
    elif summary.group == "completed":
        st.success(DONE_TEXT, icon=":material/task_alt:")
    elif summary.group == "closed":
        st.info(CLOSED_TEXT, icon=":material/support_agent:")
    else:
        st.info("We’re working on your answers. Please check back in a moment.", icon=":material/hourglass_top:")
        st.button("Check again", icon=":material/refresh:")

    st.divider()
    if st.button("Leave for now", icon=":material/logout:"):
        for key in ("sf_thread", "sf_transcript", "sf_new"):
            st.session_state.pop(key, None)
        st.rerun()


def page() -> None:
    st.html(STYLE)
    st.title("SilverFile")
    st.caption("A Kushim service that prepares a draft return for a person to check. "
               "It never files anything and can’t give tax advice.")
    thread_id = st.session_state.get("sf_thread")
    if thread_id:
        conversation(thread_id)
    else:
        start_screen()
