"""Reading a W-2 picture: load pages, run OCR, find each box's value (P4).

The approach is "find the printed label, read the number printed under it":
  1. Load the image (PNG/JPG/TIFF/...) or the pages of a PDF.
  2. An OCR backend turns the page into words with positions and a confidence score each.
  3. For each W-2 box we look for the words of its printed label ("Wages, tips, other compensation"),
     then take the nearest number directly below it. This works on any layout that prints the amount
     under its label, which is how the IRS form is laid out, instead of relying on fixed pixel positions.
  4. The page is read TWICE with different image preparation. A value counts as "read" only when
     both passes agree and the OCR confidence is high. A value the passes disagree on is "uncertain".

No tax meaning is applied anywhere in this file, and nothing is added up. We copy printed numbers.
"""
from __future__ import annotations

import difflib
import hashlib
import re
import shutil
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Protocol

from PIL import Image, ImageOps

from src.extraction.schema import CONFIDENCE_THRESHOLD, MONEY_BOXES, SSN_BOX, SSN_BOX_LABEL, Word
from src.security.ssn import check_ssn

MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 40_000_000              # refuses decompression bombs
MAX_PDF_PAGES = 4
PDF_DPI = 200
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


class UnreadableDocument(Exception):
    """The file is missing, too big, the wrong type, or damaged. The message is safe to log."""


class OcrBackend(Protocol):
    """Anything that can turn an image into positioned words. Tests plug in a fake one.

    `line=True` means "this picture is one short line of text" (a cropped value). `charset` then limits
    which characters may be returned (digits and punctuation for money), which stops letters being guessed.
    """

    name: str

    def read_words(self, image: Image.Image, *, line: bool = False, charset: str | None = None) -> list[Word]: ...


class TesseractBackend:
    """OCR through the Tesseract engine (needs the `tesseract` program plus the `pytesseract` package)."""

    def __init__(self) -> None:
        import pytesseract
        self._pt = pytesseract
        self.name = f"tesseract {pytesseract.get_tesseract_version()}"

    @staticmethod
    def available() -> bool:
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            return False
        return shutil.which("tesseract") is not None

    def read_words(self, image: Image.Image, *, line: bool = False, charset: str | None = None) -> list[Word]:
        config = "--psm 7" if line else "--psm 11"
        if charset:
            config += f" -c tessedit_char_whitelist={charset}"
        data = self._pt.image_to_data(image, config=config, output_type=self._pt.Output.DICT)
        words = []
        for text, left, top, width, height, conf in zip(data["text"], data["left"], data["top"],
                                                          data["width"], data["height"], data["conf"]):
            text = (text or "").strip()
            if text and float(conf) >= 0:
                words.append(Word(text=text, left=int(left), top=int(top), width=int(width),
                                  height=int(height), conf=float(conf)))
        return words


# --- loading ----------------------------------------------------------------------------------------
def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pages(path: Path) -> list[Image.Image]:
    """Open an image or PDF as a list of RGB pages. Raises UnreadableDocument with a safe message."""
    if not path.is_file():
        raise UnreadableDocument("file not found")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise UnreadableDocument("file is larger than 15 MB")
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            import pypdfium2
            pdf = pypdfium2.PdfDocument(str(path))
            pages = [pdf[i].render(scale=PDF_DPI / 72).to_pil().convert("RGB")
                     for i in range(min(len(pdf), MAX_PDF_PAGES))]
        elif suffix in IMAGE_SUFFIXES:
            with Image.open(path) as opened:
                if opened.width * opened.height > MAX_PIXELS:
                    raise UnreadableDocument("image is too large")
                pages = [ImageOps.exif_transpose(opened).convert("RGB")]
        else:
            raise UnreadableDocument(f"unsupported file type {suffix or '(none)'}")
    except UnreadableDocument:
        raise
    except Exception as exc:                      # damaged file, encrypted PDF, missing PDF library ...
        raise UnreadableDocument(f"could not open the file ({type(exc).__name__})") from None
    if not pages:
        raise UnreadableDocument("document has no pages")
    return pages


# --- finding labels and values -------------------------------------------------------------------------
_MONEY = re.compile(r"^\$?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?$")
_HAS_CENTS = re.compile(r"\.\d{2}$")

# Words printed in each label, in order. Box "a" is the SSN cell.
_LABEL_WORDS: dict[str, list[str]] = {
    SSN_BOX: ["employee's", "social", "security", "number"],
    "1": ["wages", "tips", "other", "compensation"],
    "2": ["federal", "income", "tax", "withheld"],
    "3": ["social", "security", "wages"],
    "4": ["social", "security", "tax", "withheld"],
    "5": ["medicare", "wages", "and", "tips"],
    "6": ["medicare", "tax", "withheld"],
}
assert set(MONEY_BOXES) | {SSN_BOX} == set(_LABEL_WORDS)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9']", "", text.lower().replace("’", "'"))


def _similar(a: str, b: str) -> float:
    """0..1 closeness of two words. A clear abbreviation ("comp." for "compensation") counts as a match."""
    if len(a) >= 4 and b.startswith(a):
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()


@dataclass
class _Label:
    box: str
    score: float
    left: int
    top: int
    right: int
    bottom: int
    height: int


def _group_lines(words: list[Word]) -> list[list[Word]]:
    """Chain words into text lines, left to right.

    A word joins a line when it starts just to the right of that line's last word and sits at about the
    same height. Only neighbouring words are compared, so a page scanned a little crooked (the line
    drifts up or down across the page) still groups correctly.
    """
    lines: list[list[Word]] = []
    for word in sorted(words, key=lambda w: (w.left, w.top)):
        centre = word.top + word.height / 2
        best, best_gap = None, None
        for line in lines:
            last = line[-1]
            gap = word.left - last.right
            drift = abs(centre - (last.top + last.height / 2))
            if -2 <= gap <= 4 * max(word.height, last.height) and drift <= 0.7 * max(word.height, last.height):
                if best is None or drift < best_gap:
                    best, best_gap = line, drift
        if best is None:
            lines.append([word])
        else:
            best.append(word)
    return lines


def find_labels(words: list[Word]) -> dict[str, _Label]:
    """Best match on the page for each box's printed label (fuzzy, so small OCR slips still match)."""
    candidates: list[_Label] = []
    for line in _group_lines(words):
        tokens = [_norm(w.text) for w in line]
        for box, phrase in _LABEL_WORDS.items():
            n = len(phrase)
            for start in range(0, len(line) - n + 1):
                scores = [_similar(tokens[start + k], phrase[k]) for k in range(n)]
                if min(scores) >= 0.6 and sum(scores) / n >= 0.8:
                    span = line[start:start + n]
                    candidates.append(_Label(
                        box, sum(scores) / n, min(w.left for w in span), min(w.top for w in span),
                        max(w.right for w in span), max(w.bottom for w in span), max(w.height for w in span)))
    best: dict[str, _Label] = {}
    for label in sorted(candidates, key=lambda c: (-c.score, c.top)):   # highest score, then topmost
        best.setdefault(label.box, label)
    return best




# --- reading each value --------------------------------------------------------------------------------
MONEY_CHARS = "0123456789,.$"
SSN_CHARS = "0123456789-"
CROP_SCALES = (2.0, 2.5, 3.0)       # three independent enlargements of the same crop


@dataclass
class Located:
    """Where a box's value sits on the page: the label, and the number the first scan saw under it (if any)."""

    label: _Label
    parts: list[Word]               # words the page-level scan read under the label, left to right
    region: tuple[int, int, int, int]  # pixels to crop for the focused re-read


def locate(words: list[Word], page_size: tuple[int, int]) -> dict[str, Located]:
    """Find every box's label, the value printed under it, and a tight crop box around where it sits."""
    labels = find_labels(words)
    numbers = [w for w in words if any(ch.isdigit() for ch in w.text)]
    pairs: list[tuple[float, str, Word]] = []
    for label in labels.values():
        h = label.height
        # A value belongs to this label only if it sits above the next label that lies below it.
        floor = min((o.top for o in labels.values()
                     if o is not label and o.top > label.bottom
                     and o.left < label.right + 8 * h and o.right > label.left - 8 * h), default=10 ** 9)
        for word in numbers:
            dy = word.top - label.bottom
            dx = word.left - label.left
            if -0.5 * h <= dy <= 8 * h and word.top < floor and -7 * h <= dx <= (label.right - label.left) + 3 * h:
                pairs.append((abs(dx) + 2 * max(dy, 0), label.box, word))
    pairs.sort(key=lambda p: p[0])
    chosen: dict[str, Word] = {}
    used: set[int] = set()
    for _cost, box, word in pairs:
        if box not in chosen and id(word) not in used:
            chosen[box] = word
            used.add(id(word))

    width, height = page_size
    located: dict[str, Located] = {}
    for box, label in labels.items():
        h = label.height
        first = chosen.get(box)
        parts = [first] if first else []
        if first and box == SSN_BOX:       # an SSN may come back as several words on one line
            for word in sorted((w for w in numbers if w is not first and w.left >= first.left and abs(
                    (w.top + w.height / 2) - (first.top + first.height / 2)) < 0.5 * first.height),
                    key=lambda w: w.left):
                if word.left - parts[-1].right <= 1.5 * first.height:
                    parts.append(word)
        # Right edge: stop before the next cell's label on the same row, so a neighbour's number is never read.
        row_top = (first.top if first else label.bottom)
        neighbours = [o.left for o in labels.values() if o is not label and o.left > label.right
                      and abs(o.top - label.top) < 4 * h]
        if first:
            left = first.left - 12
            top, bottom = first.top - 8, max(w.bottom for w in parts) + 8
            right_cap = left + max(14 * first.height, 360)
        else:                               # nothing seen under the label: look in the area where it should be
            left = label.left - 30
            top, bottom = label.bottom + 4, label.bottom + 4 + int(4.5 * h)
            right_cap = left + 520
        right = min(right_cap, (min(neighbours) - 60) if neighbours else right_cap, width)
        located[box] = Located(label, parts, (max(0, left), max(0, top), max(right, left + 40), min(height, bottom)))
    return located


@dataclass
class BoxResult:
    """The outcome for one box after comparing all reading passes."""

    box: str
    value: Decimal | None
    raw_text: str | None
    confidence: float
    status: str                        # read / uncertain / unreadable
    reason: str | None
    location: tuple[int, int, int, int] | None
    ssn_status: str | None = None
    ssn_masked: str | None = None


def parse_amount(text: str | None) -> Decimal | None:
    """'31,250.00' -> Decimal('31250.00'). Anything that is not a plain dollar amount returns None."""
    if text is None:
        return None
    cleaned = text.strip().rstrip(".,;:")
    if not _MONEY.match(cleaned) or len(cleaned) > 16:
        return None
    try:
        return Decimal(cleaned.replace("$", "").replace(",", ""))
    except InvalidOperation:
        return None


def _crop_pass(page: Image.Image, region: tuple[int, int, int, int], scale: float, backend: OcrBackend,
               charset: str) -> str:
    """Re-read one cropped value at a given enlargement. Returns the text, or "" if nothing was read.

    Only the TEXT of a close-up is used. Tesseract's confidence numbers on tiny crops are unreliable
    (it can report 0 for a perfectly read number), so confidence comes from the full-page readings instead.
    """
    crop = ImageOps.autocontrast(ImageOps.grayscale(page.crop(region)), cutoff=1)
    crop = crop.resize((max(1, int(crop.width * scale)), max(1, int(crop.height * scale))), Image.LANCZOS)
    crop = ImageOps.expand(crop, border=24, fill=255)
    return "".join(w.text for w in backend.read_words(crop, line=True, charset=charset))


def _page_votes(locs: list[Located]) -> list[tuple[str, float]]:
    """(text, confidence 0..1) of the number each full-page reading saw under the label."""
    return [("".join(w.text for w in loc.parts), min(w.conf for w in loc.parts) / 100) for loc in locs if loc.parts]


MIN_AGREEING_READINGS = 3       # of the (up to) five readings, at least this many must give the same answer
MAX_DISSENTING_READINGS = 1     # ... and no rival answer may be backed by more than this many
IGNORE_PAGE_VOTE_BELOW = 0.5    # a full-page reading this unsure is noise; it neither helps nor hurts


def _tally(votes: list):
    """Most common non-empty answer, its count, and the count of the runner-up."""
    counts: dict = {}
    for vote in votes:
        if vote is not None:
            counts[vote] = counts.get(vote, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    top, top_n = ranked[0] if ranked else (None, 0)
    return top, top_n, (ranked[1][1] if len(ranked) > 1 else 0)


def _decide_money(box: str, locs: list[Located], crops: list[str]) -> BoxResult:
    """A value is "read" only when several independent readings agree and the engine is confident.

    Readings: three close-up crops plus up to two full-page scans. The answer must be backed by at least
    three of them with at most one rival. Anything less is "uncertain" and the taxpayer will be asked.
    """
    region = locs[0].region
    page = [(t, c) for t, c in _page_votes(locs) if c >= IGNORE_PAGE_VOTE_BELOW]
    page_amounts = [parse_amount(t) for t, _ in page]
    votes = [parse_amount(t) for t in crops] + page_amounts
    shown = " | ".join(dict.fromkeys(t for t in [*crops, *(t for t, _ in page)] if t)) or None
    if all(v is None for v in votes):
        return BoxResult(box, None, shown, 0.0, "unreadable",
                         "no clear dollar amount could be read here (the box may be blank or damaged)", region)
    top, top_n, rival_n = _tally(votes)
    if top_n < MIN_AGREEING_READINGS or rival_n > MAX_DISSENTING_READINGS:
        # The readings disagree, so no number is trustworthy. Show none; the taxpayer will be asked instead.
        best = max((c for _, c in page), default=0.0)
        return BoxResult(box, None, shown, min(best, 0.5), "uncertain",
                         "the readings of this box gave different answers", region)
    agreeing = [c for (t, c), amount in zip(page, page_amounts) if amount == top]
    confidence = max(agreeing, default=0.0)
    text = next((t for (t, _), amount in zip(page, page_amounts) if amount == top), None) or \
        next(t for t in crops if parse_amount(t) == top)
    if not _HAS_CENTS.search(text):
        # W-2 amounts are printed to the cent. "87" or "87,654" almost certainly means the rest is
        # smudged, cut off or covered, so it is never accepted, however many readings agree.
        return BoxResult(box, None, shown, min(confidence, 0.5), "uncertain",
                         "the amount has no cents, so part of it may be missing", region)
    if confidence < CONFIDENCE_THRESHOLD:
        reason = ("no full-page reading confirmed it" if not agreeing else "the reading engine was not confident")
        return BoxResult(box, top, text, confidence, "uncertain", reason, region)
    return BoxResult(box, top, text, confidence, "read", None, region)


def _digest(check, text: str) -> str | None:
    """A one-way fingerprint of a reading, so readings can be compared without keeping the number."""
    if check.ok:
        return hashlib.sha256(check.normalized.encode()).hexdigest()
    if check.reason == "not_test_range":
        return hashlib.sha256(re.sub(r"[^0-9]", "", text).encode()).hexdigest()
    return None


def _decide_ssn(locs: list[Located], crops: list[str]) -> BoxResult:
    """Run the SSN rule on every reading. Only a verdict and a masked form leave this function."""
    region = locs[0].region
    page = [(t, c) for t, c in _page_votes(locs) if c >= IGNORE_PAGE_VOTE_BELOW]
    texts = [*crops, *(t for t, _ in page)]
    checks = [check_ssn(t) for t in texts]
    if all(c.reason in ("empty", "bad_format") for c in checks):
        return BoxResult(SSN_BOX, None, None, 0.0, "unreadable", "the number could not be read clearly",
                         region, "unreadable", "***-**-****")
    digests = [_digest(c, t) for c, t in zip(checks, texts)]
    top, top_n, rival_n = _tally(digests)
    if top_n < MIN_AGREEING_READINGS or rival_n > MAX_DISSENTING_READINGS:
        return BoxResult(SSN_BOX, None, None, 0.5, "uncertain",
                         "the readings of this number gave different answers", region, "unreadable", "***-**-****")
    verdict = next(c for c, d in zip(checks, digests) if d == top)
    page_digests = digests[len(crops):]
    confidence = max((conf for (_t, conf), d in zip(page, page_digests) if d == top), default=0.0)
    masked = verdict.masked if verdict.ok else "***-**-****"      # a non-test number is not echoed at all
    confident = confidence >= CONFIDENCE_THRESHOLD
    return BoxResult(SSN_BOX, None, None, confidence, "read" if confident else "uncertain",
                     None if confident else "the reading engine was not confident", region,
                     "accepted" if verdict.ok else "not_test_range", masked)


def read_w2_page(page: Image.Image, backend: OcrBackend) -> dict[str, BoxResult]:
    """Read every box on one page.

    Step 1: two full-page scans (as scanned, and enlarged with more contrast) find the labels and the
            number under each, with the engine's confidence.
    Step 2: each value is cropped and re-read three times at different enlargements, digits only.
    Step 3: all readings must agree. Anything else is "uncertain" or "unreadable", never a guess.
    """
    gray = ImageOps.grayscale(page)
    enlarged = ImageOps.autocontrast(gray, cutoff=1).resize(
        (int(gray.width * 1.5), int(gray.height * 1.5)), Image.LANCZOS)
    located_a = locate(backend.read_words(gray), gray.size)
    located_b = locate(backend.read_words(enlarged), enlarged.size)
    results: dict[str, BoxResult] = {}
    for box in [SSN_BOX, *MONEY_BOXES]:
        loc = located_a.get(box)
        if loc is None:
            results[box] = BoxResult(box, None, None, 0.0, "unreadable",
                                     "the printed label for this box was not found on the page", None,
                                     "unreadable" if box == SSN_BOX else None,
                                     "***-**-****" if box == SSN_BOX else None)
            continue
        locs = [loc] + ([located_b[box]] if box in located_b else [])
        charset = SSN_CHARS if box == SSN_BOX else MONEY_CHARS
        crops = [_crop_pass(page, loc.region, scale, backend, charset) for scale in CROP_SCALES]
        results[box] = _decide_ssn(locs, crops) if box == SSN_BOX else _decide_money(box, locs, crops)
    return results
