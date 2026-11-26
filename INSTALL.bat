@echo off
call "%~dp0deploy\windows\launch.cmd" install %*
set "result=%errorlevel%"
if "%~1"=="" pause
exit /b %result%
