# Cork Driver Checker

Private GitHub Pro app. Checks **one day at a time** (Monday circular against Monday daily sheet).

Do not commit weekly circular PDFs or daily sheets. Upload them in the browser instead.

## On the work laptop (no .exe / .py / .bat)

1. Open this repository on GitHub.
2. Click **Code** → **Codespaces** → **Create codespace on main**.
3. Wait until the terminal shows Streamlit is ready (a local URL / “You can now view your Streamlit app”).
4. Open the **Ports** tab (bottom). On port **8501**, click the globe / **Open in Browser**.
   Do not use the in-editor Simple Browser — that shows "refused to connect".
5. If the port is Private, right-click **8501** → Port Visibility → **Public**, then open it again.
6. Choose the day and upload that day's pages PDF.
7. To compare, also upload that day's Word daily sheet, then click **Compare**.
8. Download the compare `.txt` (or `.csv`). **Missing** items still need to go on the sheet.
9. Stop the codespace when you are finished (Codespaces → Stop) so it does not keep using your Pro hours.

### If you get HTTP 404 on the checker page

The Codespace is open, but Streamlit is not serving yet (or the old start died).

1. In Codespaces, open a **new Terminal** (`+` next to the terminal tabs).
2. Run:

```bash
bash start_checker.sh
```

3. Wait until you see **You can now view your Streamlit app**.
4. Open **Ports** → **8501** → globe (Open in Browser).
5. If it still 404s: set **8501** to **Public**, then open the globe again.

After a code update: Source Control → **Pull**, then run `bash start_checker.sh` again (or create a new codespace).

GitHub Pro includes Codespaces hours. A weekly Monday check is a few minutes.

## Local (home PC)

```text
pip install -r requirements.txt
streamlit run streamlit_app.py
```
