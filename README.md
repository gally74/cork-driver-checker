# Cork Driver Checker

Private GitHub Pro app. Checks **one day at a time** (Monday circular against Monday daily sheet).

Do not commit weekly circular PDFs or daily sheets. Upload them in the browser instead.

## On the work laptop (no .exe / .py / .bat)

1. Open this repository on GitHub.
2. Click **Code** → **Codespaces** → **Create codespace on main**.
3. Wait until the checker page opens (port 8501). If it does not, open the Ports tab and click the forwarded **8501** link.
4. Choose **Monday**, upload `Monday_pages.pdf`, click **Build checklist**.
5. Download the `.txt` and tick those items onto the daily sheet.
6. Stop the codespace when you are finished (Codespaces → Stop) so it does not keep using your Pro hours.

GitHub Pro includes Codespaces hours. A weekly Monday check is a few minutes.

## Local (home PC)

```text
pip install -r requirements.txt
streamlit run streamlit_app.py
```
