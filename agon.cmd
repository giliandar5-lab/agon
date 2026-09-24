@echo off
rem Starts agon.py with Python 3 (the Codex and Antigravity plugins run Agon through this file on Windows).
rem python3 is usually a Microsoft Store stub on Windows, so: the py launcher if there is one, else python.
where py >nul 2>nul
if %errorlevel% equ 0 (py -3 "%~dp0agon.py" %*) else (python "%~dp0agon.py" %*)
