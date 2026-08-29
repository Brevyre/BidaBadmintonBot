@echo off
set PYTHONUTF8=1
cd /d "%~dp0"
echo Starting BBBot... (close this window or press Ctrl+C to stop)
py bot.py
echo.
echo BBBot has stopped.
pause
