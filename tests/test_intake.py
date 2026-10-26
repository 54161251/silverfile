from src.agents.intake import (
    QUESTIONS,
    field_path,
    next_question,
    parse_birth_date,
    parse_filing_status,
    parse_yes_no,
    run,
    run_interactive,
    build_summary,
    parse_ssn,
    handle_answer
)


def test_filing_status_married_maps_to_mfj():
    assert parse_filing_status("Married") == "mfj"


def test_widowed_is_not_guessed():
    assert parse_filing_status("widowed") is None


def test_birth_date_formats():
    assert parse_birth_date("03/05/1958") == "1958-03-05"
    assert parse_birth_date("March 5, 1958") == "1958-03-05"
    assert parse_birth_date("banana") is None


def test_yes_no():
    assert parse_yes_no("yes") is True
    assert parse_yes_no("no") is False
    assert parse_yes_no("maybe") is None


def test_questions_asked_in_order():
    assert next_question({})["field"] == "filing_status"
    assert next_question({"filing_status": "single"})["field"] == "birth_date"


def test_false_answer_is_not_asked_again():
    intake = {"filing_status": "single",
                "taxpayer": {"birth_date": "1958-03-05", "blind": False,
                           "ssn": "901-55-1234"},
              "dual_status_alien": False,
              "can_be_claimed_as_dependent": False}
    assert next_question(intake) is None


def test_earlier_answers_are_kept():
    first = run({"latest_answer": "single"})
    second = run({"intake": first["intake"], "latest_answer": "March 5, 1958"})
    assert second["intake"]["filing_status"] == "single"
    assert second["intake"]["taxpayer"]["birth_date"] == "1958-03-05"


def test_unclear_answer_raises_uncertain_flag():
    result = run({"latest_answer": "widowed"})
    assert result["intake"] == {}
    assert result["flags"][0]["type"] == "uncertain_answer"

def test_dual_status_question_is_asked_last_and_saved():
    intake = {"filing_status": "single",
              "taxpayer": {"birth_date": "1958-03-05", "blind": False,
                           "ssn": "901-55-1234"}}
    assert next_question(intake)["field"] == "dual_status_alien"
    result = run({"intake": intake, "latest_answer": "no"})
    assert result["intake"]["dual_status_alien"] is False

def test_field_paths_are_full_paths():
    paths = [field_path(q) for q in QUESTIONS]
    assert "intake.filing_status" in paths
    assert "intake.taxpayer.birth_date" in paths

def test_interrupt_asks_question_and_resumes_with_answer():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command

    from src.agents.intake import run_interactive

    builder = StateGraph(dict)
    builder.add_node("intake", run_interactive)
    builder.add_edge(START, "intake")
    builder.add_edge("intake", END)
    graph = builder.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t1"}}

    first = graph.invoke({}, config)
    payload = first["__interrupt__"][0].value
    assert payload["type"] == "intake"
    assert payload["fields"] == ["intake.filing_status"]

    final = graph.invoke(Command(resume={"answer": "single"}), config)
    assert final["intake"]["filing_status"] == "single"

def test_advice_request_is_flagged_and_not_answered():
    result = run({"latest_answer": "Should I convert my IRA to a Roth?"})
    assert result["intake"] == {}
    assert result["flags"][0]["type"] == "advice_request"
    assert result["open_questions"] == ["filing_status"]

def test_advice_request_gets_polite_notice_and_same_question():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command

    builder = StateGraph(dict)
    builder.add_node("intake", run_interactive)
    builder.add_edge(START, "intake")
    builder.add_edge("intake", END)
    graph = builder.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t2"}}

    graph.invoke({}, config)
    second = graph.invoke(
        Command(resume={"answer": "Should I convert my IRA to a Roth?"}), config
    )
    payload = second["__interrupt__"][0].value
    assert "can't advise" in payload["question"]
    assert payload["fields"] == ["intake.filing_status"]

def test_summary_lists_done_and_remaining():
    text = build_summary({"filing_status": "single"})
    assert "your filing status" in text
    assert "Still to go" in text
    assert "your date of birth" in text.split("Still to go")[1]

def test_summary_is_empty_when_nothing_answered():
    assert build_summary({}) == ""

def test_resumed_session_shows_summary_first():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph

    builder = StateGraph(dict)
    builder.add_node("intake", run_interactive)
    builder.add_edge(START, "intake")
    builder.add_edge("intake", END)
    graph = builder.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t3"}}

    first = graph.invoke({"intake": {"filing_status": "single"}}, config)
    question = first["__interrupt__"][0].value["question"]
    assert question.startswith("So far we have covered")
    assert "date of birth" in question

def test_ssn_accepts_only_900_series():
    assert parse_ssn("901-55-1234") == "901-55-1234"
    assert parse_ssn("901551234") == "901-55-1234"
    assert parse_ssn("123-45-6789") is None
    assert parse_ssn("banana") is None

def test_volunteered_ssn_is_not_saved_and_flag_has_no_number():
    result = handle_answer({}, "my ssn is 123-45-6789", 1)
    assert result["intake"] == {}
    flag = result["flags"][0]
    assert flag["type"] == "ssn_volunteered"
    assert "6789" not in flag["excerpt"]

def test_volunteered_ssn_gets_polite_notice_and_same_question():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command

    builder = StateGraph(dict)
    builder.add_node("intake", run_interactive)
    builder.add_edge(START, "intake")
    builder.add_edge("intake", END)
    graph = builder.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t4"}}

    graph.invoke({}, config)
    second = graph.invoke(
        Command(resume={"answer": "my ssn is 123-45-6789"}), config
    )
    payload = second["__interrupt__"][0].value
    assert "don't need to share" in payload["question"]
    assert "6789" not in payload["question"]
    assert payload["fields"] == ["intake.filing_status"]