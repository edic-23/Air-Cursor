@echo off
REM Launch Air Cursor using the project's virtual environment.
cd /d "%~dp0"
".venv\Scripts\pythonw.exe" -m air_cursor.main
