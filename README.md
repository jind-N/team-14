\# Team 14 — Footprint Receipt (Personal Data Footprint Auditor)



A local-first privacy tool that reads exported data archives (like Google Takeout / Spotify exports) and generates an \*\*evidence-backed “what to review first” receipt\*\*.



\## Hackathon checkpoint #1 (current progress)

\- ✅ App runs locally (Streamlit)

\- ✅ Basic parser for Google Search MyActivity JSON format

\- ✅ Downloadable “privacy action receipt” report

\- ✅ Works offline (no server needed)



\## How to run (Windows)

```powershell

python -m venv .venv

.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt

.\\.venv\\Scripts\\python.exe -m streamlit run app.py

