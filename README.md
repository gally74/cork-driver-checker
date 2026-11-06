# Cork Driver Checker

Private GitHub Pro app for Cork Driver amendments from the weekly circular.

Do not commit weekly circular PDFs or daily sheets. Upload them in the browser instead.

## Modes

- **Extract for daily sheet** (website default) — upload the circular PDF → copy/paste text into Word. No Word upload.
- **One day** — one day's pages PDF + optional that day's Word sheet (compare / checklist). Unchanged.
- **Whole week** — full circular PDF + Mon-Sun weekly daily sheet → miss-list. Unchanged.

**Home PC Weekly Rosters → Scan Circulars** is a separate Excel tool and is not changed by this app.

## Open website (recommended on work laptop)

Host the Streamlit app so you only need a link + Upload:

1. Push this repo to GitHub (already: `gally74/cork-driver-checker`).
2. Go to [share.streamlit.io](https://share.streamlit.io) (Streamlit Community Cloud).
3. Sign in with GitHub → **New app**.
4. Repo: `gally74/cork-driver-checker` · Branch: `main` · Main file: `streamlit_app.py`.
5. Deploy. Open the app URL → **Extract for daily sheet** → Upload → Copy into Word.

Keep the app **private** if Streamlit/your plan allows (circulars are internal).

## Codespaces (fallback)

1. Open this repository on GitHub.
2. Click **Code** → **Codespaces** → **Create codespace on main**.
3. Wait until Streamlit is ready.
4. **Ports** → **8501** → globe / **Open in Browser**.
5. If the port is Private, set **Port Visibility** → **Public**.
6. Use **Extract for daily sheet**, or the compare modes if you need them.
7. Stop the codespace when finished.

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

Whole week compare from the command line:

```text
py -3 cork_driver_checker.py --full-circular 4255.pdf --weekly-sheet "21 Sep to 27 Sep.docm"
```
