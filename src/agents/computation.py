"""Computation agent (B5, workstream P2).

Populates every derived line of the Form 1040-SR draft. It does no arithmetic itself: each
dollar amount comes from a deterministic MCP tool call (src/tools/mcp_server.py), and each
line carries a Provenance record (data contract #1) saying where the number came from.

Reads : intake, user_inputs, documents, eligibility, filing_status_validated, box_count_12d, scope
Writes: lines, open_questions (only these, per B5 / R10)

On success it returns {"lines": {...}, "open_questions": []}. The empty list matters: the
orchestrator routes back to Intake whenever open_questions is non-empty.
If anything it needs is missing or inconsistent it returns {"lines": {}, "open_questions": [...]}
and no partial return. Each entry is a dotted state path, optionally followed by ": reason".
Repeated blocking ends in the orchestrator's loop guard (E10), which escalates to staff.

Line order follows the dependency order in docs/P2_COMPUTATION.md. Line 6b needs every other
income line, and lines 12e/13b need the filing status, the 12d box count and AGI (11a).

Interface conventions and open items for other workstreams: docs/P2_COMPUTATION.md.
"""
import asyncio
import json
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.tools.mcp_server import build_server
from src.tools.tax_math import TaxMathError, to_decimal

CITE_DOCUMENTS = "policy.md#in-scope-documents"
CITE_DIVIDENDS = "policy.md#dividends"
CITE_1099R = "policy.md#1099-r-distributions"
CITE_SOCIAL_SECURITY = "policy.md#social-security-exclusions"
CITE_SCHEDULES = "policy.md#schedules"
CITE_SENIOR = "policy.md#senior-deduction"

# Direct-input lines that must be present in user_inputs. Empty means every direct line defaults
# to a zero with kind "default_zero" when the taxpayer gave no value, and the dashboard shows it.
# Put "10" and "26" here if the team prefers to block until Intake asks for them explicitly.
REQUIRED_DIRECT_LINES: tuple[str, ...] = ()

# Lines the taxpayer types in (Schedules 1-3 totals, other wages, credits, payments). Lines 21 and
# 32 are handled separately because they can also be computed from their parts.
DIRECT_LINES = ("8", "10", "17", "19", "20", "23", "25c", "26")
OPTIONAL_WAGE_LINES = ("1b", "1c", "1d", "1e", "1f", "1g", "1h")
PAYMENT_COMPONENTS = ("27", "28", "29", "30", "31")
MAY_BE_NEGATIVE = {"8"}  # Schedule 1 line 10 can be a loss

FORMS = {"W2": "W-2", "1099INT": "1099-INT", "1099DIV": "1099-DIV", "1099R": "1099-R", "SSA1099": "SSA-1099"}


class ToolCallError(RuntimeError):
    """An MCP tool call failed (bad input, out-of-scope case or server fault)."""


# --- Calling the MCP server -----------------------------------------------------------

class ToolClient:
    """Calls the SilverFile tax MCP server in-process. Same server as `python -m src.tools.mcp_server`."""

    def __init__(self, server=None):
        self.server = server or build_server()

    async def call(self, name: str, **arguments: Any) -> dict:
        try:
            result = await self.server.call_tool(name, arguments)
        except Exception as exc:  # the SDK wraps tool errors; the message names the cause
            raise ToolCallError(f"{name}: {exc}") from exc
        if getattr(result, "is_error", False) or getattr(result, "isError", False):
            raise ToolCallError(f"{name}: {_text(result)}")
        data = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
        if data is None:
            data = json.loads(_text(result))
        if set(data) == {"result"} and isinstance(data["result"], dict):  # SDKs that wrap plain returns
            data = data["result"]
        return data


def _text(result) -> str:
    return " ".join(getattr(block, "text", "") for block in getattr(result, "content", []))


def _run_sync(coroutine):
    """Run a coroutine from sync code, even if the caller already has a running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coroutine).result()


# --- Reading inputs -------------------------------------------------------------------

class _Bucket:
    """Amounts (and where each came from) that feed one line."""

    def __init__(self):
        self.items: list[dict] = []
        self.sources: list[dict] = []

    def add(self, label: str, amount, source: dict, line: str | None = None):
        item = {"label": label, "value": float(amount)}
        if line:
            item["line"] = line
        self.items.append(item)
        self.sources.append(source)


def _scalar(raw: Any) -> Any:
    return raw.get("value") if isinstance(raw, dict) else raw


def _form(document: dict) -> str | None:
    return FORMS.get(re.sub(r"[^A-Z0-9]", "", str(document.get("form", "")).upper()))


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "x", "checked"}
    return bool(value)


def _read_box(document: dict, box: str, required: bool, user_inputs: dict, missing: list):
    """Return (amount, source) for one box, or None. Adds to `missing` when it cannot be used.

    A value in user_inputs["<doc_id>.<box>"] (taxpayer confirmation or staff resolution) replaces
    the printed box. Without one, a box in the document's `unverified` list (low OCR confidence)
    is not used, and neither is 1099-R box 2a when box 2b "taxable amount not determined" is
    checked: a preparer must enter that amount (E3).
    """
    doc_id = document["doc_id"]
    path = f"documents.{doc_id}.boxes.{box}"
    boxes = document.get("boxes") or {}
    raw = boxes.get(box)
    confirmed = False
    override = user_inputs.get(f"{doc_id}.{box}")
    if override is not None:
        raw, confirmed = _scalar(override), True
    elif box in (document.get("unverified") or []):
        missing.append(f"{path}: low-confidence value needs the taxpayer to confirm it")
        return None
    elif box == "2a" and _form(document) == "1099-R" and _truthy(boxes.get("2b_not_determined")):
        missing.append(f"{path}: taxable amount not determined; a preparer must enter it (E3)")
        return None
    if raw is None or raw == "":
        if required:
            missing.append(f"{path}: required box is blank")
        return None
    try:
        amount = to_decimal(raw, path)
    except TaxMathError as exc:
        missing.append(f"{path}: {exc}")
        return None
    if amount < 0:
        missing.append(f"{path}: amount cannot be negative")
        return None
    source = {"doc_id": doc_id, "form": document["form"], "box": box, "value": float(amount) if amount % 1 else int(amount)}
    if confirmed:
        kind = override.get("kind") if isinstance(override, dict) else None
        source["confirmed_by"] = "staff (human_resolution)" if kind == "human_resolution" else "user_input"
        if isinstance(override, dict) and override.get("entered_by"):
            source["entered_by"] = override["entered_by"]
    return amount, source


def _gather(documents: list, user_inputs: dict, missing: list) -> dict[str, _Bucket]:
    buckets: dict[str, _Bucket] = defaultdict(_Bucket)

    def take(bucket: str, document: dict, box: str, required: bool = False, line: str | None = None):
        found = _read_box(document, box, required, user_inputs, missing)
        if found:
            amount, source = found
            label = f"{source['form']} {document['doc_id']} box {box}"
            buckets[bucket].add(label, amount, source, line)

    for document in sorted(documents, key=lambda d: d["doc_id"]):
        form = _form(document)
        if form == "W-2":
            take("1a", document, "1", required=True)
            take("25a", document, "2")
        elif form == "1099-INT":
            take("2b", document, "1", required=True)
            take("2b", document, "3")
            take("2a", document, "8")
            take("25b", document, "4")
        elif form == "1099-DIV":
            take("3b", document, "1a", required=True)
            take("3a", document, "1b")
            take("25b", document, "4")
        elif form == "1099-R":
            if _truthy((document.get("boxes") or {}).get("ira_sep_simple")):
                take("4a", document, "1", required=True)
                take("4b_gross", document, "2a", required=True)
                take("qcd", document, "qcd_amount")
            else:
                take("5a", document, "1", required=True)
                take("5b", document, "2a", required=True)
            take("25b", document, "4")
        elif form == "SSA-1099":
            take("6a", document, "5", required=True)
            take("25b", document, "6")
        # Any other form is Rules' job to escalate (E1); it is not summed here.
    return buckets


def _direct_input(line: str, user_inputs: dict, now: str, missing: list, *, optional: bool = False):
    """Provenance for a line the taxpayer types in: user_input, default_zero, or None (optional and absent)."""
    raw = user_inputs.get(line)
    if raw is None:
        if line in REQUIRED_DIRECT_LINES:
            missing.append(f"user_inputs.{line}: ask the taxpayer (enter 0 if none)")
            return None
        if optional:
            return None
        return _record(line, 0, "default_zero", now, formula="no amount given, entered as 0",
                       citation=CITE_SCHEDULES)
    try:
        amount = to_decimal(_scalar(raw), f"user_inputs.{line}")
    except TaxMathError as exc:
        missing.append(f"user_inputs.{line}: {exc}")
        return None
    if amount < 0 and line not in MAY_BE_NEGATIVE:
        missing.append(f"user_inputs.{line}: amount cannot be negative")
        return None
    # Kept unrounded here; _compute rounds cents through the sum_amounts tool (A23, R9).
    value = int(amount) if amount == amount.to_integral_value() else float(amount)
    if isinstance(raw, dict):  # Intake or staff supplied a full provenance record: keep its audit fields
        record = {key: raw[key] for key in ("kind", "formula", "inputs", "sources", "tool", "citation",
                                            "entered_by", "timestamp") if key in raw}
        record.update(line=line, value=value)
        record.setdefault("kind", "user_input")
        record.setdefault("entered_by", "taxpayer (intake)")
        record.setdefault("timestamp", now)
        record.setdefault("citation", CITE_SCHEDULES)
        for key, default in (("formula", None), ("inputs", []), ("sources", [{"user_inputs": line}]), ("tool", None)):
            record.setdefault(key, default)
        return record
    record = _record(line, 0, "user_input", now, sources=[{"user_inputs": line}],
                     entered_by="taxpayer (intake)", citation=CITE_SCHEDULES)
    record["value"] = value
    return record


def _record(line: str, value: int, kind: str, now: str, *, formula=None, inputs=None, sources=None,
            tool=None, citation=None, entered_by=None) -> dict:
    return {"line": line, "value": int(value), "kind": kind, "formula": formula, "inputs": inputs or [],
            "sources": sources or [], "tool": tool, "citation": citation, "entered_by": entered_by,
            "timestamp": now}


def _timestamp() -> str:
    try:
        return datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds")
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone().isoformat(timespec="seconds")


# --- The calculation ------------------------------------------------------------------

async def _compute(state: dict, call, now: str) -> tuple[dict, list]:
    intake = state.get("intake") or {}
    user_inputs = state.get("user_inputs") or {}
    eligibility = state.get("eligibility") or {}
    status = state.get("filing_status_validated")
    missing: list[str] = []

    # Prerequisites owned by other agents. Blocking here is a routing bug, so say what is absent.
    if not status:
        missing.append("intake.filing_status: no validated filing status yet")
    if not (state.get("scope") or {}).get("in_scope"):
        missing.append("scope.in_scope: Rules has not cleared the return as in scope")
    if "taxpayer_65_or_older" not in eligibility or "senior_deduction_qualifiers" not in eligibility:
        missing.append("eligibility: Rules output (taxpayer_65_or_older, senior_deduction_qualifiers) is missing")
    if not isinstance(state.get("box_count_12d"), int) or isinstance(state.get("box_count_12d"), bool):
        missing.append("box_count_12d: Rules has not supplied the line 12d count")

    buckets = _gather(state.get("documents") or [], user_inputs, missing)
    direct = {line: _direct_input(line, user_inputs, now, missing) for line in DIRECT_LINES}
    wages_extra = {line: _direct_input(line, user_inputs, now, missing, optional=True) for line in OPTIONAL_WAGE_LINES}
    direct_21 = _direct_input("21", user_inputs, now, missing, optional=True)
    direct_32 = _direct_input("32", user_inputs, now, missing, optional=True)
    payment_parts = {line: _direct_input(line, user_inputs, now, missing, optional=True) for line in PAYMENT_COMPONENTS}
    if missing:
        return {}, missing

    # A23: a direct input with cents is rounded by the sum_amounts tool, not here (R9).
    for record in [*direct.values(), *wages_extra.values(), direct_21, direct_32, *payment_parts.values()]:
        if record and isinstance(record["value"], float):
            result = await call("sum_amounts", items=[{"label": f"line {record['line']} as entered",
                                                       "value": record["value"]}])
            record.update(value=result["value"], formula=result["formula"], tool=result["tool"])

    lines: dict[str, dict] = {}

    def put(record: dict) -> int:
        lines[record["line"]] = record
        return record["value"]

    async def tool_line(line: str, name: str, *, sources=None, citation=None, **arguments) -> int:
        result = await call(name, **arguments)
        formula = result["formula"]
        if "unrounded" in result:
            formula += f"  [{result['unrounded']} before rounding]"
        return put(_record(line, result["value"], "computed", now, formula=formula, inputs=result["inputs"],
                           sources=sources, tool=result["tool"], citation=citation or result.get("citation")))

    async def from_documents(line: str, bucket: str, description: str, citation: str, **extra) -> int:
        found = buckets.get(bucket)
        if not found or not found.items:
            return put(_record(line, 0, "default_zero", now, formula=f"no {description} provided",
                               citation=citation))
        return await tool_line(line, "sum_amounts", items=found.items, sources=found.sources,
                               citation=citation)

    def total_of(*names: str) -> list[dict]:
        return [{"label": f"line {n}", "line": n, "value": lines[n]["value"]} for n in names]

    # 1. Income from documents and direct inputs (no dependencies)
    wages = [{"label": "line 1a (W-2 wages)", "line": "1a", "value": await from_documents(
        "1a", "1a", "W-2", CITE_DOCUMENTS)}]
    for line, record in wages_extra.items():
        if record:
            wages.append({"label": f"line {line}", "line": line, "value": put(record)})
    await tool_line("1z", "sum_amounts", items=wages)
    await from_documents("2a", "2a", "tax-exempt interest", CITE_DOCUMENTS)
    await from_documents("2b", "2b", "1099-INT", CITE_DOCUMENTS)
    await from_documents("3a", "3a", "qualified dividends", CITE_DIVIDENDS)
    await from_documents("3b", "3b", "1099-DIV", CITE_DIVIDENDS)
    await from_documents("4a", "4a", "IRA distributions", CITE_1099R)
    gross, qcd = buckets.get("4b_gross"), buckets.get("qcd")
    if qcd and qcd.items and gross and gross.items:
        gross_total = (await call("sum_amounts", items=gross.items))["value"]
        qcd_total = (await call("sum_amounts", items=qcd.items))["value"]
        await tool_line("4b", "subtract", minuend=gross_total, subtrahend=qcd_total, floor_zero=True,
                        minuend_label="taxable IRA distributions (1099-R box 2a)", minuend_line="4a",
                        subtrahend_label="qualified charitable distributions (QCD)",
                        sources=gross.sources + qcd.sources, citation=CITE_1099R)
    else:
        await from_documents("4b", "4b_gross", "IRA distributions", CITE_1099R)
    await from_documents("5a", "5a", "pension or annuity", CITE_1099R)
    await from_documents("5b", "5b", "pension or annuity", CITE_1099R)
    await from_documents("6a", "6a", "SSA-1099", CITE_SOCIAL_SECURITY)
    put(_record("7", 0, "default_zero", now, formula="capital gains are out of scope (entered as 0)",
                citation="policy.md#out-of-scope"))
    put(direct["8"])
    put(direct["10"])

    # 2. Line 6b needs every other income line and the adjustments (line 10)
    other_income = (await call("sum_amounts", items=total_of("1z", "2b", "3b", "4b", "5b", "7", "8")))["value"]
    if lines["6a"]["value"] == 0:
        put(_record("6b", 0, "default_zero", now, formula="no Social Security benefits",
                    citation=CITE_SOCIAL_SECURITY))
    else:
        mfs_apart = bool(intake.get("mfs_lived_with_spouse"))
        await tool_line("6b", "taxable_social_security", filing_status=status, benefits=lines["6a"]["value"],
                        other_income=other_income, tax_exempt_interest=lines["2a"]["value"],
                        adjustments=lines["10"]["value"], mfs_lived_with_spouse=mfs_apart,
                        sources=buckets["6a"].sources)
    # (other_income above is passed to the tool as a total; the line items are in lines 1z..8.)

    # 3. Totals: income, AGI
    await tool_line("9", "sum_amounts", items=total_of("1z", "2b", "3b", "4b", "5b", "6b", "7", "8"))
    await tool_line("11a", "subtract", minuend=lines["9"]["value"], subtrahend=lines["10"]["value"],
                    floor_zero=False, minuend_label="line 9 (total income)", minuend_line="9",
                    subtrahend_label="line 10 (adjustments to income)", subtrahend_line="10")
    agi = lines["11a"]["value"]

    # 4. Deductions
    taxpayer = intake.get("taxpayer") or {}
    spouse = intake.get("spouse") or {}
    joint = status == "mfj"
    count_result = await call(
        "count_12d_boxes", filing_status=status, taxpayer_65=bool(eligibility["taxpayer_65_or_older"]),
        taxpayer_blind=bool(taxpayer.get("blind")),
        spouse_65=bool(eligibility.get("spouse_65_or_older")) if joint else False,
        spouse_blind=bool(spouse.get("blind")) if joint else False)
    if count_result["value"] != state["box_count_12d"]:
        return {}, [f"box_count_12d: Rules reported {state['box_count_12d']} but the 12d tool counted "
                    f"{count_result['value']}; the two must agree before the return is computed"]
    put(_record("12d", count_result["value"], "computed", now, formula=count_result["formula"],
                inputs=count_result["inputs"], tool=count_result["tool"], citation=count_result["citation"]))
    box_count = lines["12d"]["value"]
    await tool_line("12e", "standard_deduction", filing_status=status, box_count=box_count)
    put(_record("13a", 0, "default_zero", now, formula="qualified business income deduction is out of scope",
                citation="policy.md#out-of-scope"))
    qualifiers = sorted(set(eligibility["senior_deduction_qualifiers"]))
    await tool_line("13b", "senior_deduction", filing_status=status, agi=agi, qualifier_count=len(qualifiers),
                    citation=CITE_SENIOR)
    await tool_line("14", "sum_amounts", items=total_of("12e", "13a", "13b"))
    await tool_line("15", "subtract", minuend=agi, subtrahend=lines["14"]["value"], floor_zero=True,
                    minuend_label="line 11a (AGI)", minuend_line="11a",
                    subtrahend_label="line 14 (total deductions)", subtrahend_line="14")

    # 5. Tax
    await tool_line("16", "income_tax", filing_status=status, taxable_income=lines["15"]["value"])
    put(direct["17"])
    await tool_line("18", "sum_amounts", items=total_of("16", "17"))
    put(direct["19"])
    put(direct["20"])
    if direct_21:
        put(direct_21)
    else:
        await tool_line("21", "sum_amounts", items=total_of("19", "20"))
    await tool_line("22", "subtract", minuend=lines["18"]["value"], subtrahend=lines["21"]["value"],
                    floor_zero=True, minuend_label="line 18", minuend_line="18",
                    subtrahend_label="line 21", subtrahend_line="21")
    put(direct["23"])
    await tool_line("24", "sum_amounts", items=total_of("22", "23"))

    # 6. Payments
    await from_documents("25a", "25a", "W-2 withholding", CITE_DOCUMENTS)
    await from_documents("25b", "25b", "1099 or SSA-1099 withholding", CITE_DOCUMENTS)
    put(direct["25c"])
    await tool_line("25d", "sum_amounts", items=total_of("25a", "25b", "25c"))
    put(direct["26"])
    parts = [put(record) for record in payment_parts.values() if record]
    if direct_32:
        put(direct_32)
    elif parts:
        await tool_line("32", "sum_amounts", items=[
            {"label": f"line {n}", "line": n, "value": lines[n]["value"]} for n in PAYMENT_COMPONENTS if n in lines])
    else:
        put(_record("32", 0, "default_zero", now, formula="no other payments or refundable credits given",
                    citation=CITE_SCHEDULES))
    await tool_line("33", "sum_amounts", items=total_of("25d", "26", "32"))

    # 7. Refund or amount owed
    await tool_line("34", "subtract", minuend=lines["33"]["value"], subtrahend=lines["24"]["value"],
                    floor_zero=True, minuend_label="line 33 (total payments)", minuend_line="33",
                    subtrahend_label="line 24 (total tax)", subtrahend_line="24")
    await tool_line("37", "subtract", minuend=lines["24"]["value"], subtrahend=lines["33"]["value"],
                    floor_zero=True, minuend_label="line 24 (total tax)", minuend_line="24",
                    subtrahend_label="line 33 (total payments)", subtrahend_line="33")
    return lines, []


def compute_return(state: dict, *, now: str | None = None, client: ToolClient | None = None) -> dict:
    """Compute the return. Returns {"lines": {...}, "open_questions": [...]}; never raises on bad input."""
    client = client or ToolClient()
    stamp = now or _timestamp()
    try:
        lines, open_questions = _run_sync(_compute(state, client.call, stamp))
    except ToolCallError as exc:
        return {"lines": {}, "open_questions": [f"computation.{exc}"]}
    return {"lines": lines, "open_questions": open_questions}


def run(state: dict) -> dict:
    """Entry point used by the graph (R10)."""
    return compute_return(state)


def main(argv: list[str] | None = None) -> int:
    """Print the computed lines for a state JSON file: python -m src.agents.computation case.json"""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m src.agents.computation <state.json>  (a golden file's \"state\" key is used)")
        return 2
    with open(args[0], encoding="utf-8") as handle:
        data = json.load(handle)
    output = compute_return(data.get("state", data))
    if output["open_questions"]:
        print("Blocked. Open questions:")
        for question in output["open_questions"]:
            print(f"  - {question}")
        return 1
    for line, record in output["lines"].items():
        print(f"{line:>4}  {record['value']:>10,}  {record['kind']:<13} {record['formula'] or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
