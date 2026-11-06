#!/usr/bin/env python3
"""
Cork Driver checker — day PDF against that day's daily sheet.

Reads Monday_pages.pdf (or Tue/Wed/...) from a week folder, pulls every
Cork Driver crew arrangement, and writes a checklist. If that day's Word
daily sheet is present, marks each item Found or Missing.

Usage:
  py -3 cork_driver_checker.py
  py -3 cork_driver_checker.py --day Monday
  py -3 cork_driver_checker.py --week "WEEK-ENDING SUNDAY 27TH SEPTEMBER, 2026" --day Monday
  py -3 cork_driver_checker.py --day Monday --sheet "DailySheet Monday 21 September 2026.docx"
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


def app_dir() -> Path:
    """Folder the user launched from: the .exe location when frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def search_roots() -> List[Path]:
    roots = []
    for path in (Path.cwd(), app_dir(), app_dir().parent):
        resolved = path.resolve()
        if resolved not in roots and resolved.is_dir():
            roots.append(resolved)
    return roots


def pause_on_exit() -> None:
    try:
        input("Press Enter to exit...")
    except (EOFError, OSError):
        pass



DAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

DAY_PDF_NAME = {day: f"{day}_pages.pdf" for day in DAYS}

OTHER_CREW = re.compile(
    r"(?:Cork Host|Heuston Driver|Limerick Driver|Mallow Driver|Tralee Driver|"
    r"Galway Driver|Portlaoise Driver|Drogheda Driver|Connolly Driver|"
    r"Fairview Driver|Athlone Driver|Westport Driver|Ballina Guard|"
    r"Connolly D\.T\.E|DART\+\s*Project Driver)",
    re.IGNORECASE,
)

CORK_DRIVER_RE = re.compile(r"Cork Drivers?\b", re.IGNORECASE)
# Cork + Mallow + Tralee depot drivers (daily-sheet extract)
LOCAL_DRIVER_RE = re.compile(
    r"(?:Cork|Mallow|Tralee)\s+Drivers?\b",
    re.IGNORECASE,
)

TRAIN_LINE_RE = re.compile(
    r"(?P<kind>Ety\.?|Reg\.?,?|Spl\.?)\s+"
    r"(?:Alt\.\s+)?"
    r"(?:\d+\s+)?"
    r"(?P<time>\d{1,2}\.\d{2})\s+"
    r"(?P<route>[A-Za-z][^()\n]{2,90}?)\s*"
    r"\((?P<train_id>[A-Z]\d{2,4})\)",
    re.IGNORECASE,
)

DUTY_STOP_RE = re.compile(
    r"(?:"
    r"Cork Host|"
    r"will be bus|"
    r"Bus transfers|"
    r"operates as per|"
    r"operates to form|"
    r"is deferred|"
    r"will call additionally|"
    r"will operate to|"
    r"will go Ety|"
    r"Set will form|"
    r"SET WORKINGS|"
    r"REGIONAL OFFICE|"
    r"\bEMPTY [A-Z]|"
    r"\bICR ALTER|"
    r"\bRAILTOURS|"
    r"\bENGINEERING WORKS|"
    r"\bSPECIAL:|"
    r"\bNOTES\b|"
    r"\bTRAIN I\.D|"
    r"W\.C\.\s*\d|"
    r"contd\./|"
    r"(?:MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY)\s+\d"
    r")",
    re.IGNORECASE,
)

ON_DAY_RE = re.compile(
    r"\bon\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
    re.IGNORECASE,
)

FORM_ON_RE = re.compile(
    r"(?:forms?|remain(?:s|ing)? in .{0,50}? to form)\s+"
    r"(.{0,90}?)\s+"
    r"on\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
    re.IGNORECASE | re.DOTALL,
)

PAGE_RE = re.compile(r"(?m)^-\s*(\d{1,3})\s*-")

PLACE_ALIASES = (
    ("portarlington", ("portarlington", "ptarlington")),
    ("portlaoise", ("portlaoise", "ptlaoise", "ploise")),
    ("limerick jctn", ("limerick jct", "limerick junction", " l.j", " lj ", "ljct")),
    ("killarney", ("killarney",)),
    ("thurles", ("thurles",)),
    ("tralee", ("tralee",)),
    ("mallow", ("mallow", " mw ", "mw–", "mw -", "mw-")),
    ("charleville", ("charleville",)),
    ("waterford", ("waterford",)),
    ("limerick", ("limerick",)),
    ("conduct", ("conduct", "conducting")),
)


@dataclass
class TrainRef:
    kind: str
    time: str
    route: str
    train_id: str = ""

    def label(self) -> str:
        route = re.sub(r"\s+", " ", self.route).strip(" .")
        bits = [self.kind, self.time, route]
        if self.train_id:
            bits.append(f"({self.train_id})")
        return " ".join(bits)


@dataclass
class CorkDriverItem:
    day: str
    cork_duty: str
    heading_title: str = ""
    related_trains: List[TrainRef] = field(default_factory=list)
    circular_page: str = ""
    source_pdf: str = ""
    carry_forward: List[str] = field(default_factory=list)
    sheet_status: str = "NOT CHECKED"
    sheet_note: str = ""
    sheet_match: str = ""

    def times_hhmm(self) -> List[str]:
        blob = " ".join(
            [self.cork_duty]
            + [t.time for t in self.related_trains]
            + [t.label() for t in self.related_trains]
        )
        return unique(time_to_hhmm(t) for t in re.findall(r"\d{1,2}\.\d{2}", blob))

    def train_ids(self) -> List[str]:
        ids = [t.train_id for t in self.related_trains if t.train_id]
        ids += re.findall(r"\(([A-Z]\d{2,4})\)", self.cork_duty)
        return unique(ids)

    def fingerprint(self) -> Tuple:
        duty = flatten(self.cork_duty).lower()
        action = "conduct" if "conduct" in duty else "work"
        times = tuple(sorted(unique(time_to_hhmm(t) for t in re.findall(r"\d{1,2}\.\d{2}", duty))))
        return (action, times, duty[:80])


def flatten(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\t", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    return re.sub(r" +", " ", text).strip()


def unique(values: Iterable[str]) -> List[str]:
    seen = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def time_to_hhmm(value: str) -> str:
    hours, minutes = value.split(".")
    return f"{int(hours):02d}{minutes}"


def extract_pdf_pages(pdf_path: Path) -> List[str]:
    """Return text for each page (1 entry per page)."""
    try:
        import fitz  # type: ignore

        doc = fitz.open(str(pdf_path))
        pages = [(page.get_text("text") or "") for page in doc]
        doc.close()
        return pages
    except Exception:
        pass

    try:
        import PyPDF2
    except ImportError as exc:
        raise SystemExit(
            "Need PyMuPDF or PyPDF2 to read circular PDFs.\n"
            "Install with:  py -3 -m pip install pymupdf PyPDF2 python-docx"
        ) from exc

    pages = []
    with open(pdf_path, "rb") as handle:
        reader = PyPDF2.PdfReader(handle)
        for page in reader.pages:
            pages.append(page.extract_text() or "")
    return pages


def extract_pdf_text(pdf_path: Path) -> str:
    return "\n".join(extract_pdf_pages(pdf_path))


def detect_day_label(text: str) -> str:
    """Return Monday..Sunday if a day heading is found near the start of the text."""
    head = "\n".join(text.splitlines()[:25])
    match = re.search(
        r"\b(MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY)\b"
        r"(?:\s+\d{1,2}(?:ST|ND|RD|TH)?\b)?",
        head,
        re.IGNORECASE,
    )
    if not match:
        return ""
    return match.group(1).capitalize()


def split_circular_by_day(pdf_path: Path) -> dict:
    """Group full weekly circular pages into Monday..Sunday text blobs."""
    pages = extract_pdf_pages(pdf_path)
    by_day = {day: [] for day in DAYS}
    current = ""
    for page_text in pages:
        found = detect_day_label(page_text)
        if found:
            current = found
        if current:
            by_day[current].append(page_text)
    return {day: "\n".join(parts) for day, parts in by_day.items() if parts}


def extract_heading_trains(preceding: str) -> List[TrainRef]:
    blob = flatten(preceding[-900:])
    trains: List[TrainRef] = []
    seen_ids = set()
    for match in TRAIN_LINE_RE.finditer(blob):
        after = blob[match.end(): match.end() + 24]
        if ON_DAY_RE.match(after.lstrip()) or re.match(r"\s*on\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", after, re.IGNORECASE):
            continue
        route = re.sub(r"\s+", " ", match.group("route")).strip(" .")
        route = re.sub(r"\s+operates.*$", "", route, flags=re.IGNORECASE)
        route = re.sub(r"\s+\d+\s*(Railcar|ICR|MKIV|BEMU|EMU).*$", "", route, flags=re.IGNORECASE)
        route = re.sub(r"\s+STATION MANAGER.*$", "", route, flags=re.IGNORECASE)
        route = re.sub(r"\s+Please issue.*$", "", route, flags=re.IGNORECASE)
        route = re.split(r"\s+(?:Reg\.|Ety\.|Spl\.)\s+", route)[0]
        if re.search(r"STATION MANAGER|Please issue", route, re.IGNORECASE):
            continue
        kind = match.group("kind").replace(",", ".")
        if kind.lower().startswith("reg"):
            kind = "Reg."
        elif kind.lower().startswith("ety"):
            kind = "Ety."
        elif kind.lower().startswith("spl"):
            kind = "Spl."
        train_id = match.group("train_id").upper()
        if train_id in seen_ids:
            continue
        seen_ids.add(train_id)
        trains.append(
            TrainRef(
                kind=kind,
                time=match.group("time"),
                route=route[:70],
                train_id=train_id,
            )
        )
    return trains[-4:]


def extract_heading_title(preceding: str) -> str:
    titles = re.findall(
        r"(?m)^([A-Z][A-Z0-9 /:&'’-]{8,90})$",
        preceding,
    )
    if titles:
        title = re.sub(r"\s+", " ", titles[-1]).strip(" .")
        if " " in title or "/" in title or ":" in title:
            return title
    return ""


def extract_circular_page(preceding: str) -> str:
    matches = list(PAGE_RE.finditer(preceding))
    return matches[-1].group(1) if matches else ""


def cork_driver_snippets(crew_text: str) -> List[str]:
    """Extract Cork / Mallow / Tralee Driver duty snippets from a crew block."""
    snippets = []
    for match in LOCAL_DRIVER_RE.finditer(crew_text):
        rest = crew_text[match.start():]
        prefix_len = match.end() - match.start()
        cut_at = None
        for crew_match in OTHER_CREW.finditer(rest[prefix_len:]):
            abs_start = crew_match.start() + prefix_len
            before = rest[max(0, abs_start - 24): abs_start]
            if re.search(r"conducts?\s*$", before, re.IGNORECASE):
                continue
            cut_at = abs_start
            break
        chunk = rest[:cut_at] if cut_at is not None else rest
        stop = DUTY_STOP_RE.search(chunk, 20)
        if stop:
            chunk = chunk[: stop.start()]
        chunk = flatten(chunk)
        chunk = re.sub(r"\s+(Ety|Reg|Spl)\.?$", "", chunk, flags=re.IGNORECASE)
        chunk = chunk.strip(" .;")
        if len(chunk) > 260:
            chunk = chunk[:260].rsplit(" ", 1)[0]
        if chunk and chunk not in snippets:
            snippets.append(chunk)
    return snippets


def is_useful_carry(snippet: str) -> bool:
    if re.search(r"\boff\s+(Spl|Reg|Ety)\b", snippet, re.IGNORECASE):
        return False
    if not re.search(
        r"cork|thurles|killarney|mallow|tralee|charleville|portarlington|portlaoise|limerick jct",
        snippet,
        re.IGNORECASE,
    ):
        return False
    if re.search(r"\barrives\b", snippet, re.IGNORECASE):
        return False
    return True


def carry_forward_notes(section_text: str, current_day: str) -> List[str]:
    notes = []
    for match in FORM_ON_RE.finditer(flatten(section_text)):
        other_day = match.group(2).capitalize()
        if other_day.lower() == current_day.lower():
            continue
        snippet = re.sub(r"\s+", " ", flatten(match.group(0)))
        if not is_useful_carry(snippet):
            continue
        notes.append(f"{snippet}  -> put on {other_day} sheet")
    if notes:
        return unique(notes)

    for match in ON_DAY_RE.finditer(flatten(section_text)):
        other_day = match.group(1).capitalize()
        if other_day.lower() == current_day.lower():
            continue
        start = max(0, match.start() - 70)
        snippet = flatten(section_text)[start: match.end() + 5]
        if not re.search(r"\b(forms?|Spl|Reg|Ety|remain)\b", snippet, re.IGNORECASE):
            continue
        if not is_useful_carry(snippet):
            continue
        notes.append(f"{snippet}  -> put on {other_day} sheet")
    return unique(notes)


def parse_day_text(text: str, day: str, source_name: str = "") -> Tuple[List[CorkDriverItem], List[str]]:
    if not text.strip():
        return [], []

    chunks = re.split(r"(CREW ARRANGEMENTS:)", text, flags=re.IGNORECASE)
    items: List[CorkDriverItem] = []

    for index in range(1, len(chunks), 2):
        preceding = chunks[index - 1]
        body = chunks[index + 1] if index + 1 < len(chunks) else ""
        cut = re.search(
            r"TRAIN I\.D\.|NOTES:|ENGINEERING WORKS|CREW ARRANGEMENTS:|-- \d+ of \d+ --",
            body,
            re.IGNORECASE,
        )
        crew_intro = body[: cut.start()] if cut else body[:900]
        crew_block = flatten(chunks[index] + " " + crew_intro)
        if not LOCAL_DRIVER_RE.search(crew_block):
            continue

        snippets = cork_driver_snippets(crew_block)
        if not snippets:
            continue

        trains = extract_heading_trains(preceding[-1500:])
        title = extract_heading_title(preceding[-1500:])
        page = extract_circular_page(preceding[-2000:])
        carry = carry_forward_notes(preceding[-1200:] + " " + crew_intro, day)

        items.append(
            CorkDriverItem(
                day=day,
                cork_duty=". ".join(snippets),
                heading_title=title,
                related_trains=trains,
                circular_page=page,
                source_pdf=source_name,
                carry_forward=carry,
            )
        )

    covered = flatten(" ".join(item.cork_duty for item in items)).lower()
    for match in LOCAL_DRIVER_RE.finditer(text):
        window = flatten(text[max(0, match.start() - 400): match.end() + 280])
        if "crew arrangements" not in window.lower():
            continue
        snippet = cork_driver_snippets(window)
        if not snippet:
            continue
        if snippet[0].lower()[:40] in covered:
            continue
        items.append(
            CorkDriverItem(
                day=day,
                cork_duty=snippet[0],
                source_pdf=source_name,
            )
        )

    return merge_items(items)


def parse_day_pdf(pdf_path: Path, day: str) -> Tuple[List[CorkDriverItem], List[str]]:
    text = extract_pdf_text(pdf_path)
    if not text.strip():
        raise SystemExit(f"No text could be read from {pdf_path}")
    return parse_day_text(text, day, source_name=pdf_path.name)


def merge_items(items: Sequence[CorkDriverItem]) -> Tuple[List[CorkDriverItem], List[str]]:
    merged: List[CorkDriverItem] = []
    all_carry: List[str] = []
    seen = {}
    for item in items:
        all_carry.extend(item.carry_forward)
        times = tuple(sorted(unique(time_to_hhmm(t) for t in re.findall(r"\d{1,2}\.\d{2}", item.cork_duty))))
        action = "conduct" if "conduct" in item.cork_duty.lower() else "work"
        duty_l = item.cork_duty.lower()
        if "mallow driver" in duty_l:
            depot = "mallow"
        elif "tralee driver" in duty_l:
            depot = "tralee"
        else:
            depot = "cork"
        key = (depot, action, times) if times else (depot,) + item.fingerprint()
        if key in seen:
            existing = merged[seen[key]]
            for train in item.related_trains:
                if train.label() not in {t.label() for t in existing.related_trains}:
                    existing.related_trains.append(train)
            if item.heading_title and item.heading_title not in existing.heading_title:
                if existing.heading_title:
                    existing.heading_title += " / " + item.heading_title
                else:
                    existing.heading_title = item.heading_title
            if item.circular_page and item.circular_page not in existing.circular_page:
                existing.circular_page = (
                    f"{existing.circular_page}, {item.circular_page}"
                    if existing.circular_page
                    else item.circular_page
                )
            continue
        seen[key] = len(merged)
        merged.append(item)
    return merged, unique(all_carry)


def collapse_repeated_cells(line: str) -> str:
    """Word tables often repeat merged Job Analysis cells. Keep each part once."""
    line = line.replace("\x07", "").replace("\u00a0", " ")
    parts = [flatten(part) for part in re.split(r"\s*\|\s*", line)]
    collapsed = []
    for part in parts:
        if not part:
            continue
        if part in collapsed:
            continue
        collapsed.append(part)
    return " | ".join(collapsed)


def extract_docm_text(path: Path) -> str:
    """Read .docm/.docx via the Office Open XML zip (works when python-docx rejects .docm)."""
    import zipfile

    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    text = re.sub(r"</w:p>", "\n", xml)
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#8211;", "-")
        .replace("&#8212;", "-")
    )
    lines = []
    for raw in text.splitlines():
        line = collapse_repeated_cells(flatten(raw))
        if line:
            lines.append(line)
    return "\n".join(lines)


def read_word_text(sheet_path: Path) -> str:
    suffix = sheet_path.suffix.lower()
    if suffix in {".docx", ".docm"}:
        try:
            import docx  # type: ignore

            document = docx.Document(str(sheet_path))
            bits = [collapse_repeated_cells(para.text) for para in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    cells = []
                    for cell in row.cells:
                        text = flatten(cell.text.replace("\x07", ""))
                        if text and text not in cells:
                            cells.append(text)
                    if cells:
                        bits.append(" | ".join(cells))
            joined = "\n".join(bit for bit in bits if bit)
            if joined.strip():
                return joined
        except Exception:
            pass

        try:
            return extract_docm_text(sheet_path)
        except Exception:
            pass

    try:
        import win32com.client  # type: ignore

        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(sheet_path.resolve()), ReadOnly=True)
        try:
            return doc.Content.Text
        finally:
            doc.Close(False)
            word.Quit()
    except Exception as exc:
        raise SystemExit(
            f"Could not read daily sheet {sheet_path.name}.\n"
            "Install python-docx with:  py -3 -m pip install python-docx\n"
            f"Details: {exc}"
        )


DAY_HEADING_RE = re.compile(
    r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
    r"(?:\s+\d{1,2}(?:st|nd|rd|th)?\b.*)?$",
    re.IGNORECASE,
)


def split_weekly_sheet_by_day(sheet_text: str) -> dict:
    """Split a Mon-Sun weekly duty sheet into per-day text blocks."""
    by_day = {day: [] for day in DAYS}
    current = ""
    for raw in sheet_text.splitlines():
        line = flatten(raw)
        if not line:
            continue
        match = DAY_HEADING_RE.match(line)
        if match:
            current = match.group(1).capitalize()
            by_day[current].append(line)
            continue
        # Also catch uppercase-only headings like "SATURDAY" alone
        upper = line.upper().strip()
        if upper in {d.upper() for d in DAYS}:
            current = upper.capitalize()
            by_day[current].append(line)
            continue
        if current:
            by_day[current].append(line)
    return {day: "\n".join(parts) for day, parts in by_day.items() if parts}


def normalize_sheet(text: str) -> str:
    text = text.replace("\u00a0", " ").lower()
    text = text.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text)


def extract_duty_rows(sheet_text: str) -> List[str]:
    rows = []
    for raw in sheet_text.splitlines():
        line = collapse_repeated_cells(flatten(raw))
        if len(line) < 8:
            continue
        if re.search(r"name of driver|job analysis|locomotive drivers", line, re.IGNORECASE):
            continue
        if line not in rows:
            rows.append(line)
    return rows


def distinctive_needles(item: CorkDriverItem) -> List[str]:
    blob = (item.cork_duty + " " + " ".join(t.label() for t in item.related_trains)).lower()
    needles = []
    for place, aliases in PLACE_ALIASES:
        if place in blob:
            needles.extend(aliases)
    if "conduct" in item.cork_duty.lower() and "conduct" not in needles:
        needles.append("conduct")
    return unique(needles)


def digits_only(text: str) -> str:
    return re.sub(r"\D+", "", text)


def times_present_in(text: str, times: Sequence[str]) -> List[str]:
    """Match 1047, 10.47 or 10:47 on the daily sheet."""
    compact = digits_only(text)
    dotted = normalize_sheet(text)
    found = []
    for hhmm in times:
        hour, minute = hhmm[:2], hhmm[2:]
        hour_n = str(int(hour))
        if hhmm in compact:
            found.append(hhmm)
            continue
        patterns = (
            f"{hour}.{minute}",
            f"{hour}:{minute}",
            f"{hour_n}.{minute}",
            f"{hour_n}:{minute}",
            f"{hour_n}{minute}",
        )
        if any(p in dotted or p in compact for p in patterns):
            found.append(hhmm)
    return unique(found)


def _item_times(item: CorkDriverItem) -> List[str]:
    times = unique(time_to_hhmm(t) for t in re.findall(r"\d{1,2}\.\d{2}", item.cork_duty))
    return times or item.times_hhmm()


def _best_duty_row(item: CorkDriverItem, rows: Sequence[str]) -> Tuple[str, int, List[str], List[str]]:
    times = _item_times(item)
    needles = [n.strip() for n in distinctive_needles(item) if n.strip()]
    best_row = ""
    best_score = -1
    best_times: List[str] = []
    best_needles: List[str] = []
    for row in rows:
        hit_times = times_present_in(row, times)
        norm = normalize_sheet(row)
        hit_needles = [n for n in needles if n in norm]
        score = (3 * len(hit_times)) + (3 * len(hit_needles))
        if times and len(hit_times) == len(times):
            score += 6
        for train_id in item.train_ids():
            if train_id.lower() in norm:
                score += 5
        if score > best_score:
            best_score = score
            best_row = collapse_repeated_cells(flatten(row))
            best_times = hit_times
            best_needles = hit_needles
    return best_row, best_score, best_times, best_needles


def compare_item_to_sheet(item: CorkDriverItem, sheet_text: str) -> None:
    rows = extract_duty_rows(sheet_text)
    needles = [n.strip() for n in distinctive_needles(item) if n.strip()]
    times = _item_times(item)

    row, score, row_times, row_needles = _best_duty_row(item, rows) if rows else ("", -1, [], [])
    if row and score > 0:
        item.sheet_match = collapse_repeated_cells(row)[:300]

    found_times = times_present_in(sheet_text, times)
    sheet_norm = normalize_sheet(sheet_text)
    found_needles = [n for n in needles if n in sheet_norm]
    missing_times = [t for t in times if t not in found_times]

    for train_id in item.train_ids():
        if train_id.lower() in sheet_norm:
            item.sheet_status = "FOUND"
            item.sheet_note = f"train ID {train_id}"
            return

    place_ok = (not needles) or bool(found_needles)

    if times and not missing_times and place_ok:
        bits = [", ".join(found_times)]
        if found_needles:
            bits.append(found_needles[0])
        item.sheet_status = "FOUND"
        item.sheet_note = " and ".join(bits)
        if not item.sheet_match and row:
            item.sheet_match = collapse_repeated_cells(row)[:300]
        return

    if missing_times and found_times:
        item.sheet_status = "MISSING"
        item.sheet_note = (
            f"on sheet: {', '.join(found_times)}; "
            f"missing {', '.join(missing_times)}"
            + (f" / {needles[0]}" if needles and not found_needles else "")
        )
        return

    if found_times and needles and not found_needles:
        item.sheet_status = "MISSING"
        item.sheet_note = (
            f"time {', '.join(found_times)} is on the sheet, but not with {needles[0]}"
        )
        return

    item.sheet_status = "MISSING"
    item.sheet_note = "not found in Job Analysis"
    if not item.sheet_match:
        item.sheet_match = ""


def find_week_dirs(root: Path) -> List[Path]:
    dirs = []
    if not root.is_dir():
        return dirs
    for path in sorted(root.iterdir(), key=lambda p: p.name.lower(), reverse=True):
        if path.is_dir() and re.search(r"WEEK[- ]ENDING", path.name, re.IGNORECASE):
            dirs.append(path)
    return dirs


def find_week_dirs_from_roots(roots: Sequence[Path]) -> List[Path]:
    found: List[Path] = []
    seen = set()
    for root in roots:
        for week in find_week_dirs(root):
            key = str(week).lower()
            if key not in seen:
                seen.add(key)
                found.append(week)
    return found



def find_day_pdf(week_dir: Path, day: str) -> Path:
    pdf = week_dir / DAY_PDF_NAME[day]
    if pdf.exists():
        return pdf
    matches = list(week_dir.glob(f"{day}*.pdf"))
    if matches:
        return matches[0]
    raise SystemExit(f"No {day} PDF found in {week_dir}")


def find_day_sheet(week_dir: Path, day: str, explicit: Optional[Path]) -> Optional[Path]:
    if explicit:
        path = explicit if explicit.is_file() else week_dir / explicit
        if not path.exists():
            raise SystemExit(f"Daily sheet not found: {path}")
        return path

    patterns = [
        f"DailySheet {day}*.docx",
        f"DailySheet {day}*.docm",
        f"{day} *.docx",
        f"{day} *.docm",
        f"*{day}*.docx",
        f"*{day}*.docm",
    ]
    for pattern in patterns:
        hits = [p for p in week_dir.glob(pattern) if not p.name.lower().startswith("~$")]
        hits = [p for p in hits if "checklist" not in p.name.lower()]
        if hits:
            return sorted(hits)[0]
    return None


def look_for_on_sheet(item: CorkDriverItem) -> str:
    times = unique(time_to_hhmm(t) for t in re.findall(r"\d{1,2}\.\d{2}", item.cork_duty))
    if not times:
        local_trains = [
            t for t in item.related_trains
            if re.search(
                r"cork|killarney|thurles|mallow|tralee|limerick|portarlington",
                t.route,
                re.IGNORECASE,
            )
        ]
        times = unique(time_to_hhmm(t.time) for t in local_trains)
    places = distinctive_needles(item)
    bits = []
    if times:
        bits.append("/".join(times[:3]))
    useful_places = [p for p in places if p not in {"mallow", " mw ", "mw–", "mw -", "mw-"}]
    if useful_places:
        bits.append(useful_places[0])
    elif places:
        bits.append(places[0])
    return ", ".join(bits) if bits else "Cork / Mallow / Tralee wording on the job"


def format_paste_for_daily_sheet(
    day: str,
    items: Sequence[CorkDriverItem],
    carry: Sequence[str] = (),
) -> str:
    """Plain text for copy/paste into the Word daily sheet (no compare)."""
    lines = [
        f"{day.upper()} — Cork / Mallow / Tralee extract",
        "Copy Cork / Mallow / Tralee lines below into your Word daily sheet.",
        "=" * 60,
        "",
    ]
    if not items:
        lines.append("No Cork / Mallow / Tralee Driver items found for this day.")
        lines.append("")
    else:
        for index, item in enumerate(items, 1):
            lines.append(f"{index}. {item.cork_duty}")
            hint = look_for_on_sheet(item)
            if hint:
                lines.append(f"   Sheet hint: {hint}")
            if item.circular_page:
                lines.append(f"   Circular page: {item.circular_page}")
            lines.append("")

    if carry:
        lines.append("-" * 60)
        lines.append("Carry forward (other day — do not paste on this sheet):")
        for note in carry:
            lines.append(f"  - {note}")
        lines.append("")

    return "\n".join(lines)


def extract_for_daily_sheet(
    pdf_path: Path,
    day: Optional[str] = None,
) -> Tuple[dict, dict, str]:
    """
    Upload-only extract: day pages PDF or full weekly circular.
    day=None extracts every day found in a full circular.
    Returns (items_by_day, carry_by_day, paste_text).
    """
    items_by_day: dict = {}
    carry_by_day: dict = {}

    day_texts = split_circular_by_day(pdf_path)
    use_split = bool(day_texts) and (day is None or day in day_texts)

    if use_split:
        target_days = DAYS if day is None else (day,)
        for d in target_days:
            text = day_texts.get(d, "")
            if not text.strip():
                items_by_day[d] = []
                carry_by_day[d] = []
                continue
            items, carry = parse_day_text(text, d, source_name=pdf_path.name)
            items_by_day[d] = items
            carry_by_day[d] = carry
    else:
        if day is None:
            raise ValueError(
                "Could not detect Monday–Sunday sections in this PDF. "
                "Either upload the full weekly circular, or pick which day this file is."
            )
        text = extract_pdf_text(pdf_path)
        if not text.strip():
            raise ValueError(f"No text could be read from {pdf_path.name}")
        items, carry = parse_day_text(text, day, source_name=pdf_path.name)
        items_by_day[day] = items
        carry_by_day[day] = carry

    paste_parts: List[str] = []
    for d in DAYS:
        if d not in items_by_day:
            continue
        paste_parts.append(
            format_paste_for_daily_sheet(d, items_by_day[d], carry_by_day.get(d, []))
        )
    if not paste_parts:
        raise ValueError("No Cork / Mallow / Tralee Driver content found in that PDF.")
    return items_by_day, carry_by_day, "\n\n".join(paste_parts)


def format_checklist(
    day: str,
    week_dir: Path,
    items: Sequence[CorkDriverItem],
    carry: Sequence[str],
    sheet_path: Optional[Path],
) -> str:
    lines = [
        f"{day.upper()} - Cork Driver checklist",
        f"Week folder: {week_dir.name}",
        f"Circular PDF: {DAY_PDF_NAME[day]}",
        f"Daily sheet: {sheet_path.name if sheet_path else '(not built yet - tick by hand)'}",
        "=" * 72,
        "",
    ]
    if not items:
        lines.append("No Cork Driver crew arrangements found on this day's circular pages.")
        lines.append("")
    else:
        missing = sum(1 for item in items if item.sheet_status == "MISSING")
        found = sum(1 for item in items if item.sheet_status == "FOUND")
        if sheet_path:
            lines.append(f"Compared with daily sheet: {found} found, {missing} missing, {len(items)} total.")
            lines.append("")
        for index, item in enumerate(items, 1):
            box = "[x]" if item.sheet_status == "FOUND" else "[ ]"
            lines.append(f"{index}. {box}  {item.cork_duty}")
            if item.heading_title:
                lines.append(f"    Section: {item.heading_title}")
            if item.related_trains:
                labels = unique(t.label() for t in item.related_trains)
                lines.append(f"    Related trains: {'; '.join(labels)}")
            if item.circular_page:
                lines.append(f"    Circular page: {item.circular_page}")
            lines.append(f"    Look on sheet for: {look_for_on_sheet(item)}")
            lines.append(f"    On {day} sheet?:  {item.sheet_status}"
                         + (f"  ({item.sheet_note})" if item.sheet_note else ""))
            lines.append("")

    lines.append("-" * 72)
    lines.append("CARRY FORWARD (not this day's sheet)")
    if carry:
        for note in carry:
            lines.append(f"  - {note}")
    else:
        lines.append("  None found.")
    lines.append("")
    lines.append("Tick each item while building the daily sheet.")
    lines.append("When the Word sheet is saved in this folder, run the checker again to mark Found/Missing.")
    lines.append("")
    return "\n".join(lines)


def format_compare_report(
    day: str,
    pdf_name: str,
    sheet_name: str,
    items: Sequence[CorkDriverItem],
    carry: Sequence[str],
) -> str:
    missing = [item for item in items if item.sheet_status == "MISSING"]
    found = [item for item in items if item.sheet_status == "FOUND"]
    other = [item for item in items if item.sheet_status not in {"MISSING", "FOUND"}]
    lines = [
        f"{day.upper()} COMPARE - circular vs daily sheet",
        f"Circular PDF: {pdf_name}",
        f"Daily sheet: {sheet_name}",
        f"Missing: {len(missing)}   Found: {len(found)}   Total: {len(items)}",
        "=" * 72,
        "",
        "MISSING (put these on the daily sheet)",
        "-" * 72,
    ]
    if not missing:
        lines.append("None. Every Cork Driver item was found on the sheet.")
        lines.append("")
    else:
        for index, item in enumerate(missing, 1):
            lines.append(f"{index}. FROM CIRCULAR:")
            lines.append(f"   {item.cork_duty}")
            lines.append(f"   Look for: {look_for_on_sheet(item)}")
            lines.append(f"   ON DAILY SHEET: {item.sheet_match or 'not found'}")
            if item.sheet_note:
                lines.append(f"   Note: {item.sheet_note}")
            lines.append("")

    lines += ["FOUND (already on the daily sheet)", "-" * 72]
    if not found:
        lines.append("None.")
        lines.append("")
    else:
        for index, item in enumerate(found, 1):
            lines.append(f"{index}. FROM CIRCULAR:")
            lines.append(f"   {item.cork_duty}")
            lines.append(f"   Look for: {look_for_on_sheet(item)}")
            lines.append(f"   ON DAILY SHEET: {item.sheet_match or item.sheet_note or 'matched'}")
            lines.append("")

    if other:
        lines += ["NOT CHECKED", "-" * 72]
        for item in other:
            lines.append(f"- {item.cork_duty}")
        lines.append("")

    lines += ["CARRY FORWARD (not this day's sheet)", "-" * 72]
    if carry:
        for note in carry:
            lines.append(f"  - {note}")
    else:
        lines.append("  None found.")
    lines.append("")
    lines.append("Missing = go look at the sheet. Times on the sheet can still be the old working.")
    lines.append("")
    return "\n".join(lines)


def format_compare_csv(
    day: str,
    items: Sequence[CorkDriverItem],
    carry: Sequence[str],
) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["Day", "Status", "From circular", "Look on sheet for", "On daily sheet", "Note"]
    )
    missing = [item for item in items if item.sheet_status == "MISSING"]
    found = [item for item in items if item.sheet_status == "FOUND"]
    other = [item for item in items if item.sheet_status not in {"MISSING", "FOUND"}]
    for item in missing + found + other:
        writer.writerow(
            [
                day,
                item.sheet_status,
                item.cork_duty,
                look_for_on_sheet(item),
                item.sheet_match,
                item.sheet_note,
            ]
        )
    for note in carry:
        writer.writerow([day, "CARRY FORWARD", note, "", "", ""])
    return buffer.getvalue()


def run_week_compare(
    circular_pdf: Path,
    weekly_sheet: Path,
) -> Tuple[dict, dict, str, str]:
    """
    Full circular + Mon-Sun weekly Word sheet.
    Returns (items_by_day, carry_by_day, report_text, csv_text).
    """
    day_texts = split_circular_by_day(circular_pdf)
    if not day_texts:
        raise SystemExit(f"Could not find day sections in {circular_pdf.name}")

    sheet_text = read_word_text(weekly_sheet)
    sheet_by_day = split_weekly_sheet_by_day(sheet_text)

    items_by_day = {}
    carry_by_day = {}
    for day in DAYS:
        text = day_texts.get(day, "")
        if not text.strip():
            items_by_day[day] = []
            carry_by_day[day] = []
            continue
        items, carry = parse_day_text(text, day, source_name=circular_pdf.name)
        day_sheet = sheet_by_day.get(day, "")
        if day_sheet:
            for item in items:
                compare_item_to_sheet(item, day_sheet)
        else:
            for item in items:
                item.sheet_status = "MISSING"
                item.sheet_note = f"no {day} block found on weekly sheet"
        items_by_day[day] = items
        carry_by_day[day] = carry

    report = format_week_compare_report(
        circular_pdf.name, weekly_sheet.name, items_by_day, carry_by_day, sheet_by_day
    )
    csv_text = format_week_compare_csv(items_by_day, carry_by_day)
    return items_by_day, carry_by_day, report, csv_text


def format_week_compare_report(
    circular_name: str,
    sheet_name: str,
    items_by_day: dict,
    carry_by_day: dict,
    sheet_by_day: dict,
) -> str:
    total_items = sum(len(v) for v in items_by_day.values())
    total_missing = sum(
        1 for items in items_by_day.values() for item in items if item.sheet_status == "MISSING"
    )
    total_found = sum(
        1 for items in items_by_day.values() for item in items if item.sheet_status == "FOUND"
    )
    lines = [
        "WEEK COMPARE - circular vs weekly daily sheet",
        f"Circular PDF: {circular_name}",
        f"Weekly sheet: {sheet_name}",
        f"Missing: {total_missing}   Found: {total_found}   Total: {total_items}",
        "=" * 72,
        "",
        "SUMMARY BY DAY",
        "-" * 72,
    ]
    for day in DAYS:
        items = items_by_day.get(day, [])
        missing = sum(1 for item in items if item.sheet_status == "MISSING")
        found = sum(1 for item in items if item.sheet_status == "FOUND")
        sheet_ok = "yes" if sheet_by_day.get(day) else "NO SHEET BLOCK"
        lines.append(
            f"{day:10}  items {len(items):2}   found {found:2}   missing {missing:2}   sheet: {sheet_ok}"
        )
    lines += ["", "MISSING (put these on the weekly sheet)", "-" * 72]
    miss_n = 0
    for day in DAYS:
        for item in items_by_day.get(day, []):
            if item.sheet_status != "MISSING":
                continue
            miss_n += 1
            lines.append(f"{miss_n}. [{day}] FROM CIRCULAR:")
            lines.append(f"   {item.cork_duty}")
            lines.append(f"   Look for: {look_for_on_sheet(item)}")
            lines.append(f"   ON DAILY SHEET: {item.sheet_match or 'not found'}")
            if item.sheet_note:
                lines.append(f"   Note: {item.sheet_note}")
            lines.append("")
    if miss_n == 0:
        lines.append("None. Every Cork Driver item was found on the weekly sheet.")
        lines.append("")

    lines += ["FOUND (already on the weekly sheet)", "-" * 72]
    found_n = 0
    for day in DAYS:
        for item in items_by_day.get(day, []):
            if item.sheet_status != "FOUND":
                continue
            found_n += 1
            lines.append(f"{found_n}. [{day}] FROM CIRCULAR:")
            lines.append(f"   {item.cork_duty}")
            lines.append(f"   Look for: {look_for_on_sheet(item)}")
            lines.append(f"   ON DAILY SHEET: {item.sheet_match or item.sheet_note or 'matched'}")
            lines.append("")
    if found_n == 0:
        lines.append("None.")
        lines.append("")

    lines += ["CARRY FORWARD", "-" * 72]
    any_carry = False
    for day in DAYS:
        for note in carry_by_day.get(day, []):
            any_carry = True
            lines.append(f"  [{day}] {note}")
    if not any_carry:
        lines.append("  None found.")
    lines.append("")
    lines.append("Missing = go look at the sheet. Times on the sheet can still be the old working.")
    lines.append("")
    return "\n".join(lines)


def format_week_compare_csv(items_by_day: dict, carry_by_day: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["Day", "Status", "From circular", "Look on sheet for", "On daily sheet", "Note"]
    )
    for day in DAYS:
        items = items_by_day.get(day, [])
        missing = [item for item in items if item.sheet_status == "MISSING"]
        found = [item for item in items if item.sheet_status == "FOUND"]
        other = [item for item in items if item.sheet_status not in {"MISSING", "FOUND"}]
        for item in missing + found + other:
            writer.writerow(
                [
                    day,
                    item.sheet_status,
                    item.cork_duty,
                    look_for_on_sheet(item),
                    item.sheet_match,
                    item.sheet_note,
                ]
            )
        for note in carry_by_day.get(day, []):
            writer.writerow([day, "CARRY FORWARD", note, "", "", ""])
    return buffer.getvalue()


def write_checklist(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def choose_from_list(title: str, options: Sequence[str]) -> str:
    print(title)
    for index, option in enumerate(options, 1):
        print(f"  {index}. {option}")
    while True:
        raw = input("Enter number: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("Invalid choice.")


def resolve_week_dir(roots: Sequence[Path], week_arg: Optional[str]) -> Path:
    weeks = find_week_dirs_from_roots(roots)
    if week_arg:
        for root in roots:
            exact = root / week_arg
            if exact.is_dir():
                return exact
        matches = [w for w in weeks if week_arg.lower() in w.name.lower()]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise SystemExit("More than one week matched. Use the full folder name.")
        raise SystemExit(f"Week folder not found: {week_arg}")
    for root in roots:
        if (root / "Monday_pages.pdf").exists() or (root / "Tuesday_pages.pdf").exists():
            return root
    if not weeks:
        searched = "\n  ".join(str(r) for r in roots)
        raise SystemExit(
            "No WEEK-ENDING folders found.\n"
            "Put CorkDriverChecker.exe in the same folder as the week folders "
            "(the ones that contain Monday_pages.pdf).\n"
            f"Looked in:\n  {searched}"
        )
    if len(weeks) == 1:
        return weeks[0]
    chosen = choose_from_list("Which week?", [w.name for w in weeks])
    return next(w for w in weeks if w.name == chosen)


def resolve_days(day_arg: Optional[str]) -> List[str]:
    if day_arg:
        if day_arg.lower() in {"all", "week"}:
            return list(DAYS)
        for day in DAYS:
            if day.lower().startswith(day_arg.lower()):
                return [day]
        raise SystemExit(f"Unknown day: {day_arg}")
    choice = choose_from_list(
        "Which day? (Monday against Monday sheet)",
        list(DAYS) + ["All days (separate checklist for each)"],
    )
    if choice.startswith("All"):
        return list(DAYS)
    return [choice]


def process_day(
    week_dir: Path,
    day: str,
    sheet_arg: Optional[Path],
) -> Path:
    pdf_path = find_day_pdf(week_dir, day)
    items, carry = parse_day_pdf(pdf_path, day)
    sheet_path = find_day_sheet(week_dir, day, sheet_arg)
    if sheet_path:
        sheet_text = read_word_text(sheet_path)
        for item in items:
            compare_item_to_sheet(item, sheet_text)
    content = format_checklist(day, week_dir, items, carry, sheet_path)
    out_path = week_dir / f"{day}_Cork_Driver_checklist.txt"
    write_checklist(out_path, content)
    print(content)
    print(f"Saved: {out_path}")
    if sheet_path:
        compare = format_compare_report(
            day, pdf_path.name, sheet_path.name, items, carry
        )
        compare_path = week_dir / f"{day}_Cork_Driver_compare.txt"
        write_checklist(compare_path, compare)
        csv_path = week_dir / f"{day}_Cork_Driver_compare.csv"
        write_checklist(csv_path, format_compare_csv(day, items, carry))
        print(compare)
        print(f"Saved: {compare_path}")
        print(f"Saved: {csv_path}")
        out_path = compare_path
    print()
    try:
        os.startfile(str(out_path))
    except Exception:
        try:
            os.startfile(str(week_dir))
        except Exception:
            pass
    return out_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cork Driver checker: one day, or full circular vs weekly sheet."
    )
    parser.add_argument("--week", help="Week folder name, or part of it (e.g. 27TH SEPTEMBER)")
    parser.add_argument("--day", help="Monday, Tuesday, ... or all")
    parser.add_argument("--sheet", help="Path to that day's Word daily sheet")
    parser.add_argument(
        "--full-circular",
        help="Full weekly circular PDF (e.g. 4255.pdf) for whole-week mode",
    )
    parser.add_argument(
        "--weekly-sheet",
        help="Mon-Sun weekly Word daily sheet (e.g. 21 Sep to 27 Sep.docm)",
    )
    parser.add_argument(
        "--root",
        help="Folder that contains the WEEK-ENDING folders",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    roots = [Path(args.root)] if args.root else search_roots()
    print("Cork Driver Checker")
    print("=" * 40)

    if args.full_circular or args.weekly_sheet:
        if not args.full_circular or not args.weekly_sheet:
            raise SystemExit("Whole-week mode needs both --full-circular and --weekly-sheet")
        circular = Path(args.full_circular)
        weekly = Path(args.weekly_sheet)
        if not circular.is_file():
            for root in roots:
                candidate = root / args.full_circular
                if candidate.is_file():
                    circular = candidate
                    break
        if not weekly.is_file():
            for root in roots:
                candidate = root / args.weekly_sheet
                if candidate.is_file():
                    weekly = candidate
                    break
        if not circular.is_file():
            raise SystemExit(f"Circular PDF not found: {args.full_circular}")
        if not weekly.is_file():
            raise SystemExit(f"Weekly sheet not found: {args.weekly_sheet}")

        print("Whole week: full circular -> Mon-Sun weekly sheet.")
        print()
        items_by_day, carry_by_day, report, csv_text = run_week_compare(circular, weekly)
        out_dir = circular.parent
        report_path = out_dir / "Week_Cork_Driver_compare.txt"
        csv_path = out_dir / "Week_Cork_Driver_compare.csv"
        write_checklist(report_path, report)
        write_checklist(csv_path, csv_text)
        print(report)
        print(f"Saved: {report_path}")
        print(f"Saved: {csv_path}")
        try:
            os.startfile(str(report_path))
        except Exception:
            pass
        return 0

    print("Checks one day at a time (Monday circular -> Monday sheet).")
    print()
    week_dir = resolve_week_dir(roots, args.week)
    days = resolve_days(args.day)
    sheet = Path(args.sheet) if args.sheet else None
    print(f"Week: {week_dir.name}")
    print()
    for day in days:
        process_day(week_dir, day, sheet if len(days) == 1 else None)
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if exc.code not in (0, None) and str(exc):
            print(exc)
    except Exception as exc:
        code = 1
        print(f"Error: {exc}")
    if getattr(sys, "frozen", False) or sys.stdin.isatty():
        pause_on_exit()
    raise SystemExit(code or 0)
