@echo off
rem USTC course grab bot - manual start (double click)
rem Starts the bot in background (headless, no window). Safe to run twice:
rem if the bot is already running, it will not start a second instance.
setlocal
set "HERE=%~dp0"
set "EXE=%HERE%.venv\Scripts\pythonw.exe"
set "SCRIPT=%HERE%run_bot.pyw"

if not exist "%EXE%" (
    echo [ERROR] Python venv not found:
    echo         %EXE%
    echo Please create .venv first - see README.
    pause
    exit /b 1
)
if not exist "%SCRIPT%" (
    echo [ERROR] Launcher not found: %SCRIPT%
    pause
    exit /b 1
)

powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'pythonw.exe' -or $_.Name -eq 'python.exe') -and $_.CommandLine -match 'grabbing\.py|run_bot\.pyw' }) { exit 1 } else { exit 0 }"
if errorlevel 1 (
    echo [OK] Bot is already running - no action needed.
    echo      Log: %HERE%run.log
    ping -n 5 127.0.0.1 >nul
    exit /b 0
)

start "USTC_Course_Grab_Bot" "%EXE%" "%SCRIPT%"
echo [OK] Bot started in background.
echo      Log: %HERE%run.log
ping -n 5 127.0.0.1 >nul
