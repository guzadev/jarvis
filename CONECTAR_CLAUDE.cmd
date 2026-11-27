@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0conectar-claude.ps1"
if errorlevel 1 pause
