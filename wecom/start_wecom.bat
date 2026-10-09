@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动企业微信接入服务（0.0.0.0:8765）...
"%LOCALAPPDATA%\Programs\Python\Python311\python.exe" -u run.py
pause
