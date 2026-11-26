@echo off
setlocal
where py.exe >nul 2>nul
if not errorlevel 1 (
    py -3.12 --version >nul 2>nul
    if not errorlevel 1 goto use_python_launcher
)
where python.exe >nul 2>nul
if errorlevel 1 goto missing_python
python -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))" >nul 2>nul
if errorlevel 1 goto missing_python
python "%~dp0local.py" %*
exit /b %errorlevel%

:use_python_launcher
py -3.12 "%~dp0local.py" %*
exit /b %errorlevel%

:missing_python
echo Install Python 3.12, then reopen this window.
exit /b 1
