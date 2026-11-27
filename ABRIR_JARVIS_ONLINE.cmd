@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0jarvis.ps1" -Online
if errorlevel 1 pause
