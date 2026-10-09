@echo off
cd /d "%~dp0"
netstat -ano | findstr ":8765" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo [wecom] already running on 8765, skip.
    exit /b 0
)
echo [wecom] starting callback service 0.0.0.0:8765 ...
start "WecomCallback" /min "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" -u run.py
exit /b 0