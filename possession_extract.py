#!/usr/bin/env python3
"""Extract Cork-area Absolute Possessions — clear & simple.

Focus lines:
  - Cork East (Cork–Cobh / Midleton)
  - Cork–Mallow (incl. Charleville)
  - Mallow–Tralee

PDF layout tip: each section lists From-times, then To-times, then day codes.
Pair row i as From[i]–To[i].

Usage:
  python possession_extract.py --pdf Sunday_pages.pdf --out notes.txt
  python possession_extract.py --pdf part1.pdf --pdf part2.pdf --out notes.txt
  python possession_extract.py --pdf Sunday_pages.pdf --day Monday --out day.txt
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

DAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

CORRIDOR_RULES = (
    (re.compile(r"(?i)CK/?CH/?MT|Cork[- /]*Cobh|Cork[- /]*Midleton|Cobh[- /]*Midleton"), "Cork East"),
    (re.compile(r"(?i)MW/?CK|Mallow[- /]*Cork|Cork[- /]*Mallow"), "Cork–Mallow"),
    (re.compile(r"(?i)RC/?CK|Charleville[- /]*Cork"), "Cork–Mallow (Charleville)"),
    (
        re.compile(
            r"(?i)MW/?BR|BR/?KY|BR/?MT|MT/?RE|KY/?FE|KY/?STN|FE/?TE|"
            r"Mallow[- /]*Banteer|Banteer[- /]*Killarney|Banteer[- /]*Millstreet|"
            r"Millstreet[- /]*Rathmore|Killarney[- /]*Farranfore|Farranfore[- /]*Tralee|"
            r"Killarney Station|MALLOW[- /]*TRALEE"
        ),
        "Mallow–Tralee",
    ),
)

SECTION_START_RE = re.compile(r"^\(([A-Z0-9][A-Z0-9/]{1,24})\)\s*$", re.MULTILINE)
DAY7_RE = re.compile(
    r"\b([1-7_]\s*,\s*[1-7_]\s*,\s*[1-7_]\s*,\s*[1-7_]\s*,\s*[1-7_]\s*,\s*[1-7_]\s*,\s*[1-7_])\b"
)
TIME_RE = re.compile(r"(?<!\d)(\d{1,2}\.\d{2})(?!\.\d)")
DIR_RE = re.compile(r"(?i)\b(Up & Down|Up Only|Down Only|Down Fast|Up Fast|Single)\b")
HEADER_RE = re.compile(r"(?i)ABSOLUTE POSSESSIONS|ENGINEERING WORKS REQUIRING ABSOLUTE")
WORK_KEYWORDS = re.compile(
    r"(?i)\b(CACR Works|Track Maintenance|Track Repairs|Hired Plant|Drainage|"
    r"Rural Fencing|OTMs?|Tamper|Hobs Train|Rail Milling|L\.?C\.? Upgrade|"
    r"Vegetation|Bridge|Signalling|Fencing)\b"
)


@dataclass(frozen=True)
class PossessionSlot:
    day: str
    line: str
    section: str
    direction: str
    time_from: str
    time_to: str
    duration: str
    work: str


def read_pdf_text(path: Path) -> str:
    try:
        import fitz

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


def read_many_pdfs(paths: Sequence[Path]) -> str:
    return "\n\n".join(read_pdf_text(p) for p in paths)


def _corridor_for(code: str, name: str) -> Optional[str]:
    blob = f"{code} {name}"
    for rx, label in CORRIDOR_RULES:
        if rx.search(blob):
            return label
    return None


def _norm_time(t: str) -> str:
    return t.replace(".", ":")


def _duration_hm(t_from: str, t_to: str) -> str:
    def mins(s: str) -> int:
        h, m = s.replace(".", ":").split(":")
        return int(h) * 60 + int(m)

    a, b = mins(t_from), mins(t_to)
    if b <= a:
        b += 24 * 60
    d = b - a
    h, m = divmod(d, 60)
    if h and m:
        return f"{h}h {m:02d}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def _parse_days(token: str) -> List[int]:
    out: List[int] = []
    for part in token.split(","):
        part = part.strip()
        if part.isdigit():
            n = int(part)
            if 1 <= n <= 7:
                out.append(n)
    return out


def _clean_work(body: str) -> str:
    """Prefer short work keywords; drop signals / legends / miles."""
    found = WORK_KEYWORDS.findall(body)
    if found:
        # preserve order, unique
        seen = set()
        uniq = []
        for w in found:
            key = w.lower()
            if key not in seen:
                seen.add(key)
                uniq.append(w)
        return ", ".join(uniq[:6])
    return ""


def _section_name_after(text: str, start: int) -> str:
    chunk = text[start : start + 180]
    lines: List[str] = []
    for ln in chunk.splitlines():
        s = ln.strip()
        if not s:
            if lines:
                break
            continue
        if DIR_RE.search(s):
            break
        if re.match(r"^[A-Z]{2}\d{2,4}\b", s):
            break
        if TIME_RE.search(s) and not re.search(r"[A-Za-z]{3,}", s):
            break
        if re.match(r"(?i)^(DAYS OF THE WEEK|W\.?E\.|W\.?C\.|Section$|Protecting)", s):
            continue
        if re.match(r"^\(", s):
            break
        lines.append(s)
        if len(" ".join(lines)) > 45:
            break
    return re.sub(r"\s+", " ", " ".join(lines)).strip(" -") or "Section"


def _pair_times(times: List[str], n_rows: int) -> List[Tuple[str, str]]:
    """Match Absolute Possessions table: From×N then To×N (or sequential pairs)."""
    if n_rows <= 0 or not times:
        return []
    # Ideal: exactly 2N times → first N From, last N To
    if len(times) == 2 * n_rows:
        return [(_norm_time(times[i]), _norm_time(times[i + n_rows])) for i in range(n_rows)]
    # Extra times (noise) but at least 2N: take first 2N with From/To split
    if len(times) > 2 * n_rows and len(times) % 2 == 0:
        half = len(times) // 2
        if half >= n_rows:
            return [
                (_norm_time(times[i]), _norm_time(times[i + half])) for i in range(n_rows)
            ]
    # Fallback sequential pairs
    pairs: List[Tuple[str, str]] = []
    j = 0
    while j + 1 < len(times) and len(pairs) < n_rows:
        pairs.append((_norm_time(times[j]), _norm_time(times[j + 1])))
        j += 2
    while len(pairs) < n_rows and pairs:
        pairs.append(pairs[0])
    return pairs


def extract_possessions(text: str) -> List[PossessionSlot]:
    m = HEADER_RE.search(text)
    if m:
        text = text[m.start() :]

    starts = list(SECTION_START_RE.finditer(text))
    slots: List[PossessionSlot] = []
    seen = set()

    for i, sm in enumerate(starts):
        code = sm.group(1).strip()
        end = starts[i + 1].start() if i + 1 < len(starts) else min(len(text), sm.end() + 1400)
        name = _section_name_after(text, sm.end())
        corridor = _corridor_for(code, name)
        if not corridor:
            continue

        body = text[sm.end() : end]
        body = re.sub(r"(?i)W\.?E\.?\s*\d{1,2}\.\d{2}\.\d{2}", " ", body)
        body = re.sub(r"(?i)DAYS OF THE WEEK:.*", " ", body)
        body = re.sub(r"(?i)MONDAY \d+(?:ST|ND|RD|TH)? TO SUNDAY .*?20\d{2}", " ", body)
        # Drop long narrative "At 23.20 hrs on Monday..." — keep table block only
        body = re.sub(r"(?i)At \d{1,2}\.\d{2} hrs on .*?(?=\(|$)", " ", body)

        direction = "Up & Down"
        dm = DIR_RE.search(body)
        if dm:
            direction = dm.group(1)

        day_rows = [_parse_days(tok) for tok in DAY7_RE.findall(body)]
        day_rows = [d for d in day_rows if d]
        if not day_rows:
            continue

        times_raw = TIME_RE.findall(body)
        pairs = _pair_times(times_raw, len(day_rows))
        if not pairs:
            continue

        work = _clean_work(body)
        section_label = f"{name} ({code})"

        for idx, days in enumerate(day_rows):
            tf, tt = pairs[idx] if idx < len(pairs) else pairs[0]
            # Skip zero-length daytime noise (00:05–00:05)
            if tf == tt and tf not in ("00:00", "24:00"):
                continue
            for d in days:
                day = DAY_NAMES[d - 1]
                key = (day, corridor, section_label, tf, tt, direction)
                if key in seen:
                    continue
                seen.add(key)
                slots.append(
                    PossessionSlot(
                        day=day,
                        line=corridor,
                        section=section_label,
                        direction=direction,
                        time_from=tf,
                        time_to=tt,
                        duration=_duration_hm(tf, tt),
                        work=work,
                    )
                )

    order = {n: i for i, n in enumerate(DAY_NAMES)}
    line_order = {
        "Cork East": 0,
        "Cork–Mallow": 1,
        "Cork–Mallow (Charleville)": 2,
        "Mallow–Tralee": 3,
    }
    slots.sort(
        key=lambda s: (
            order.get(s.day, 99),
            line_order.get(s.line, 9),
            s.time_from,
            s.section,
        )
    )
    return slots


def _is_major(s: PossessionSlot) -> bool:
    """Overnight / Up & Down / long blocks — show first."""
    if "Up & Down" in s.direction:
        return True
    try:
        h = int(s.time_from.split(":")[0])
        if h >= 20 or h < 6:
            return True
    except Exception:
        pass
    # duration >= 3h
    m = re.match(r"(\d+)h", s.duration)
    if m and int(m.group(1)) >= 3:
        return True
    return False


def format_possessions_simple(slots: Sequence[PossessionSlot]) -> str:
    lines = [
        "POSSESSIONS — Cork East / Cork–Mallow / Mallow–Tralee",
        "(from Absolute Possessions table — skim circular to confirm)",
        "",
    ]
    if not slots:
        lines += ["No Cork-area possessions found in this PDF.", ""]
        return "\n".join(lines)

    current_day = None
    for s in slots:
        if s.day != current_day:
            current_day = s.day
            day_slots = [x for x in slots if x.day == current_day]
            major = [x for x in day_slots if _is_major(x)]
            plant = [x for x in day_slots if not _is_major(x)]
            lines.append("")
            lines.append(f"{s.day}")
            lines.append("=" * len(s.day))
            if major:
                lines.append("")
                lines.append("Main / overnight")
                for x in major:
                    lines.append(
                        f"  {x.line}: {x.time_from}–{x.time_to} ({x.duration}) — {x.direction}"
                    )
                    detail = x.section
                    if x.work:
                        detail += f" — {x.work}"
                    lines.append(f"    {detail}")
            if plant:
                lines.append("")
                lines.append("Daytime plant (single line)")
                for x in plant:
                    lines.append(
                        f"  {x.line}: {x.time_from}–{x.time_to} ({x.duration}) — {x.section}"
                    )
    lines.append("")
    return "\n".join(lines)


def format_possessions_for_day(day: str, slots: Sequence[PossessionSlot]) -> str:
    """Paste block for one Word daily-sheet day (append after circular notes)."""
    day_slots = [s for s in slots if s.day == day]
    lines = ["* POSSESSIONS (Cork East / Cork–Mallow / Mallow–Tralee)"]
    if not day_slots:
        lines.append("* (none for this day — skim Sunday Absolute Possessions to confirm)")
        return "\n".join(lines)

    major = [s for s in day_slots if _is_major(s)]
    plant = [s for s in day_slots if not _is_major(s)]
    if major:
        lines.append("* — Main / overnight —")
        for s in major:
            bit = f"* {s.line}: {s.time_from}–{s.time_to} ({s.duration}) — {s.direction} — {s.section}"
            if s.work:
                bit += f" — {s.work}"
            lines.append(bit)
    if plant:
        lines.append("* — Daytime plant —")
        for s in plant:
            lines.append(
                f"* {s.line}: {s.time_from}–{s.time_to} ({s.duration}) — {s.section}"
            )
    return "\n".join(lines)


def extract_possessions_from_pdfs(paths: Sequence[Path]) -> List[PossessionSlot]:
    return extract_possessions(read_many_pdfs(paths))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Extract Cork-area Absolute Possessions")
    ap.add_argument("--pdf", action="append", required=True, help="PDF path (repeatable)")
    ap.add_argument("--out", required=True, help="Output text file")
    ap.add_argument("--day", help="Monday..Sunday → one-day paste block")
    args = ap.parse_args(list(argv) if argv is not None else None)

    paths = [Path(p) for p in args.pdf]
    for p in paths:
        if not p.exists():
            Path(args.out).write_text(f"ERROR: PDF not found: {p}\n", encoding="utf-8")
            return 3
    try:
        slots = extract_possessions_from_pdfs(paths)
        if args.day:
            day = args.day.strip().title()
            text = format_possessions_for_day(day, slots)
        else:
            text = format_possessions_simple(slots)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"OK: {len(slots)} slot(s) -> {args.out}", file=sys.stderr)
        return 0
    except Exception as e:
        Path(args.out).write_text(f"ERROR: {e}\n", encoding="utf-8")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
