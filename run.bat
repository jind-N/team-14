@echo off
cd /d %~dp0
if not exist .venv ( py -3 -m venv .venv || python -m venv .venv )
call .venv\Scripts\python.exe -m pip install -r requirements.txt
call .venv\Scripts\python.exe -m streamlit run heldby_v2.py --server.address=127.0.0.1
pause