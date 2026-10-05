@echo off
chcp 65001 >nul
cd /d YOUR_PATH\wecom
echo 正在启动企业微信接入服务（0.0.0.0:8765）...
"YOUR_PATH\AppData\Local\Programs\Python\Python311\python.exe" -u run.py
pause
