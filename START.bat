@echo off
call "%~dp0deploy\windows\launch.cmd" start %*
set "result=%errorlevel%"
if "%~1"=="" pause
exit /b %result%
