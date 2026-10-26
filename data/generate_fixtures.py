"""Generate FAKE W-2 sample documents for tests, demos and the evaluation cases (P4).

Every person, employer, address, ID and amount here is invented. Every SSN is in the 900-series
testing range, with one deliberate exception: the "real-looking SSN" fixture uses 123-45-6789,
a well-known placeholder that was never issued, so we can prove the system rejects it.
Each page is stamped "SYNTHETIC SAMPLE - NOT A REAL TAX DOCUMENT".

Usage (from the repo root):
    python data/generate_fixtures.py                    # all fixtures -> data/fixtures/, demo/
    python data/generate_fixtures.py --out some/dir     # fixtures only, somewhere else
    python data/generate_fixtures.py --batch-only       # just the 10-document batch
    python data/generate_fixtures.py --custom my_w2.jpg --wages 41250.00 --withheld 3300 \\
            --ssn 900-11-2222 --name "Sam Placeholder" # one W-2 with YOUR numbers (graders: use this)

Output is deterministic: the same command always draws the same pictures (random noise is seeded).
Needs only Pillow and numpy; no tax code is imported except the SSN rule.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from src.security.ssn import is_test_ssn  # noqa: E402  (the one piece of shared code we reuse)

PAGE = (2000, 1500)
INK = (15, 15, 15)
LINE = (60, 60, 60)


def money(value: str | Decimal | None, commas: bool = True) -> str:
    """Format like a W-2: two decimals. None or "" prints a blank box."""
    if value in (None, ""):
        return ""
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:,.2f}" if commas else f"{amount:.2f}"


@dataclass
class W2Spec:
    """Everything printed on one fake W-2. Amounts are strings so cents are exact."""

    name: str                       # file stem, e.g. "w2_clean_1"
    employee_name: str = "Eleanor Testwood"
    employee_address: str = "100 Example Street, Anytown, NY 12345"
    ssn: str = "901-23-4567"
    ein: str = "98-7654321"
    employer_name: str = "Northwind Test Supply Co."
    employer_address: str = "1 Placeholder Plaza, Sampletown, NY 12345"
    control_number: str = "A0001"
    wages: str | None = "31250.00"             # box 1
    withheld: str | None = "3400.00"           # box 2
    ss_wages: str | None = "31250.00"          # box 3
    ss_tax: str | None = "1937.50"             # box 4
    medicare_wages: str | None = "31250.00"    # box 5
    medicare_tax: str | None = "453.13"        # box 6
    state_id: str = "NY 12-3456789"
    state_wages: str | None = "31250.00"       # box 16
    state_tax: str | None = "1100.00"          # box 17
    commas: bool = True
    style: str = "clean"                       # clean | scan | smudge
    seed: int = 1

    def truth(self) -> dict:
        """What a perfect reader would return. Used by tests; never read by the extractor."""
        boxes = {"1": self.wages, "2": self.withheld, "3": self.ss_wages, "4": self.ss_tax,
                 "5": self.medicare_wages, "6": self.medicare_tax}
        return {"name": self.name, "style": self.style, "ssn": self.ssn,
                "boxes": {k: (None if v in (None, "") else money(v, commas=False)) for k, v in boxes.items()},
                "note": "Synthetic data. Boxes are dollars and cents as printed; null means the box is blank."}


# --- drawing ------------------------------------------------------------------------------------
def _font(size: int, mono: bool = False, bold: bool = False):
    names = (["DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf", "cour.ttf", "Courier New.ttf"] if mono
             else ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", "arialbd.ttf" if bold else "arial.ttf",
                   "Arial.ttf"])
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _cell(draw, box, label, value="", lines=()):
    """One form cell: a border, a small label at the top-left and the value underneath it."""
    x0, y0, x1, y1 = box
    draw.rectangle(box, outline=LINE, width=3)
    draw.text((x0 + 16, y0 + 10), label, font=_font(21), fill=INK)
    if value:
        draw.text((x0 + 16, y0 + 52), value, font=_font(40, mono=True), fill=INK)
    for n, text in enumerate(lines):
        draw.text((x0 + 16, y0 + 52 + n * 44), text, font=_font(30, mono=True), fill=INK)


def render(spec: W2Spec) -> Image.Image:
    """Draw the form in the layout of IRS Form W-2 (Copy B), one cell per box."""
    page = Image.new("RGB", PAGE, "white")
    d = ImageDraw.Draw(page)
    d.text((80, 50), "Form W-2   Wage and Tax Statement   2025", font=_font(44, bold=True), fill=INK)
    d.text((80, 112), "Copy B - To Be Filed With Employee's FEDERAL Tax Return.", font=_font(24), fill=INK)
    d.text((1180, 60), "SYNTHETIC SAMPLE - NOT A REAL TAX DOCUMENT", font=_font(28, bold=True), fill=INK)
    d.text((1180, 104), "Fake data for software testing only.", font=_font(24), fill=INK)

    left, mid, right, end = 80, 880, 1420, 1940          # column edges
    rows = [210, 350, 490, 630, 770, 910, 1050, 1190]
    h = 140
    m = lambda key: money(getattr(spec, key), spec.commas)

    _cell(d, (left, rows[0], mid, rows[0] + h), "a  Employee's social security number", spec.ssn)
    _cell(d, (mid, rows[0], right, rows[0] + h), "1  Wages, tips, other compensation", m("wages"))
    _cell(d, (right, rows[0], end, rows[0] + h), "2  Federal income tax withheld", m("withheld"))
    _cell(d, (left, rows[1], mid, rows[1] + h), "b  Employer identification number (EIN)", spec.ein)
    _cell(d, (mid, rows[1], right, rows[1] + h), "3  Social security wages", m("ss_wages"))
    _cell(d, (right, rows[1], end, rows[1] + h), "4  Social security tax withheld", m("ss_tax"))
    _cell(d, (left, rows[2], mid, rows[3] + h), "c  Employer's name, address, and ZIP code",
          lines=[spec.employer_name, spec.employer_address])
    _cell(d, (mid, rows[2], right, rows[2] + h), "5  Medicare wages and tips", m("medicare_wages"))
    _cell(d, (right, rows[2], end, rows[2] + h), "6  Medicare tax withheld", m("medicare_tax"))
    _cell(d, (mid, rows[3], right, rows[3] + h), "7  Social security tips")
    _cell(d, (right, rows[3], end, rows[3] + h), "8  Allocated tips")
    _cell(d, (left, rows[4], mid, rows[4] + h), "d  Control number", spec.control_number)
    _cell(d, (mid, rows[4], right, rows[4] + h), "9")
    _cell(d, (right, rows[4], end, rows[4] + h), "10  Dependent care benefits")
    _cell(d, (left, rows[5], mid, rows[5] + h), "e  Employee's first name and initial   Last name",
          spec.employee_name)
    _cell(d, (mid, rows[5], right, rows[5] + h), "11  Nonqualified plans")
    _cell(d, (right, rows[5], end, rows[5] + h), "12a  See instructions for box 12")
    _cell(d, (left, rows[6], mid, rows[6] + h), "f  Employee's address and ZIP code", lines=[spec.employee_address])
    _cell(d, (mid, rows[6], right, rows[6] + h), "13  Retirement plan / Third-party sick pay")
    _cell(d, (right, rows[6], end, rows[6] + h), "12b")
    sub = (end - left) // 6
    labels = ["15  State  Employer's state ID no.", "16  State wages, tips, etc.", "17  State income tax",
              "18  Local wages, tips, etc.", "19  Local income tax", "20  Locality name"]
    values = [spec.state_id, m("state_wages"), m("state_tax"), "", "", ""]
    for n, (label, value) in enumerate(zip(labels, values)):
        box = (left + n * sub, rows[7], left + (n + 1) * sub, rows[7] + h)
        d.rectangle(box, outline=LINE, width=3)
        d.text((box[0] + 10, box[1] + 10), label, font=_font(17), fill=INK)
        if value:
            d.text((box[0] + 10, box[1] + 52), value, font=_font(28, mono=True), fill=INK)
    return _apply_style(page, spec)


def _apply_style(page: Image.Image, spec: W2Spec) -> Image.Image:
    rng = np.random.default_rng(spec.seed)
    if spec.style == "smudge":
        # An ink blot over the right half of the box 1 amount: a taxpayer's coffee-stained scan.
        overlay = Image.new("RGBA", page.size, (0, 0, 0, 0))
        ImageDraw.Draw(overlay).ellipse((1010, 255, 1140, 325), fill=(40, 40, 40, 250))
        page = Image.alpha_composite(page.convert("RGBA"), overlay.filter(ImageFilter.GaussianBlur(3))).convert("RGB")
    if spec.style == "scan":
        page = page.rotate(0.6, expand=True, fillcolor=(255, 255, 255), resample=Image.BICUBIC)
        page = page.filter(ImageFilter.GaussianBlur(0.8))
        pixels = np.asarray(page).astype(np.float32)
        pixels = pixels * 0.94 + 8                       # slightly grey paper
        pixels += rng.normal(0, 6, pixels.shape)          # scanner noise
        page = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))
    return page


def save(spec: W2Spec, folder: Path, formats=("png", "jpg", "pdf")) -> list[Path]:
    """Write the picture in the requested formats, plus <name>.truth.json."""
    folder.mkdir(parents=True, exist_ok=True)
    image = render(spec)
    written = []
    for fmt in formats:
        path = folder / f"{spec.name}.{fmt}"
        if fmt == "jpg":
            image.save(path, "JPEG", quality=70 if spec.style == "scan" else 92)
        elif fmt == "pdf":
            image.save(path, "PDF", resolution=200.0)
        else:
            image.save(path, "PNG")
        written.append(path)
    truth = folder / f"{spec.name}.truth.json"
    truth.write_text(json.dumps(spec.truth(), indent=2) + "\n", encoding="utf-8")
    return written + [truth]


# --- the fixtures ---------------------------------------------------------------------------------
# Evaluation case 1 (clean) and 2 (human review) documents. See evals/eval_cases.json.
EVAL_1 = W2Spec(name="w2_clean_1", seed=11)
EVAL_2 = W2Spec(name="w2_scan_2", style="scan", seed=22, employee_name="Harold Samplestone",
                ssn="902-34-5678", ein="98-1234567", employer_name="Lakeside Demo Services LLC",
                control_number="B0042", wages="24800.00", withheld="2100.00", ss_wages="24800.00",
                ss_tax="1537.60", medicare_wages="24800.00", medicare_tax="359.60",
                state_wages="24800.00", state_tax="880.00")

# Edge-case documents used by the tests.
EDGE_CASES = [
    # Cents, no commas (many payroll systems print this way), and a zero in box 2.
    W2Spec(name="w2_cents_3", seed=33, employee_name="Priya Placeholder", ssn="903-45-6789", ein="98-2223334",
           employer_name="Demo Harbor Foods Inc.", wages="48213.57", withheld="0.00", ss_wages="48213.57",
           ss_tax="2989.24", medicare_wages="48213.57", medicare_tax="699.09", state_wages="48213.57",
           state_tax="1500.10", commas=False),
    # Box 1 is blotted out: the extractor must flag it, not guess.
    W2Spec(name="w2_smudged_box1", style="smudge", seed=44, employee_name="Marcus Mockwell", ssn="904-56-7890",
           wages="87654.32", ss_wages="87654.32", ss_tax="5434.57", medicare_wages="87654.32",
           medicare_tax="1271.00", withheld="9100.00"),
    # Box 2 is empty: blank is not the same as zero, so it must be flagged, not turned into 0.
    W2Spec(name="w2_blank_box2", seed=55, employee_name="Jordan Fakeman", ssn="905-67-8901", withheld=None),
    # A number outside the 900 series: this is what a real SSN would look like. Must be refused.
    W2Spec(name="w2_real_looking_ssn", seed=66, employee_name="Casey Notreal", ssn="123-45-6789"),
]

_FIRST = ["Alma", "Bruno", "Celia", "Dev", "Esme", "Felix", "Greta", "Hugo", "Ines", "Jules"]
_LAST = ["Fakename", "Testerman", "Mockford", "Samplewood", "Placeholder", "Dummyfield", "Examplar",
         "Trialson", "Stubbs", "Notreal"]
_EMPLOYERS = ["Acme Demo Works", "Blue Test Dairy Co.", "Cedar Mock Clinic", "Delta Sample Freight",
              "Evergreen Fake Foods", "Fairview Pretend Bank", "Granite Trial Hardware",
              "Harbor Dummy Marine", "Iris Example Labs", "Juniper Sandbox Schools"]


def batch_specs(count: int = 10) -> list[W2Spec]:
    """Ten different fake W-2s for the batch / context-window measurement (TEAM.md: P4 -> P3)."""
    rng = random.Random(2025)
    specs = []
    for n in range(count):
        wages = Decimal(rng.randrange(1_800_000, 9_500_000)) / 100
        withheld = (wages * Decimal(rng.choice(["0.06", "0.08", "0.10", "0.12"]))).quantize(Decimal("0.01"))
        ss_tax = (wages * Decimal("0.062")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        med_tax = (wages * Decimal("0.0145")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        specs.append(W2Spec(
            name=f"w2_batch_{n + 1:02d}", seed=100 + n, style="clean",
            employee_name=f"{_FIRST[n]} {_LAST[n]}", ssn=f"9{n:02d}-{rng.randrange(10, 99)}-{rng.randrange(1000, 9999)}",
            ein=f"98-{rng.randrange(1000000, 9999999)}", employer_name=_EMPLOYERS[n],
            control_number=f"C{n + 1:04d}", wages=str(wages), withheld=str(withheld), ss_wages=str(wages),
            ss_tax=str(ss_tax), medicare_wages=str(wages), medicare_tax=str(med_tax),
            state_wages=str(wages), state_tax=str((wages * Decimal("0.04")).quantize(Decimal("0.01")))))
    return specs


def generate_all(out: Path, demo: Path | None, batch_only: bool = False) -> list[Path]:
    written: list[Path] = []
    if not batch_only:
        written += save(EVAL_1, out)                                    # clean: PNG, JPG and PDF
        written += save(EVAL_2, out, formats=("jpg", "pdf"))            # noisy scan: a PNG would be 6 MB
        for spec in EDGE_CASES:                     # edge cases only need one format
            written += save(spec, out, formats=("jpg",))
        if demo is not None:
            # The assignment's demo folder wants w2_image_1.jpg and w2_image_2.jpg.
            for spec, target in ((EVAL_1, "w2_image_1"), (EVAL_2, "w2_image_2")):
                demo.mkdir(parents=True, exist_ok=True)
                (demo / f"{target}.jpg").write_bytes((out / f"{spec.name}.jpg").read_bytes())
                written.append(demo / f"{target}.jpg")
    batch_dir = out / "batch"
    manifest = []
    for spec in batch_specs():
        written += save(spec, batch_dir, formats=("jpg",))
        manifest.append({"doc_id": spec.name, "source_file": f"data/fixtures/batch/{spec.name}.jpg", "form": "W-2"})
    (batch_dir / "manifest.json").write_text(json.dumps({"uploads": manifest}, indent=2) + "\n", encoding="utf-8")
    written.append(batch_dir / "manifest.json")
    return written


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=REPO / "data" / "fixtures")
    parser.add_argument("--demo-dir", type=Path, default=REPO / "demo",
                        help="where w2_image_1.jpg / w2_image_2.jpg are copied (use --no-demo to skip)")
    parser.add_argument("--no-demo", action="store_true")
    parser.add_argument("--batch-only", action="store_true")
    parser.add_argument("--custom", type=Path, metavar="FILE", help="write ONE W-2 (png/jpg/pdf by extension)")
    for option in ("wages", "withheld", "ss_wages", "ss_tax", "medicare_wages", "medicare_tax"):
        parser.add_argument(f"--{option.replace('_', '-')}", help="amount, e.g. 41250.00")
    parser.add_argument("--ssn", default="900-11-2222", help="must be 900-999 (test range)")
    parser.add_argument("--name", default="Sam Placeholder")
    parser.add_argument("--style", choices=["clean", "scan"], default="clean")
    args = parser.parse_args(argv)

    if args.custom:
        if not is_test_ssn(args.ssn):
            parser.error("--ssn must be a 900-series test number (900-999). Never use a real SSN.")
        fields = {o: getattr(args, o) for o in ("wages", "withheld", "ss_wages", "ss_tax", "medicare_wages",
                                                "medicare_tax") if getattr(args, o) is not None}
        spec = W2Spec(name=args.custom.stem, employee_name=args.name, ssn=args.ssn, style=args.style, **fields)
        suffix = args.custom.suffix.lstrip(".").lower() or "jpg"
        written = save(spec, args.custom.parent if str(args.custom.parent) else Path("."), formats=(suffix,))
    else:
        written = generate_all(args.out, None if args.no_demo else args.demo_dir, args.batch_only)
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
