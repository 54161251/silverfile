from src.agents.intake import (
    QUESTIONS,
    build_summary,
    field_path,
    handle_answer,
    next_question,
    out_of_scope_items,
    parse_account_owner,
    parse_birth_date,
    parse_filing_status,
    parse_refund_method,
    parse_ssn,
    parse_yes_no,
    run,
    run_interactive,
    wants_to_go_back,
    previous_question,
    dependent_question
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

def test_third_party_answer_is_flagged_and_not_saved():
    result = handle_answer({}, "I am answering for my mother", 1)
    assert result["intake"] == {}
    assert result["flags"][0]["type"] == "third_party_answering"

def test_third_party_gets_notice_and_same_question():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command

    builder = StateGraph(dict)
    builder.add_node("intake", run_interactive)
    builder.add_edge(START, "intake")
    builder.add_edge("intake", END)
    graph = builder.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t5"}}

    graph.invoke({}, config)
    second = graph.invoke(
        Command(resume={"answer": "I am answering for my mother"}), config
    )
    payload = second["__interrupt__"][0].value
    assert "colleague" in payload["question"]
    assert payload["fields"] == ["intake.filing_status"]

def test_spouse_question_only_asked_when_married_joint():
    base = {"taxpayer": {"birth_date": "1958-03-05", "ssn": "901-55-1234",
                         "blind": False},
            "dual_status_alien": False,
            "can_be_claimed_as_dependent": False}
    single = dict(base, filing_status="single")
    joint = dict(base, filing_status="mfj")
    assert next_question(single) is None
    assert next_question(joint)["field"] == "birth_date"
    assert field_path(next_question(joint)) == "intake.spouse.birth_date"

def test_spouse_questions_only_asked_when_married_joint():
    base = {"taxpayer": {"birth_date": "1958-03-05", "ssn": "901-55-1234",
                         "blind": False},
            "dual_status_alien": False,
            "can_be_claimed_as_dependent": False}
    single = dict(base, filing_status="single")
    joint = dict(base, filing_status="mfj")
    assert next_question(single) is None
    paths = []
    state = dict(joint)
    for answer in ("March 5, 1959", "901-66-4321", "no"):
        q = next_question(state)
        paths.append(field_path(q))
        state = run({"intake": state, "latest_answer": answer})["intake"]
    assert paths == ["intake.spouse.birth_date", "intake.spouse.ssn",
                     "intake.spouse.blind"]
    assert next_question(state) is None

def test_rules_missing_path_is_asked_first():
    intake = {"filing_status": "mfj",
              "taxpayer": {"birth_date": "1958-03-05", "ssn": "901-55-1234",
                           "blind": False},
              "dual_status_alien": False,
              "can_be_claimed_as_dependent": False}
    q = next_question(intake, ["intake.spouse.ssn"])
    assert field_path(q) == "intake.spouse.ssn"

def test_refund_method_and_owner_parsing():
    assert parse_refund_method("direct deposit") == "direct_deposit"
    assert parse_refund_method("mail me a check") == "check"
    assert parse_account_owner("my own account") == "taxpayer"
    assert parse_account_owner("not sure") == "unknown"
    assert parse_account_owner("my son's account") == "other"
    assert parse_account_owner("a person") is None
    assert parse_account_owner("banana") is None

def test_correction_is_flagged_and_keeps_answers():
    state = {"intake": {"filing_status": "single"}}
    result = handle_answer(state, "Sorry, I meant 1957", 1)
    assert result["intake"] == {"filing_status": "single"}
    assert result["flags"][0]["type"] == "contradiction"

def test_refund_questions_are_conditional():
    base = {"filing_status": "single",
            "taxpayer": {"birth_date": "1958-03-05", "ssn": "901-55-1234",
                         "blind": False},
            "dual_status_alien": False,
            "can_be_claimed_as_dependent": False}
    assert next_question(base) is None
    started = dict(base, refund={})
    assert field_path(next_question(started)) == "intake.refund.method"
    deposit = dict(base, refund={"method": "direct_deposit"})
    assert field_path(next_question(deposit)) == "intake.refund.account_owner"
    mailed = dict(base, refund={"method": "check"})
    assert next_question(mailed) is None

def test_session_resumes_after_closing_sqlite(tmp_path):
    from src.demo_agents import adapters
    from src.memory import open_sessions

    path = tmp_path / "resume.db"
    with open_sessions(path, adapters()) as sessions:
        first = sessions.start("tue", {"intake": {}}, mode="demo")
    assert first["__interrupt__"][0].value["fields"] == ["intake.filing_status"]

    with open_sessions(path, adapters()) as sessions:
        second = sessions.resume("tue", {"answer": "single"})
    payload = second["__interrupt__"][0].value
    assert payload["fields"] == ["intake.taxpayer.birth_date"]
    assert payload["question"].startswith("So far we have covered")

def test_out_of_scope_items_are_detected():
    assert out_of_scope_items("I also rent out a house") == ["rental"]
    assert out_of_scope_items("I sold some bitcoin") == ["digital_assets"]
    assert out_of_scope_items("single") == []


def test_out_of_scope_mention_is_flagged_and_not_saved():
    result = handle_answer({}, "I have rental income too", 1)
    assert result["intake"] == {}
    assert result["flags"][0]["type"] == "out_of_scope_mention"

def test_go_back_detection_and_previous_question():
    assert wants_to_go_back("Can we go back?")
    assert not wants_to_go_back("single")
    intake = {"filing_status": "single"}
    assert previous_question(intake, QUESTIONS[1])["field"] == "filing_status"
    assert previous_question({}, QUESTIONS[0]) is None


def test_go_back_reasks_previous_question_and_keeps_answers():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command

    builder = StateGraph(dict)
    builder.add_node("intake", run_interactive)
    builder.add_edge(START, "intake")
    builder.add_edge("intake", END)
    graph = builder.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t6"}}

    first = graph.invoke({"intake": {"filing_status": "single"}}, config)
    assert first["__interrupt__"][0].value["fields"] == ["intake.taxpayer.birth_date"]
    second = graph.invoke(Command(resume={"answer": "can we go back"}), config)
    payload = second["__interrupt__"][0].value
    assert payload["fields"] == ["intake.filing_status"]
    assert "Of course" in payload["question"]
    final = graph.invoke(Command(resume={"answer": "married"}), config)
    assert final["intake"]["filing_status"] == "mfj"

def test_rules_named_dependent_path_is_asked_and_saved():
    intake = {"dependents": [{"name": "Sam"}]}
    q = next_question(intake, ["intake.dependents.0.relationship"])
    assert field_path(q) == "intake.dependents.0.relationship"
    result = handle_answer({"intake": intake}, "grandson", 1, q)
    assert result["intake"]["dependents"][0] == {"name": "Sam", "relationship": "grandson"}
    ssn_q = dependent_question("intake.dependents.0.ssn")
    result = handle_answer(result, "901-55-1234", 2, ssn_q)
    assert result["intake"]["dependents"][0]["ssn"] == "901-55-1234"

def test_dependent_fields_are_asked_in_order():
    missing = [
        "intake.dependents.0.name",
        "intake.dependents.0.relationship",
        "intake.dependents.0.ssn",
    ]
    intake = {}
    asked = []
    for turn, answer in enumerate(["Sam", "grandson", "901-55-1234"], 1):
        q = next_question(intake, missing)
        asked.append(field_path(q))
        intake = handle_answer({"intake": intake}, answer, turn, q)["intake"]
    assert asked == missing
    assert intake["dependents"][0] == {
        "name": "Sam", "relationship": "grandson", "ssn": "901-55-1234"}
    assert next_question(intake, missing)["field"] == "filing_status"

def test_filing_status_understands_sentences_but_does_not_guess():
    assert parse_filing_status("I am married") == "mfj"
    assert parse_filing_status("Actually, I'm single.") == "single"
    assert parse_filing_status("married, filing separately") == "mfs"
    assert parse_filing_status("I am the head of household") == "hoh"
    assert parse_filing_status("I am not married") is None
    assert parse_filing_status("my husband passed away, I am a widow") is None
    assert parse_filing_status("I was single, now married") is None

def test_two_corrections_in_a_row_flag_but_change_nothing():
    state = {"intake": {}}
    q = next_question(state["intake"])
    state = handle_answer(state, "single", 1, q)
    q = next_question(state["intake"])
    assert q["field"] == "birth_date"
    state = handle_answer(state, "sorry, I meant married", 2, q)
    state = handle_answer(state, "sorry, I meant single", 3, q)
    assert state["intake"] == {"filing_status": "single"}
    assert [f["type"] for f in state["flags"]] == ["contradiction", "contradiction"]
    assert next_question(state["intake"])["field"] == "birth_date"

def test_empty_and_garbled_answers_are_uncertain_and_change_nothing():
    state = {"intake": {}}
    q = next_question(state["intake"])
    for turn, text in enumerate(["", "   ", "asdf qwerty ???"], 1):
        state = handle_answer(state, text, turn, q)
    assert state["intake"] == {}
    assert [f["type"] for f in state["flags"]] == ["uncertain_answer"] * 3
    assert next_question(state["intake"])["field"] == "filing_status"

def test_ssn_never_leaks_into_flags_when_mixed_with_other_content():
    q = next_question({})
    for turn, text in enumerate([
        "Should I take the standard deduction? My SSN is 901-55-1234",
        "I'm helping my mother, her number is 901551234",
        "sorry, I meant single, my ssn is 901-55-1234",
    ], 1):
        state = handle_answer({"intake": {}}, text, turn, q)
        assert state["flags"], text
        assert "901-55-1234" not in str(state), text
        assert "901551234" not in str(state), text