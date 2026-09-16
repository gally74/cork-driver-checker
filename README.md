# Cork Driver Checker

Private GitHub Pro app. Checks **one day at a time** (Monday circular against Monday daily sheet).

Do not commit weekly circular PDFs or daily sheets. Upload them in the browser instead.

## On the work laptop (no .exe / .py / .bat)

1. Open this repository on GitHub.
2. Click **Code** → **Codespaces** → **Create codespace on main**.
3. Wait until the terminal says Streamlit is running.
4. Open the **Ports** tab (bottom). On port **8501**, click the globe / **Open in Browser**.
   Do not use the in-editor Simple Browser — that shows "refused to connect".
5. If the port is Private, right-click **8501** → Port Visibility → **Public**, then open it again.
6. Choose **Monday** and upload `Monday_pages.pdf`.
7. To compare, also upload that day's Word daily sheet, then click **Compare**.
8. Download the compare `.txt` (or `.csv`). **Missing** items still need to go on the sheet.
9. Stop the codespace when you are finished (Codespaces → Stop) so it does not keep using your Pro hours.

If the codespace was already running before this update: Source Control → Pull, or create a new codespace.

GitHub Pro includes Codespaces hours. A weekly Monday check is a few minutes.

## Local (home PC)

```text
pip install -r requirements.txt
streamlit run streamlit_app.py
```
