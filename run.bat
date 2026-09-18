@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到 .venv，请先执行: py -3.14 -m venv .venv
    echo        然后: .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)
".venv\Scripts\python.exe" -m pi_tool
