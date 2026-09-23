# Cork Driver Checker

Private GitHub Pro app. Checks Cork Driver amendments from the weekly circular
against your daily sheets.

Do not commit weekly circular PDFs or daily sheets. Upload them in the browser instead.

## Modes

- **One day** — one day's pages PDF + that day's Word sheet (while you build Monday, etc.).
- **Whole week** — full circular PDF (e.g. `4255.pdf`) + Mon-Sun weekly daily sheet
  (e.g. `21 Sep to 27 Sep.docm`) → one week miss-list.

## On the work laptop (no .exe / .py / .bat)

1. Open this repository on GitHub.
2. Click **Code** → **Codespaces** → **Create codespace on main**.
3. Wait until the terminal shows Streamlit is ready.
4. Open the **Ports** tab → **8501** → globe / **Open in Browser**
   (not the in-editor Simple Browser).
5. If the port is Private, right-click **8501** → Port Visibility → **Public**.
6. Choose **One day** or **Whole week**, upload the files, then compare.
7. Download the compare `.txt` / `.csv`. **Missing** items still need to go on the sheet.
8. Stop the codespace when finished so it does not keep using Pro hours.

### If you get HTTP 404

```bash
bash start_checker.sh
```

Then open **Ports** → **8501** → globe. After a code update: Source Control → **Pull**, then run that again.

## Local (home PC)

```text
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Whole week from the command line:

```text
py -3 cork_driver_checker.py --full-circular 4255.pdf --weekly-sheet "21 Sep to 27 Sep.docm"
```
