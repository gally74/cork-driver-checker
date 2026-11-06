#!/usr/bin/env python3
"""Extract Cork/Mallow/Tralee roster impacts from a weekly circular PDF.

Includes Cork/Mallow/Tralee Driver crew notes, cancellations, bus substitutions,
and other traffic changes on Cork/Mallow/Tralee routes.

Usage:
  python circular_extract.py --pdf Monday_pages.pdf --day Monday --expected 2026-11-02 --out notes.txt

Exit codes:
  0 = ok (notes may be empty)
  2 = date mismatch / cannot validate date
  3 = PDF missing / read error
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

DRIVER_RE = re.compile(r"(?i)\b(cork|mallow|tralee)\s+drivers?\b")
OTHER_DRIVER_RE = re.compile(
    r"(?i)\b(?!cork|mallow|tralee)([A-Za-z]+)\s+drivers?\b"
)
# Prefer over-inclusion for rostering — places + common codes
CMT_PLACE_RE = re.compile(
    r"(?i)\b(cork|mallow|tralee|cobh|midleton|charleville|kent)\b"
    r"|(?<![A-Za-z])(Ck|Mw|Hstn)(?![A-Za-z])"
)
TRAIN_START_RE = re.compile(
    r"(?i)^(Reg\.?|Ety\.?|Empty|Special|Railcar|Railcar movement)\b"
)
IMPACT_RE = re.compile(
    r"(?i)\b("
    r"cancel|cancelled|cancellation|"
    r"substituted by buses|substituted by bus|bus transfers?|buses will|road transfers?|"
    r"operate to .+ only|will not operate|does not operate|"
    r"diverted|diversion|terminate[sd]? at|terminating at|"
    r"retimed|re-timed|altered timing|altered|non-stop|runs via|via |"
    r"short[- ]?formed|reduced to|attached|detached|"
    r"single line|possession|blockade|"
    r"crew arrangements|relief required|pilot required|"
    r"as required|extra working|special working|platform change"
    r")\b"
)
CMT_SECTION_RE = re.compile(
    r"(?i)^(ENGINEERING WORKS|TRAFFIC ARRANGEMENTS|EMPTY RAILCAR MOVEMENT|"
    r"SPEED RESTRICTIONS)\s*:.*"
    r"\b(cork|mallow|tralee|cobh|midleton|charleville|kent)\b"
)
REGIONAL_CORK_RE = re.compile(r"(?i)^REGIONAL OFFICE,\s*CORK\b")
SECTION_STOP_RE = re.compile(
    r"(?i)^(ENGINEERING WORKS|TRAFFIC ARRANGEMENTS|EMPTY RAILCAR|SPEED RESTRICTIONS|"
    r"WEEKLY CIRCULAR|PART\s+\d|LINE\s*&\s*SECTION|TRAIN\s+I\.?D)"
)
CHECK_PDF_BANNER = (
    "CHECK CIRCULAR PDF — no auto matches for Cork/Mallow/Tralee "
    "(still skim Engineering / Traffic / Empty Railcar)."
)

# MONDAY 2ND NOVEMBER, 2026  /  Monday 2nd November 2026
DATE_RE = re.compile(
    r"(?i)\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(january|february|march|april|may|june|july|august|september|october|november|december)\s*,?\s*"
    r"(20\d{2})\b"
)

# WEEK-ENDING SUNDAY 8TH NOVEMBER, 2026
WEEK_END_RE = re.compile(
    r"(?i)WEEK[-\s]?ENDING\s+(?:SUNDAY\s+)?"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(january|february|march|april|may|june|july|august|september|october|november|december)\s*,?\s*"
    r"(20\d{2})\b"
)

# (MONDAY 2ND – SUNDAY 8TH NOVEMBER, 2026)
RANGE_RE = re.compile(
    r"(?i)\(\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\s*[–\-—]\s*"
    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(january|february|march|april|may|june|july|august|september|october|november|december)\s*,?\s*"
    r"(20\d{2})\s*\)"
)


def read_pdf_text(path: Path) -> str:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path)
        try:
            return "\n".join(page.get_text() for page in doc)
        finally:
            doc.close()
    except Exception:
        pass
    import PyPDF2
    reader = PyPDF2.PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def parse_date(day: str, dom: int, month: str, year: int) -> datetime:
    return datetime(year, MONTHS[month.lower()], dom)


def extract_pdf_day_date(text: str, day_name: str) -> datetime | None:
    """Best date for this day's circular (prefer explicit day headers)."""
    day_l = day_name.lower()
    candidates: list[datetime] = []

    for m in DATE_RE.finditer(text):
        if m.group(1).lower() != day_l:
            continue
        try:
            candidates.append(
                parse_date(m.group(1), int(m.group(2)), m.group(3), int(m.group(4)))
            )
        except Exception:
            continue

    # Prefer dates that appear near ENGINEERING / TRAFFIC / day title (not ancient refs)
    # Filter to year >= 2025 if possible
    recent = [d for d in candidates if d.year >= 2025]
    pool = recent or candidates
    if not pool:
        # Fall back: week range start if day is Monday
        for m in RANGE_RE.finditer(text):
            if m.group(1).lower() == "monday" and day_l == "monday":
                try:
                    return parse_date("monday", int(m.group(2)), m.group(5), int(m.group(6)))
                except Exception:
                    pass
        return None

    # Mode / most common date for this weekday
    counts: dict[datetime, int] = {}
    for d in pool:
        key = datetime(d.year, d.month, d.day)
        counts[key] = counts.get(key, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _trim_other_depot_drivers(block: str) -> str:
    """Keep Cork/Mallow/Tralee driver clauses; cut at a following other-depot Driver."""
    m = DRIVER_RE.search(block)
    if not m:
        return block
    cut = None
    for od in OTHER_DRIVER_RE.finditer(block):
        if od.start() > m.start():
            cut = od.start()
            break
    if cut is not None:
        return block[:cut].strip(" ;,.")
    return block


def _is_cmt_train_line(line: str) -> bool:
    if not TRAIN_START_RE.match(line):
        return False
    return bool(CMT_PLACE_RE.search(line))


def _collect_block(lines: list[str], start: int, max_extra: int = 12) -> tuple[str, int]:
    """Join start line + indented/continuation lines. Returns (block, next_index)."""
    block_lines = [lines[start]]
    j = start + 1
    while j < len(lines) and j <= start + max_extra:
        nxt = lines[j]
        if not nxt:
            # allow one blank inside a train block
            if j + 1 < len(lines) and lines[j + 1] and (
                lines[j + 1].startswith("-")
                or lines[j + 1].lower().startswith("will ")
                or lines[j + 1].lower().startswith("is ")
                or lines[j + 1].lower().startswith("bus")
                or re.match(r"(?i)^CREW ARRANGEMENTS:", lines[j + 1])
            ):
                j += 1
                continue
            break
        if SECTION_STOP_RE.match(nxt) or CMT_SECTION_RE.match(nxt):
            break
        # "Reg. Alt. …" is a continuation of the previous train, not a new entry
        if TRAIN_START_RE.match(nxt) and j > start and not re.match(
            r"(?i)^Reg\.?\s*Alt\.?\b", nxt
        ):
            break
        if REGIONAL_CORK_RE.match(nxt) and j > start:
            break
        if re.match(r"(?i)^CREW ARRANGEMENTS:", nxt) and j > start:
            # include our depot crew; stop before other-depot-only crew
            if OTHER_DRIVER_RE.search(nxt) and not DRIVER_RE.search(nxt):
                break
        if OTHER_DRIVER_RE.search(nxt) and not DRIVER_RE.search(nxt) and not CMT_PLACE_RE.search(nxt):
            break
        block_lines.append(nxt)
        j += 1
    return _norm_space(" ".join(block_lines)), j


def _mentions_cmt(s: str) -> bool:
    return bool(CMT_PLACE_RE.search(s) or DRIVER_RE.search(s))


def extract_roster_notes(text: str) -> list[str]:
    """Notes that may affect Cork / Mallow / Tralee rostering (prefer over-inclusion)."""
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    notes: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue

        # Section banner for CMT engineering / traffic / empty / speed — context header
        if CMT_SECTION_RE.match(line):
            block = _norm_space(line)
            if block not in notes:
                notes.append(block)
            i += 1
            continue

        # Regional office Cork road-transfer instruction (single line)
        if REGIONAL_CORK_RE.match(line):
            block = _norm_space(line)
            if block not in notes:
                notes.append(block)
            i += 1
            continue

        # Cork/Mallow/Tralee Driver crew arrangements
        if DRIVER_RE.search(line) or (
            re.match(r"(?i)^CREW ARRANGEMENTS:", line)
            and _mentions_cmt(" ".join(lines[i : i + 4]))
        ):
            block, j = _collect_block(lines, i, max_extra=14)
            block = _trim_other_depot_drivers(block)
            if _mentions_cmt(block) and block not in notes:
                # Drop other-depot-only crew with no CMT place left
                if DRIVER_RE.search(block) or CMT_PLACE_RE.search(block):
                    if not (
                        OTHER_DRIVER_RE.search(block)
                        and not DRIVER_RE.search(block)
                        and not CMT_PLACE_RE.search(block)
                    ):
                        notes.append(block)
            i = max(j, i + 1)
            continue

        # Any Reg/Ety/Empty train naming CMT places — keep all (roster may care)
        if _is_cmt_train_line(line):
            block, j = _collect_block(lines, i, max_extra=14)
            block = _trim_other_depot_drivers(block)
            if _mentions_cmt(block) and block not in notes:
                notes.append(block)
            i = max(j, i + 1)
            continue

        # Other lines: CMT place + impact wording (catch odd layouts)
        if _mentions_cmt(line) and IMPACT_RE.search(line):
            # skip pure maintenance "on or near the line" unless impact-y already matched
            block, j = _collect_block(lines, i, max_extra=8)
            block = _trim_other_depot_drivers(block)
            if _mentions_cmt(block) and block not in notes:
                notes.append(block)
            i = max(j, i + 1)
            continue

        i += 1

    return notes


# Back-compat alias
def extract_driver_notes(text: str) -> list[str]:
    return extract_roster_notes(text)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--day", required=True, help="Monday..Sunday")
    ap.add_argument("--expected", required=True, help="YYYY-MM-DD expected calendar date for that day")
    ap.add_argument("--out", required=True, help="Output text file for notes")
    args = ap.parse_args()

    day = args.day.strip()
    if day.lower() not in DAY_NAMES:
        print(f"ERROR: bad day '{day}'", file=sys.stderr)
        return 3

    pdf = Path(args.pdf)
    out = Path(args.out)
    if not pdf.exists():
        out.write_text(f"ERROR: PDF not found: {pdf}\n", encoding="utf-8")
        print(f"ERROR: PDF not found: {pdf}", file=sys.stderr)
        return 3

    try:
        expected = datetime.strptime(args.expected.strip()[:10], "%Y-%m-%d")
    except ValueError:
        out.write_text(f"ERROR: bad expected date '{args.expected}'\n", encoding="utf-8")
        return 3

    try:
        text = read_pdf_text(pdf)
    except Exception as e:
        out.write_text(f"ERROR: could not read PDF: {e}\n", encoding="utf-8")
        return 3

    pdf_date = extract_pdf_day_date(text, day)
    if pdf_date is None:
        out.write_text(
            "ERROR: could not find a date in the circular for "
            f"{day}. Check the PDF is a weekly circular.\n",
            encoding="utf-8",
        )
        return 2

    if (pdf_date.year, pdf_date.month, pdf_date.day) != (
        expected.year,
        expected.month,
        expected.day,
    ):
        out.write_text(
            "DATE_MISMATCH\n"
            f"PDF date: {pdf_date.strftime('%A %d %B %Y')}\n"
            f"Expected: {expected.strftime('%A %d %B %Y')}\n"
            "Wrong weekly circular in the folder - not pasted.\n",
            encoding="utf-8",
        )
        return 2

    notes = extract_roster_notes(text)
    lines = [
        f"CIRCULAR NOTES - {day} {expected.strftime('%d %B %Y')} "
        f"(Cork / Mallow / Tralee roster - skim PDF to confirm)",
        "",
    ]
    if not notes:
        # Visible trail — silence is dangerous for rostering
        lines.append(f"* {CHECK_PDF_BANNER}")
    else:
        for n in notes:
            lines.append(f"* {n}")
        lines.append("")
        lines.append(
            "* Reminder: skim Engineering / Traffic / Empty Railcar for anything missed."
        )
    # ASCII so Excel VBA OpenTextFile (ANSI) does not mojibake into Word
    out.write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")
    print(f"OK: {len(notes)} note(s) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
