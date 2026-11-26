@echo off
call "%~dp0deploy\windows\launch.cmd" update %*
set "result=%errorlevel%"
if "%~1"=="" pause
exit /b %result%
