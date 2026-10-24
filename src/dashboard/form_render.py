"""Draft Form 1040-SR as HTML, with provenance on hover and on click (spec §4.2, D7).

Every dollar line shows its value; hovering shows a one-line summary of where it came from,
and clicking opens the full Provenance record (contract #1): kind, formula, inputs (linked to
the lines they came from), source documents and boxes, MCP tool, policy citation with the
cited policy text, who entered it, and when. Values are displayed exactly as stored: this
module formats numbers but never does arithmetic on them (R9).

SSNs are masked on screen (R17). The output is a draft for a Kushim preparer, never a filing.
"""
from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path

POLICY_FILE = Path(__file__).resolve().parents[2] / "data" / "policy.md"

# (line, label) in form order. Labels paraphrase the 2025 Form 1040-SR captions.
SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Income", [
        ("1a", "Total amount from Form(s) W-2, box 1"),
        ("1b", "Household employee wages not reported on Form(s) W-2"),
        ("1c", "Tip income not reported on line 1a"),
        ("1d", "Medicaid waiver payments not reported on Form(s) W-2"),
        ("1e", "Taxable dependent care benefits"),
        ("1f", "Employer-provided adoption benefits"),
        ("1g", "Wages from Form 8919"),
        ("1h", "Other earned income"),
        ("1z", "Total wages (add lines 1a through 1h)"),
        ("2a", "Tax-exempt interest"),
        ("2b", "Taxable interest"),
        ("3a", "Qualified dividends"),
        ("3b", "Ordinary dividends"),
        ("4a", "IRA distributions"),
        ("4b", "IRA distributions, taxable amount"),
        ("5a", "Pensions and annuities"),
        ("5b", "Pensions and annuities, taxable amount"),
        ("6a", "Social Security benefits"),
        ("6b", "Social Security benefits, taxable amount"),
        ("7", "Capital gain or (loss)"),
        ("8", "Additional income from Schedule 1, line 10"),
        ("9", "Total income"),
        ("10", "Adjustments to income from Schedule 1, line 26"),
        ("11a", "Adjusted gross income"),
    ]),
    ("Deductions", [
        ("12d", "Age / blindness boxes checked"),
        ("12e", "Standard deduction"),
        ("13a", "Qualified business income deduction"),
        ("13b", "Additional deductions from Schedule 1-A (senior deduction)"),
        ("14", "Total deductions (add lines 12e, 13a and 13b)"),
        ("15", "Taxable income"),
    ]),
    ("Tax and credits", [
        ("16", "Tax"),
        ("17", "Amount from Schedule 2, line 3"),
        ("18", "Add lines 16 and 17"),
        ("19", "Child tax credit or credit for other dependents"),
        ("20", "Amount from Schedule 3, line 8"),
        ("21", "Add lines 19 and 20"),
        ("22", "Subtract line 21 from line 18"),
        ("23", "Other taxes from Schedule 2, line 21"),
        ("24", "Total tax"),
    ]),
    ("Payments", [
        ("25a", "Federal income tax withheld from Form(s) W-2"),
        ("25b", "Federal income tax withheld from Form(s) 1099"),
        ("25c", "Federal income tax withheld from other forms"),
        ("25d", "Total federal income tax withheld"),
        ("26", "2025 estimated tax payments"),
        ("27", "Earned income credit"),
        ("28", "Additional child tax credit"),
        ("29", "American opportunity credit"),
        ("30", "Reserved / other refundable credit"),
        ("31", "Amount from Schedule 3, line 15"),
        ("32", "Total other payments and refundable credits"),
        ("33", "Total payments"),
    ]),
    ("Refund or amount you owe", [
        ("34", "Overpaid (refund)"),
        ("37", "Amount you owe"),
    ]),
]
COUNT_LINES = {"12d"}  # a count of boxes, not dollars
OPTIONAL_LINES = {"1b", "1c", "1d", "1e", "1f", "1g", "1h", "27", "28", "29", "30", "31"}
KIND_LABELS = {"extracted": "From a document", "user_input": "Entered by taxpayer", "computed": "Computed",
               "default_zero": "Zero (nothing provided)", "human_resolution": "Set by Kushim staff"}
FILING_STATUS_LABELS = {"single": "Single", "mfj": "Married filing jointly", "mfs": "Married filing separately",
                        "hoh": "Head of household", "qss": "Qualifying surviving spouse"}

CSS = """
.sf-form{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-size:16px;line-height:1.45;
 color:#1b1f24;max-width:980px}
.sf-banner{background:#fff4ce;border:1px solid #e0c060;border-radius:6px;padding:8px 12px;margin:0 0 12px;
 font-weight:600}
.sf-head{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px 24px;
 border:1px solid #c9d1d9;border-radius:6px;padding:12px;margin-bottom:16px;background:#f6f8fa}
.sf-head dt{font-size:13px;color:#57606a;margin:0}.sf-head dd{margin:0 0 4px;font-weight:600}
.sf-form h3{font-size:17px;margin:20px 0 6px;padding-bottom:4px;border-bottom:2px solid #1f4e79;color:#1f4e79}
.sf-row{display:grid;grid-template-columns:56px 1fr;align-items:start;border-bottom:1px solid #e5e8eb}
.sf-row:target{background:#eaf3ff}
.sf-num{font-weight:700;padding:7px 0 7px 4px;font-variant-numeric:tabular-nums}
.sf-label{padding:7px 8px}
.sf-line{display:grid;grid-template-columns:1fr 150px}
.sf-row summary{list-style:none;cursor:pointer;border-radius:4px}
.sf-row summary:hover{background:#f3f6f9}
.sf-row summary::-webkit-details-marker{display:none}
.sf-amt{text-align:right;padding:7px 8px;font-variant-numeric:tabular-nums;font-weight:600;position:relative}
.sf-amt .sf-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle}
.k-extracted{background:#2f81f7}.k-user_input{background:#8250df}.k-computed{background:#1a7f37}
.k-default_zero{background:#8c959f}.k-human_resolution{background:#bf3989}
.sf-tip{display:none;position:absolute;right:0;top:100%;z-index:20;width:340px;text-align:left;font-weight:400;
 font-size:13px;background:#1b1f24;color:#fff;border-radius:6px;padding:8px 10px;box-shadow:0 4px 12px #0003}
.sf-row summary:hover .sf-tip,.sf-row summary:focus .sf-tip{display:block}
.sf-row details[open] .sf-tip{display:none}
.sf-row summary:focus-visible{outline:3px solid #2f81f7;outline-offset:-3px}
.sf-prov{margin:0 0 10px;padding:10px 12px;border-left:4px solid #1f4e79;background:#f6f8fa;
 font-size:14px}
.sf-prov dl{display:grid;grid-template-columns:120px 1fr;gap:4px 12px;margin:0}
.sf-prov dt{color:#57606a}.sf-prov dd{margin:0;overflow-wrap:anywhere}
.sf-prov code{background:#eaeef2;padding:1px 4px;border-radius:4px;font-size:13px}
.sf-prov blockquote{margin:4px 0 0;padding:4px 8px;border-left:3px solid #d0d7de;color:#424a53;white-space:pre-line}
.sf-missing{color:#8c959f;font-weight:400}
.sf-legend{font-size:13px;color:#57606a;margin:4px 0 12px}.sf-legend span{margin-right:14px}
.sf-deps{width:100%;border-collapse:collapse;font-size:14px;margin-top:6px}
.sf-deps th,.sf-deps td{border-bottom:1px solid #e5e8eb;padding:4px 6px;text-align:left}
@media (prefers-color-scheme: dark){.sf-standalone{background:#fff}}
"""


def _e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def mask_ssn(value) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return f"XXX-XX-{digits[-4:]}" if len(digits) == 9 else ("—" if not value else "XXX-XX-XXXX")


def money(record: dict | None, line: str) -> str:
    if not record:
        return '<span class="sf-missing">not computed</span>'
    value = record.get("value")
    if line in COUNT_LINES:
        return f"{value} box{'es' if value != 1 else ''}"
    if not isinstance(value, int):
        return _e(value)
    text = f"{value:,}"
    # Accounting format for a Schedule 1 loss; string handling only, no arithmetic (R9).
    return f"({text[1:]})" if text.startswith("-") else text


def _slug(heading: str) -> str:
    return re.sub(r"\s+", "-", re.sub(r"[^a-z0-9 \-]", "", heading.lower()).strip())


@lru_cache(maxsize=1)
def policy_sections() -> dict[str, str]:
    """policy.md heading anchor -> section text, so a citation can show what it cites."""
    if not POLICY_FILE.is_file():
        return {}
    sections, current, buffer = {}, None, []
    for line in POLICY_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(buffer).strip()
            current, buffer = _slug(line[3:]), []
        elif current:
            buffer.append(line)
    if current:
        sections[current] = "\n".join(buffer).strip()
    return sections


def policy_excerpt(citation: str | None, limit: int = 420) -> str:
    if not citation or "#" not in citation:
        return ""
    text = policy_sections().get(citation.split("#", 1)[1], "")
    text = re.sub(r"\*\*|`", "", text)
    text = re.sub(r"\[([^\]]+)\]\(#[^)]+\)", r"\1", text)
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def _source_text(source: dict) -> str:
    if "doc_id" in source:
        text = f"{source.get('form', 'document')} <code>{_e(source['doc_id'])}</code> box {_e(source.get('box'))}"
        if "value" in source:
            text += f" = {_e(source['value'])}"
        if source.get("confirmed_by"):
            text += " (low-confidence value confirmed by taxpayer)"
        return text
    if "user_inputs" in source:
        return f"Intake answer for line {_e(source['user_inputs'])}"
    return "<code>" + _e(", ".join(f"{k}={v}" for k, v in source.items())) + "</code>"


def _input_text(item: dict) -> str:
    label = _e(item.get("label", ""))
    if item.get("line"):
        label = f'<a href="#line-{_e(item["line"])}">{label or "line " + _e(item["line"])}</a>'
    return f"{label}: {_e(item.get('value'))}"


def hover_summary(record: dict) -> str:
    kind = KIND_LABELS.get(record.get("kind"), record.get("kind", ""))
    parts = [kind]
    if record.get("tool"):
        parts.append(f"tool {record['tool'].get('name')}")
    if record.get("formula"):
        parts.append(record["formula"])
    if record.get("sources"):
        docs = [s["doc_id"] for s in record["sources"] if "doc_id" in s]
        if docs:
            parts.append("from " + ", ".join(docs))
    if record.get("entered_by"):
        parts.append(f"entered by {record['entered_by']}")
    return " · ".join(parts) + " — click for full record"


def provenance_panel(record: dict) -> str:
    rows = [("Source type", KIND_LABELS.get(record.get("kind"), _e(record.get("kind"))))]
    if record.get("formula"):
        rows.append(("Calculation", f"<code>{_e(record['formula'])}</code>"))
    if record.get("inputs"):
        rows.append(("Inputs", "<br>".join(_input_text(i) for i in record["inputs"])))
    if record.get("sources"):
        rows.append(("Documents", "<br>".join(_source_text(s) for s in record["sources"])))
    tool = record.get("tool")
    if tool:
        rows.append(("MCP tool", f"<code>{_e(tool.get('name'))}</code> v{_e(tool.get('version'))}"
                     + (f", tax year {_e(tool['tax_year'])}" if tool.get("tax_year") else "")))
    if record.get("citation"):
        excerpt = policy_excerpt(record["citation"])
        rows.append(("Policy", f"<code>{_e(record['citation'])}</code>"
                     + (f"<blockquote>{_e(excerpt)}</blockquote>" if excerpt else "")))
    if record.get("entered_by"):
        rows.append(("Entered by", _e(record["entered_by"])))
    rows.append(("Recorded", _e(record.get("timestamp"))))
    body = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows)
    return f'<div class="sf-prov" role="region" aria-label="Provenance for line {_e(record.get("line"))}"><dl>{body}</dl></div>'


def _line_row(line: str, label: str, record: dict | None) -> str:
    head = f'<div class="sf-num">{_e(line)}</div>'
    if not record:
        return (f'<div class="sf-row" id="line-{_e(line)}">{head}<div class="sf-line"><span class="sf-label">'
                f'{_e(label)}</span><span class="sf-amt">{money(None, line)}</span></div></div>')
    kind = _e(record.get("kind"))
    summary = (f'<summary class="sf-line" aria-label="Line {_e(line)}, {_e(label)}: {money(record, line)}. Show where this came from">'
               f'<span class="sf-label">{_e(label)}</span>'
               f'<span class="sf-amt" title="{_e(hover_summary(record))}"><span class="sf-dot k-{kind}"></span>'
               f'{money(record, line)}<span class="sf-tip" role="tooltip">{_e(hover_summary(record))}</span></span>'
               f'</summary>')
    return (f'<div class="sf-row" id="line-{_e(line)}">{head}<details>{summary}'
            f'{provenance_panel(record)}</details></div>')


def _header(intake: dict, meta: dict) -> str:
    taxpayer, spouse = intake.get("taxpayer") or {}, intake.get("spouse") or {}
    status = meta.get("filing_status") or intake.get("filing_status")
    items = [("Return", meta.get("title", "Draft Form 1040-SR (2025)")),
             ("Filing status", FILING_STATUS_LABELS.get(status, status or "not yet validated")),
             ("Taxpayer", taxpayer.get("name") or "—"), ("Taxpayer SSN", mask_ssn(taxpayer.get("ssn")))]
    if spouse:
        items += [("Spouse", spouse.get("name") or "—"), ("Spouse SSN", mask_ssn(spouse.get("ssn")))]
    items += [(k, v) for k, v in meta.get("extra", [])]
    head = "".join(f"<div><dt>{_e(k)}</dt><dd>{_e(v)}</dd></div>" for k, v in items)
    deps = intake.get("dependents") or []
    if deps:
        rows = "".join(f"<tr><td>{_e(d.get('name'))}</td><td>{mask_ssn(d.get('ssn'))}</td>"
                       f"<td>{_e(d.get('relationship'))}</td></tr>" for d in deps)
        head += ('<div style="grid-column:1/-1"><dt>Dependents</dt><dd><table class="sf-deps"><thead><tr>'
                 f'<th>Name</th><th>SSN</th><th>Relationship</th></tr></thead><tbody>{rows}</tbody></table></dd></div>')
    return f'<dl class="sf-head">{head}</dl>'


def render_form(lines: dict, intake: dict | None = None, meta: dict | None = None) -> str:
    """HTML fragment (for st.html). Lines missing from `lines` show as 'not computed'."""
    lines, intake, meta = lines or {}, intake or {}, meta or {}
    legend = "".join(f'<span><span class="sf-dot k-{k}" style="display:inline-block;width:8px;height:8px;'
                     f'border-radius:50%;margin-right:4px"></span>{v}</span>' for k, v in KIND_LABELS.items())
    parts = [f"<style>{CSS}</style>", '<div class="sf-form">',
             '<div class="sf-banner" role="note">DRAFT for Kushim staff review. Not filed. Not tax advice.</div>',
             _header(intake, meta),
             f'<div class="sf-legend">Hover a value for a summary; click it for the full record. {legend}</div>']
    for title, rows in SECTIONS:
        parts.append(f"<h3>{_e(title)}</h3>")
        for line, label in rows:
            record = lines.get(line)
            if record is None and line in OPTIONAL_LINES:
                continue
            parts.append(_line_row(line, label, record))
    parts.append("</div>")
    return "".join(parts)


def render_page(lines: dict, intake: dict | None = None, meta: dict | None = None) -> str:
    """Standalone HTML document for download or for the grader to open in a browser."""
    title = _e((meta or {}).get("title", "SilverFile draft Form 1040-SR"))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title></head>'
            f'<body class="sf-standalone" style="margin:24px">{render_form(lines, intake, meta)}</body></html>')
