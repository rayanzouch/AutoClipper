@echo off
setlocal
cd /d "%~dp0app" || exit /b 1
set "PATH=%~dp0venv\Scripts;%PATH%"
set "IMAGEIO_FFMPEG_EXE=%~dp0venv\Scripts\ffmpeg.exe"
set "PYTHONUTF8=1"
"%~dp0venv\Scripts\python.exe" -c "from dotenv import dotenv_values; c=dotenv_values('../.env'); import sys; sys.exit(0 if c.get('DISCORD_TOKEN') and all((c.get(k) or '').isdigit() for k in ('CHANNEL_INPUT_ID','CHANNEL_OUTPUT_ID')) else 1)"
if errorlevel 1 (
    echo Renseigne DISCORD_TOKEN, CHANNEL_INPUT_ID et CHANNEL_OUTPUT_ID dans le fichier .env du projet.
    pause
    exit /b 1
)
"%~dp0venv\Scripts\python.exe" bot.py
if errorlevel 1 pause
