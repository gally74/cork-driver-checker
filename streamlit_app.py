"""Browser checker for Cork Driver crew arrangements.

Modes:
  - Extract for daily sheet: upload PDF → copy/paste text (website default)
  - Extract possessions: Absolute Possessions table → Cork East / Cork–Mallow / Mallow–Tralee
  - One day: day PDF + that day's Word sheet (home/compare — unchanged)
  - Whole week: full circular PDF + Mon-Sun weekly Word sheet (unchanged)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from cork_driver_checker import (
    DAYS,
    compare_item_to_sheet,
    extract_for_daily_sheet,
    format_checklist,
    format_compare_csv,
    format_compare_report,
    parse_day_pdf,
    read_word_text,
    run_week_compare,
)

# Possession extract is optional at import time so Driver modes still load
# if Streamlit Cloud is mid-redeploy. Loaded when that mode runs.
try:
    from possession_extract import (
        extract_possessions_from_pdfs,
        format_possessions_for_day,
        format_possessions_simple,
        prepare_slots,
    )

    _POSSESSION_IMPORT_ERROR = None
except Exception as _poss_exc:  # pragma: no cover - cloud deploy edge
    extract_possessions_from_pdfs = None  # type: ignore
    format_possessions_for_day = None  # type: ignore
    format_possessions_simple = None  # type: ignore
    prepare_slots = None  # type: ignore
    _POSSESSION_IMPORT_ERROR = _poss_exc


st.set_page_config(page_title="Cork / Mallow / Tralee Checker", layout="centered")

st.title("Cork / Mallow / Tralee Checker")
st.caption(
    "Extract for daily sheet matches Cork Roster → Scan Circulars. "
    "Extract possessions always uses Sunday pages / full circular "
    "(Absolute Possessions sit at the end). "
    "Compare modes still check Driver items against Word."
)

mode = st.radio(
    "Mode",
    ["Extract for daily sheet", "Extract possessions", "One day", "Whole week"],
    horizontal=True,
    help=(
        "Extract = Scan Circulars notes. "
        "Possessions = Absolute Possessions for Cork East / Cork–Mallow / Mallow–Tralee. "
        "One day / Whole week = Driver compare (unchanged)."
    ),
)

if mode == "Extract for daily sheet":
    st.subheader("Upload → Extract → Copy into Word")
    st.info(
        "Same extract as **Weekly Rosters → Scan Circulars**: Cork / Mallow / Tralee "
        "Driver notes, engineering works, bus substitutions, cancellations, and other "
        "CMT route impacts. Paste under the red day heading (or notes band) in Word."
    )
    pdf_file = st.file_uploader(
        "Upload circular PDF (full week e.g. 4255.pdf, or one day's pages)",
        type=["pdf"],
        key="extract_pdf",
    )
    day_choice = st.selectbox(
        "Which day?",
        ["All days (full circular)"] + list(DAYS),
        index=0,
        help="Use All days for a full weekly circular. Pick a day for Monday_pages.pdf etc.",
    )
    run_extract = st.button(
        "Extract for daily sheet",
        type="primary",
        disabled=pdf_file is None,
    )

    if run_extract and pdf_file is not None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            pdf_path = tmp_dir / pdf_file.name
            pdf_path.write_bytes(pdf_file.getvalue())
            day = None if day_choice.startswith("All days") else day_choice
            try:
                notes_by_day, dates_by_day, paste_text = extract_for_daily_sheet(
                    pdf_path, day=day
                )
            except Exception as exc:
                st.error(f"Could not extract that PDF. {exc}")
                st.stop()

        total = sum(len(v) for v in notes_by_day.values())
        st.success(
            f"Extracted {total} roster note(s) (Scan Circulars style). "
            "Select the text below and copy (Ctrl+A / Ctrl+C)."
        )

        for d in DAYS:
            notes = notes_by_day.get(d)
            if notes is None:
                continue
            st.write(f"**{d}:** {len(notes)} note(s)")

        st.download_button(
            "Download extract (.txt)",
            data=paste_text.encode("utf-8"),
            file_name="circular_notes_daily_sheet.txt",
            mime="text/plain",
            key="download_extract_txt",
        )
        st.text_area("Copy this into your Word daily sheet", paste_text, height=480)

elif mode == "Extract possessions":
    st.subheader("Absolute Possessions → simple list")
    if _POSSESSION_IMPORT_ERROR is not None:
        st.error(
            "Could not load possession_extract.py on the server. "
            "Reboot the Streamlit app (Manage app → Reboot), or wait for redeploy. "
            f"Detail: {_POSSESSION_IMPORT_ERROR}"
        )
        st.stop()
    st.info(
        "Absolute Possessions are **always at the end** of the weekly circular → "
        "upload **Sunday_pages.pdf** or the **full weekly circular** (1–3 parts). "
        "Do **not** upload Monday–Saturday day PDFs. "
        "Pick a day (e.g. Monday) only to filter which slots to show — "
        "the source PDF is still Sunday / full circular. "
        "Cork East / Cork–Mallow / Mallow–Tralee only. Paste **after** Driver notes."
    )
    pdf_files = st.file_uploader(
        "Upload Sunday pages and/or full weekly circular PDF(s)",
        type=["pdf"],
        accept_multiple_files=True,
        key="poss_pdfs",
        help="Sunday_pages.pdf or full circular — not Monday_pages.pdf etc.",
    )
    day_choice = st.selectbox(
        "Show which day?",
        ["Whole week"] + list(DAYS),
        index=0,
        key="poss_day",
        help=(
            "Filters output only. Source PDF should still be Sunday pages / full circular."
        ),
    )
    major_only = st.checkbox(
        "Main / overnight only (skip short daytime plant windows)",
        value=False,
        key="poss_major",
        help="Same option as Excel Scan Possessions — keeps Up & Down and overnight blocks.",
    )
    run_poss = st.button(
        "Extract possessions",
        type="primary",
        disabled=not pdf_files,
        key="poss_run",
    )

    if run_poss and pdf_files:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            paths = []
            for f in pdf_files:
                p = tmp_dir / f.name
                p.write_bytes(f.getvalue())
                paths.append(p)
            try:
                slots = extract_possessions_from_pdfs(paths)
            except Exception as exc:
                st.error(f"Could not read possessions from that PDF. {exc}")
                st.stop()

        # Same prepare/format pipeline as Excel (overnight merge + optional major-only)
        shown = prepare_slots(slots, major_only=major_only)
        if day_choice == "Whole week":
            paste_text = format_possessions_simple(slots, major_only=major_only)
        else:
            paste_text = format_possessions_for_day(
                day_choice, slots, major_only=major_only
            )

        st.success(
            f"Showing {len(shown)} slot(s) after overnight merge"
            + (" (main / overnight only)." if major_only else ".")
            + " Same text as Cork Roster Scan Possessions."
        )
        for d in DAYS:
            n = sum(1 for s in shown if s.day == d)
            if n:
                st.write(f"**{d}:** {n}")

        st.download_button(
            "Download possessions (.txt)",
            data=paste_text.encode("utf-8"),
            file_name="possessions_cork_area.txt",
            mime="text/plain",
            key="download_poss_txt",
        )
        st.text_area("Copy this into your Word daily sheet", paste_text, height=480)

elif mode == "One day":
    day = st.selectbox("Which day?", DAYS, index=0)
    pdf_file = st.file_uploader(
        "Upload that day's circular pages (e.g. Monday_pages.pdf)",
        type=["pdf"],
        key="day_pdf",
    )
    sheet_file = st.file_uploader(
        "Optional: that day's Word daily sheet (for compare)",
        type=["docx", "docm"],
        key="day_sheet",
    )
    button_label = "Compare circular and daily sheet" if sheet_file else "Build checklist"
    run = st.button(button_label, type="primary", disabled=pdf_file is None)

    if run and pdf_file is not None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            pdf_path = tmp_dir / f"{day}_pages.pdf"
            pdf_path.write_bytes(pdf_file.getvalue())

            sheet_path = None
            if sheet_file is not None:
                sheet_path = tmp_dir / sheet_file.name
                sheet_path.write_bytes(sheet_file.getvalue())

            try:
                items, carry = parse_day_pdf(pdf_path, day)
                if sheet_path:
                    sheet_text = read_word_text(sheet_path)
                    for item in items:
                        compare_item_to_sheet(item, sheet_text)
                week_dir = Path(pdf_file.name)
                checklist = format_checklist(day, week_dir, items, carry, sheet_path)
                compare = ""
                compare_csv = ""
                if sheet_path:
                    compare = format_compare_report(
                        day, pdf_file.name, sheet_file.name, items, carry
                    )
                    compare_csv = format_compare_csv(day, items, carry)
            except Exception as exc:
                st.error(f"Could not read those files. {exc}")
                st.stop()

        missing_items = [item for item in items if item.sheet_status == "MISSING"]
        found_items = [item for item in items if item.sheet_status == "FOUND"]

        if sheet_path:
            if missing_items:
                st.error(
                    f"{len(missing_items)} missing on the daily sheet, "
                    f"{len(found_items)} found, {len(items)} total."
                )
            else:
                st.success(
                    f"All {len(items)} Cork Driver item(s) were found on the daily sheet."
                )

            st.download_button(
                f"Download {day} compare (.txt)",
                data=compare.encode("utf-8"),
                file_name=f"{day}_Cork_Driver_compare.txt",
                mime="text/plain",
                key="download_compare_txt",
            )
            st.download_button(
                f"Download {day} compare (.csv)",
                data=compare_csv.encode("utf-8"),
                file_name=f"{day}_Cork_Driver_compare.csv",
                mime="text/csv",
                key="download_compare_csv",
            )

            st.subheader("Missing")
            if not missing_items:
                st.write("None.")
            else:
                for item in missing_items:
                    st.markdown(
                        f"**Circular:** {item.cork_duty}  \n"
                        f"**On daily sheet:** {item.sheet_match or 'not found'}  \n"
                        f"**Note:** {item.sheet_note}"
                    )

            st.subheader("Found")
            if not found_items:
                st.write("None.")
            else:
                for item in found_items:
                    st.markdown(
                        f"**Circular:** {item.cork_duty}  \n"
                        f"**On daily sheet:** {item.sheet_match or item.sheet_note}"
                    )

            if carry:
                st.subheader("Carry forward")
                for note in carry:
                    st.write(f"- {note}")

            st.text_area("Full compare", compare, height=360)
        else:
            st.info(
                f"{len(items)} Cork Driver item(s). "
                "Upload the Word daily sheet as well to compare Found / Missing."
            )
            st.download_button(
                f"Download {day}_Cork_Driver_checklist.txt",
                data=checklist.encode("utf-8"),
                file_name=f"{day}_Cork_Driver_checklist.txt",
                mime="text/plain",
            )
            st.text_area("Checklist", checklist, height=420)

else:
    circular_file = st.file_uploader(
        "Upload the full weekly circular PDF (e.g. 4255.pdf)",
        type=["pdf"],
        key="week_pdf",
    )
    weekly_sheet_file = st.file_uploader(
        "Upload the weekly daily sheet (Mon-Sun Word file, e.g. 21 Sep to 27 Sep.docm)",
        type=["docx", "docm"],
        key="week_sheet",
    )
    run_week = st.button(
        "Compare whole week",
        type="primary",
        disabled=circular_file is None or weekly_sheet_file is None,
    )

    if run_week and circular_file is not None and weekly_sheet_file is not None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            circular_path = tmp_dir / circular_file.name
            sheet_path = tmp_dir / weekly_sheet_file.name
            circular_path.write_bytes(circular_file.getvalue())
            sheet_path.write_bytes(weekly_sheet_file.getvalue())
            try:
                items_by_day, carry_by_day, report, csv_text = run_week_compare(
                    circular_path, sheet_path
                )
            except Exception as exc:
                st.error(f"Could not compare those files. {exc}")
                st.stop()

        total_items = sum(len(v) for v in items_by_day.values())
        total_missing = sum(
            1
            for items in items_by_day.values()
            for item in items
            if item.sheet_status == "MISSING"
        )
        total_found = sum(
            1
            for items in items_by_day.values()
            for item in items
            if item.sheet_status == "FOUND"
        )

        if total_missing:
            st.error(
                f"Week: {total_missing} missing, {total_found} found, {total_items} total."
            )
        else:
            st.success(f"Week: all {total_items} Cork Driver item(s) found.")

        st.download_button(
            "Download week compare (.txt)",
            data=report.encode("utf-8"),
            file_name="Week_Cork_Driver_compare.txt",
            mime="text/plain",
            key="week_txt",
        )
        st.download_button(
            "Download week compare (.csv)",
            data=csv_text.encode("utf-8"),
            file_name="Week_Cork_Driver_compare.csv",
            mime="text/csv",
            key="week_csv",
        )

        st.subheader("Summary by day")
        for day in DAYS:
            items = items_by_day.get(day, [])
            missing = sum(1 for item in items if item.sheet_status == "MISSING")
            found = sum(1 for item in items if item.sheet_status == "FOUND")
            st.write(f"**{day}:** {len(items)} items — {found} found, {missing} missing")

        st.subheader("Missing")
        shown = 0
        for day in DAYS:
            for item in items_by_day.get(day, []):
                if item.sheet_status != "MISSING":
                    continue
                shown += 1
                st.markdown(
                    f"**[{day}] Circular:** {item.cork_duty}  \n"
                    f"**On daily sheet:** {item.sheet_match or 'not found'}  \n"
                    f"**Note:** {item.sheet_note}"
                )
        if shown == 0:
            st.write("None.")

        st.text_area("Full week compare", report, height=420)

st.divider()
st.markdown(
    """
**How to use**
- **Extract for daily sheet:** same rules as Cork Roster **Scan Circulars** (Driver + engineering / buses / cancellations) → copy into Word.
- **Extract possessions:** Absolute Possessions (always end of circular → **Sunday pages** or full PDF). Pick a day to filter; paste **after** Driver notes.
- **One day / Whole week:** Driver compare tools (checklist against Word) — unchanged.
- Excel: **Scan Circulars** then **Scan Possessions** (appends; does not replace notes).
"""
)
