@echo off
REM Madeleine service launcher — Scheduled Task target (logon, restart x3)
set PYTHONUTF8=1
cd /d E:\git\Memory-Madeleine
.venv\Scripts\python.exe -m uvicorn src.agent.api:app --host 127.0.0.1 --port 8011 >> data\logs\service.log 2>&1
