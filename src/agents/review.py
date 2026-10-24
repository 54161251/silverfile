"""Review / Audit agent (B6, workstream P6).

Tries to falsify the assembled draft before any person sees it. It never fixes anything: it
returns review_verdict "pass", or "revise" with findings naming the agent that should redo its
work. The orchestrator routes the first finding and bounds the loop (E9 review limit, E10 cycle).

Reads : lines, documents, user_inputs, intake, flags, eligibility, filing_status_validated,
        box_count_12d, scope, escalations
Writes: review_verdict, review_findings (only these, per B6 / R10)

Review does no arithmetic. Each total it re-checks is recomputed by calling the same
deterministic MCP tools as Computation, but from Review's own reading of the inputs, so a wrong
input, a stale line or a skipped step shows up as a disagreement. Comparisons such as
"6b <= 6a" are checks, not arithmetic.

Four groups of checks (see docs/P6_REVIEW.md):
  P  provenance: every required line has a complete record that matches the current state
  T  totals: each derived line agrees with an independent tool call
  R  rules and contradictions: 1040-SR eligibility, line 12d, relations such as 6b <= 6a
  S  scope and escalation: nothing out of scope or unescalated reached the draft

Each finding: {"check", "target_agent", "reason", "line"?, "evidence"?}. Findings are sorted so
the most upstream fix comes first (extraction, intake, rules, computation), because the
orchestrator acts on review_findings[0] and everything downstream reruns after it.
"""
import asyncio
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from src.agents.computation import ToolCallError, ToolClient

SENIOR_BIRTH_CUTOFF = date(1961, 1, 2)  # born before this: 1040-SR eligible and 65+ in 2025
STATUSES = {"single", "mfj", "mfs", "hoh", "qss"}
FORMS = {"W2": "W-2", "1099INT": "1099-INT", "1099DIV": "1099-DIV", "1099R": "1099-R", "SSA1099": "SSA-1099"}
REQUIRED_LINES = ("1a", "1z", "2a", "2b", "3a", "3b", "4a", "4b", "5a", "5b", "6a", "6b", "7", "8", "9",
                  "10", "11a", "12d", "12e", "13a", "13b", "14", "15", "16", "17", "18", "19", "20", "21",
                  "22", "23", "24", "25a", "25b", "25c", "25d", "26", "32", "33", "34", "37")
KINDS = {"extracted", "user_input", "computed", "default_zero", "human_resolution"}
NEGATIVE_ALLOWED = {"8", "11a"}  # Schedule 1 can be a loss; AGI is not floored
LOW_CONFIDENCE = 0.8  # a box below this must be listed as unverified (confirm with P4)
TARGET_ORDER = {"extraction": 0, "intake": 1, "rules": 2, "computation": 3}
SSN_PATTERN = re.compile(r"9\d{2}-?\d{2}-?\d{4}")
# Intake flag type -> escalation code Rules must have raised for it (mirrors rules.FLAG_RULES).
FLAG_CODES = {"out_of_scope_mention": "E1", "contradiction": "E2", "advice_request": "E4",
              "third_party_answering": "E6", "unknown_refund_account": "E6",
              "pressure_signal": "E6", "uncertain_answer": "E8"}
# Lines that must come from one particular tool when computed (checks the tool was really called).
TOOL_FOR_LINE = {"9": "sum_amounts", "11a": "subtract", "12e": "standard_deduction",
                 "13b": "senior_deduction", "14": "sum_amounts", "15": "subtract", "16": "income_tax",
                 "18": "sum_amounts", "22": "subtract", "24": "sum_amounts", "25d": "sum_amounts",
                 "33": "sum_amounts", "34": "subtract", "37": "subtract"}


class _Findings:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check: str, target: str, reason: str, line: str | None = None, evidence=None):
        item = {"check": check, "target_agent": target, "reason": reason}
        if line:
            item["line"] = line
        if evidence:
            item["evidence"] = evidence
        if item not in self.items:
            self.items.append(item)


# --- Small readers -------------------------------------------------------------------------

def _form(document: dict) -> str:
    raw = str(document.get("form", ""))
    return FORMS.get(re.sub(r"[^A-Z0-9]", "", raw.upper()), raw)


def _scalar(raw):
    return raw.get("value") if isinstance(raw, dict) else raw


def _box(document: dict, box: str, user_inputs: dict):
    """The box value Computation should have used: a taxpayer-confirmed value for unverified boxes."""
    if box in (document.get("unverified") or []):
        return _scalar(user_inputs.get(f"{document['doc_id']}.{box}"))
    return (document.get("boxes") or {}).get(box)


def _same(a, b) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return a == b


def _birth(person: dict | None):
    try:
        return date.fromisoformat(str((person or {}).get("birth_date")))
    except ValueError:
        return None


def _escalated(state: dict, code: str, ref: str, resolved_only: bool = True) -> bool:
    """True if Rules raised `code` with evidence `ref` (a "@hash" suffix is allowed)."""
    for record in state.get("escalations") or []:
        if record.get("code") != code or (resolved_only and record.get("status") != "resolved"):
            continue
        if any(item == ref or item.startswith(ref + "@") for item in record.get("evidence") or []):
            return True
    return False


def _ssn_values(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else key
            if key.lower().endswith("ssn") and item is not None:
                yield child, item
            yield from _ssn_values(item, child)
    elif isinstance(value, list):
        for position, item in enumerate(value):
            yield from _ssn_values(item, f"{path}[{position}]")


# --- S: scope and escalation ----------------------------------------------------------------

def _check_scope(state: dict, f: _Findings):
    if not (state.get("scope") or {}).get("in_scope"):
        f.add("S1", "rules", "The return is not cleared as in scope")
    for record in state.get("escalations") or []:
        if record.get("status") == "open":
            f.add("S2", "rules", f"Escalation {record.get('id')} ({record.get('code')}) is still open",
                  evidence=[record.get("id")])
    for document in state.get("documents") or []:
        ref, form, boxes = f"doc:{document.get('doc_id')}", _form(document), document.get("boxes") or {}
        if form not in FORMS.values() and not _escalated(state, "E1", ref):
            f.add("S3", "rules", f"Out-of-scope document {form} reached the draft without escalation",
                  evidence=[ref])
        if form == "1099-R":
            if (boxes.get("2b_not_determined") or "taxable_amount_not_determined" in (document.get("flags") or [])) \
                    and not _escalated(state, "E3", ref):
                f.add("S4", "rules", "1099-R with taxable amount not determined was not escalated", evidence=[ref])
            if str(boxes.get("7", "")).strip().upper() != "7" and not _escalated(state, "E1", ref):
                f.add("S5", "rules", "1099-R distribution code is not 7 and was not escalated", evidence=[ref])
        if form == "1099-DIV" and boxes.get("2a") and not _escalated(state, "E1", ref):
            f.add("S6", "rules", "1099-DIV capital gain distributions were not escalated", evidence=[ref])
    for item in (state.get("intake") or {}).get("out_of_scope_items") or []:
        ref = f"intake.out_of_scope_items.{item}"
        if not _escalated(state, "E1", ref):
            f.add("S7", "rules", f"Out-of-scope item '{item}' was not escalated", evidence=[ref])
    for flag in state.get("flags") or []:
        code = FLAG_CODES.get(flag.get("type"))
        if code and not _escalated(state, code, flag.get("id", ""), resolved_only=False):
            f.add("S8", "rules", f"Intake flag {flag.get('id')} ({flag.get('type')}) has no {code} escalation",
                  evidence=[flag.get("id")])
    for source in ("intake", "user_inputs"):
        for path, ssn in _ssn_values(state.get(source) or {}, source):
            if not isinstance(ssn, str) or not SSN_PATTERN.fullmatch(ssn):
                f.add("S9", "intake", f"{path} is not a 900-series test SSN", evidence=[path])


# --- P: provenance --------------------------------------------------------------------------

def _check_provenance(state: dict, f: _Findings) -> bool:
    """Returns True when every required line is present and well formed, so totals can be checked."""
    lines = state.get("lines") or {}
    if not lines:
        f.add("P1", "computation", "The draft has no lines")
        return False
    complete = True
    for line in REQUIRED_LINES:
        if line not in lines:
            f.add("P1", "computation", f"Line {line} is missing from the draft", line)
            complete = False
    documents = {d.get("doc_id"): d for d in state.get("documents") or []}
    user_inputs = state.get("user_inputs") or {}
    for key, record in lines.items():
        value, kind = record.get("value"), record.get("kind")
        if record.get("line") != key or not isinstance(value, int) or isinstance(value, bool):
            f.add("P2", "computation", f"Line {key} has a malformed record", key)
            complete = False
            continue
        if value < 0 and key not in NEGATIVE_ALLOWED:
            f.add("P2", "computation", f"Line {key} is negative ({value})", key)
        if kind not in KINDS:
            f.add("P3", "computation", f"Line {key} has unknown provenance kind {kind!r}", key)
        if kind == "computed" and not (record.get("tool") and record.get("inputs") and record.get("formula")):
            f.add("P3", "computation", f"Line {key} is computed but lacks tool, inputs or formula", key)
        if kind in {"user_input", "human_resolution"} and not (record.get("entered_by") and record.get("timestamp")):
            f.add("P3", "computation", f"Line {key} is a direct input without who entered it and when", key)
        if kind == "default_zero" and value != 0:
            f.add("P3", "computation", f"Line {key} is marked default zero but holds {value}", key)
        expected_tool = TOOL_FOR_LINE.get(key)
        if kind == "computed" and expected_tool and (record.get("tool") or {}).get("name") != expected_tool:
            f.add("P5", "computation", f"Line {key} was not produced by the {expected_tool} tool", key)
        for source in record.get("sources") or []:
            if "doc_id" in source:
                document = documents.get(source["doc_id"])
                if document is None:
                    f.add("P4", "computation", f"Line {key} cites document {source['doc_id']}, which is not in "
                          "the return", key, [source["doc_id"]])
                elif not _same(_box(document, source.get("box"), user_inputs), source.get("value")):
                    f.add("P4", "computation", f"Line {key} used {source.get('value')} from {source['doc_id']} "
                          f"box {source.get('box')}, which no longer matches the document", key, [source["doc_id"]])
            if source.get("user_inputs") == key and kind == "user_input":
                raw = _scalar(user_inputs.get(key))
                if isinstance(raw, int) and not isinstance(raw, bool) and raw != value:
                    f.add("P4", "computation", f"Line {key} shows {value} but the taxpayer entered {raw}", key)
        if kind == "computed" and key != "4b":  # 4b's minuend is box 2a, labelled with line 4a
            for item in record.get("inputs") or []:
                ref = item.get("line")
                if ref in lines and ref != key and not _same(item.get("value"), lines[ref].get("value")):
                    f.add("P6", "computation", f"Line {key} used {item.get('value')} for line {ref}, but line {ref} "
                          f"is now {lines[ref].get('value')} (stale)", key)
    for document in documents.values():
        for box, score in (document.get("confidence") or {}).items():
            if score < LOW_CONFIDENCE and box not in (document.get("unverified") or []):
                f.add("P7", "extraction", f"{document['doc_id']} box {box} has confidence {score} but is not "
                      "marked unverified", evidence=[document["doc_id"]])
    return complete


# --- R and T: rules, contradictions, totals (tool calls) -----------------------------------

async def _check_rules(state: dict, call, f: _Findings):
    intake, eligibility = state.get("intake") or {}, state.get("eligibility") or {}
    status, lines = state.get("filing_status_validated"), state.get("lines") or {}
    if status not in STATUSES:
        f.add("R1", "rules", f"Filing status {status!r} is not a validated status")
        return
    if eligibility.get("form_1040sr_eligible") is not True:
        f.add("R2", "rules", "Rules has not confirmed 1040-SR eligibility")
    taxpayer, spouse = intake.get("taxpayer") or {}, intake.get("spouse") or {}
    tp_born, sp_born = _birth(taxpayer), _birth(spouse)
    tp_senior = tp_born < SENIOR_BIRTH_CUTOFF if tp_born else bool(eligibility.get("taxpayer_65_or_older"))
    sp_senior = sp_born < SENIOR_BIRTH_CUTOFF if sp_born else bool(eligibility.get("spouse_65_or_older"))
    joint = status == "mfj"
    if tp_born and tp_senior != bool(eligibility.get("taxpayer_65_or_older")):
        f.add("R3", "rules", "Taxpayer 65-or-older status does not match the birth date", "12d")
    if sp_born and joint and sp_senior != bool(eligibility.get("spouse_65_or_older")):
        f.add("R3", "rules", "Spouse 65-or-older status does not match the birth date", "12d")
    if (tp_born or sp_born) and not (tp_senior or (joint and sp_senior)):
        f.add("R2", "rules", "Nobody on the return was born before 2 January 1961, so 1040-SR does not apply")
    qualifiers = set(eligibility.get("senior_deduction_qualifiers") or [])
    if ("taxpayer" in qualifiers and not tp_senior) or ("spouse" in qualifiers and not (joint and sp_senior)):
        f.add("R4", "rules", "Senior deduction lists a person who is not 65 or older on this return", "13b")
    try:
        counted = await call("count_12d_boxes", filing_status=status, taxpayer_65=tp_senior,
                             taxpayer_blind=bool(taxpayer.get("blind")), spouse_65=joint and sp_senior,
                             spouse_blind=joint and bool(spouse.get("blind")))
    except ToolCallError as exc:
        f.add("R5", "rules", f"Line 12d could not be recounted: {exc}", "12d")
    else:
        if counted["value"] != state.get("box_count_12d"):
            f.add("R5", "rules", f"Rules reported {state.get('box_count_12d')} boxes on line 12d; an independent "
                  f"count gives {counted['value']} ({counted['formula']})", "12d")
        if "12d" in lines and counted["value"] != lines["12d"].get("value"):
            f.add("R5", "computation", f"Line 12d is {lines['12d'].get('value')}; an independent count gives "
                  f"{counted['value']}", "12d")
    chart_blockers = {"can_be_claimed_as_dependent": "the taxpayer can be claimed as a dependent",
                      "dual_status_alien": "the taxpayer was a dual-status alien"}
    if status == "mfs":
        chart_blockers["mfs_spouse_itemizes"] = "the separately filing spouse itemizes"
    for key, reason in chart_blockers.items():
        if intake.get(key) and not _escalated(state, "E7", f"intake.{key}"):
            f.add("R6", "rules", f"The standard deduction chart does not apply: {reason}", "12e")
    value = {key: record.get("value") for key, record in lines.items()}
    pairs = [("4b", "4a", "extraction"), ("5b", "5a", "extraction"), ("3a", "3b", "extraction"),
             ("6b", "6a", "computation")]
    for part, whole, target in pairs:
        if part in value and whole in value and value[part] > value[whole]:
            f.add("R7", target, f"Line {part} ({value[part]}) is larger than line {whole} ({value[whole]})", part)
    for line in ("7", "13a"):
        if value.get(line):
            f.add("R8", "rules", f"Line {line} has a value but is out of scope", line)
    if value.get("34", 0) > 0 and value.get("37", 0) > 0:
        f.add("R9", "computation", "Both a refund (line 34) and an amount owed (line 37) are shown", "34")


async def _check_totals(state: dict, call, f: _Findings):
    lines, status = state["lines"], state.get("filing_status_validated")
    user_inputs, documents = state.get("user_inputs") or {}, state.get("documents") or []
    value = {key: record["value"] for key, record in lines.items()}

    def items(*names):
        return [{"label": f"line {n}", "line": n, "value": value[n]} for n in names if n in value]

    def boxes(spec):
        out = []
        for document in sorted(documents, key=lambda d: d.get("doc_id", "")):
            for box in spec.get(_form(document), ()):
                raw = _box(document, box, user_inputs)
                if raw not in (None, ""):
                    out.append({"label": f"{document['doc_id']} box {box}", "value": raw})
        return out

    async def expect(line, tool, check="T1", **arguments):
        try:
            result = await call(tool, **arguments)
        except ToolCallError as exc:
            f.add("T0", "computation", f"Line {line} could not be rechecked: {exc}", line)
            return None
        if result["value"] != value[line]:
            f.add(check, "computation", f"Line {line} is {value[line]}; an independent {tool} call gives "
                  f"{result['value']} ({result['formula']})", line)
        return result

    # Lines read straight from documents, recomputed from the documents themselves
    from_documents = {"1a": {"W-2": ("1",)}, "2a": {"1099-INT": ("8",)}, "2b": {"1099-INT": ("1", "3")},
                      "3a": {"1099-DIV": ("1b",)}, "3b": {"1099-DIV": ("1a",)}, "6a": {"SSA-1099": ("5",)},
                      "25a": {"W-2": ("2",)},
                      "25b": {"1099-INT": ("4",), "1099-DIV": ("4",), "1099-R": ("4",), "SSA-1099": ("6",)}}
    for line, spec in from_documents.items():
        await expect(line, "sum_amounts", "T2", items=boxes(spec))
    try:  # 4a + 5a must account for every 1099-R box 1 (IRA vs pension split is Computation's call)
        shown = await call("sum_amounts", items=items("4a", "5a"))
        documented = await call("sum_amounts", items=boxes({"1099-R": ("1",)}))
    except ToolCallError as exc:
        f.add("T0", "computation", f"Lines 4a and 5a could not be rechecked: {exc}", "4a")
    else:
        if shown["value"] != documented["value"]:
            f.add("T2", "computation", f"Lines 4a + 5a total {shown['value']} but the 1099-R forms show "
                  f"{documented['value']} in box 1", "4a")

    # Totals in dependency order
    await expect("1z", "sum_amounts", items=items("1a", "1b", "1c", "1d", "1e", "1f", "1g", "1h"))
    if value["6a"] == 0:
        if value["6b"] != 0:
            f.add("T1", "computation", "Line 6b is not 0 although there are no Social Security benefits", "6b")
    else:
        other = await expect_total(call, f, items("1z", "2b", "3b", "4b", "5b", "7", "8"))
        if other is not None:
            await expect("6b", "taxable_social_security", filing_status=status, benefits=value["6a"],
                         other_income=other, tax_exempt_interest=value["2a"], adjustments=value["10"],
                         mfs_lived_with_spouse=bool((state.get("intake") or {}).get("mfs_lived_with_spouse")))
    await expect("9", "sum_amounts", items=items("1z", "2b", "3b", "4b", "5b", "6b", "7", "8"))
    await expect("11a", "subtract", minuend=value["9"], subtrahend=value["10"], floor_zero=False)
    if status in STATUSES:
        qualifiers = len(set((state.get("eligibility") or {}).get("senior_deduction_qualifiers") or []))
        await expect("12e", "standard_deduction", filing_status=status, box_count=value["12d"])
        await expect("13b", "senior_deduction", filing_status=status, agi=value["11a"], qualifier_count=qualifiers)
    await expect("14", "sum_amounts", items=items("12e", "13a", "13b"))
    await expect("15", "subtract", minuend=value["11a"], subtrahend=value["14"], floor_zero=True)
    if status in STATUSES:
        await expect("16", "income_tax", filing_status=status, taxable_income=value["15"])
    await expect("18", "sum_amounts", items=items("16", "17"))
    if lines["21"].get("kind") == "computed":
        await expect("21", "sum_amounts", items=items("19", "20"))
    await expect("22", "subtract", minuend=value["18"], subtrahend=value["21"], floor_zero=True)
    await expect("24", "sum_amounts", items=items("22", "23"))
    await expect("25d", "sum_amounts", items=items("25a", "25b", "25c"))
    if lines["32"].get("kind") == "computed":
        await expect("32", "sum_amounts", items=items("27", "28", "29", "30", "31"))
    await expect("33", "sum_amounts", items=items("25d", "26", "32"))
    await expect("34", "subtract", minuend=value["33"], subtrahend=value["24"], floor_zero=True)
    await expect("37", "subtract", minuend=value["24"], subtrahend=value["33"], floor_zero=True)


async def expect_total(call, f: _Findings, items: list[dict]):
    try:
        return (await call("sum_amounts", items=items))["value"]
    except ToolCallError as exc:
        f.add("T0", "computation", f"Other income for line 6b could not be rechecked: {exc}", "6b")
        return None


async def _audit(state: dict, call, f: _Findings, totals: bool):
    await _check_rules(state, call, f)
    if totals:
        await _check_totals(state, call, f)


def _run_sync(coroutine):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coroutine).result()


# --- Entry points ---------------------------------------------------------------------------

def review_return(state: dict, *, client: ToolClient | None = None) -> dict:
    """Audit the draft. Returns {"review_verdict": "pass"|"revise", "review_findings": [...]}."""
    f = _Findings()
    _check_scope(state, f)
    complete = _check_provenance(state, f)
    _run_sync(_audit(state, (client or ToolClient()).call, f, totals=complete))
    findings = sorted(f.items, key=lambda item: TARGET_ORDER[item["target_agent"]])
    return {"review_verdict": "revise" if findings else "pass", "review_findings": findings}


def run(state: dict) -> dict:
    """Entry point used by the graph (R10)."""
    return review_return(state)


def main(argv: list[str] | None = None) -> int:
    """Compute and then review a state file: python -m src.agents.review tests/golden/g01_single_ss_50pct.json"""
    from src.agents.computation import compute_return
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m src.agents.review <state.json>  (a golden file's \"state\" key is used)")
        return 2
    with open(args[0], encoding="utf-8") as handle:
        data = json.load(handle)
    state = data.get("state", data)
    state.setdefault("escalations", [])
    if not state.get("lines"):
        computed = compute_return(state)
        if computed["open_questions"]:
            print("Computation is blocked:", *computed["open_questions"], sep="\n  - ")
            return 1
        state["lines"] = computed["lines"]
    result = review_return(state)
    print(f"verdict: {result['review_verdict']}")
    for finding in result["review_findings"]:
        print(f"  [{finding['check']}] -> {finding['target_agent']}: {finding['reason']}")
    return 0 if result["review_verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
