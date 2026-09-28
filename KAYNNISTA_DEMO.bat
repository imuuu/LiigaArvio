@echo off
call "%~dp0RUN.bat" --demo %*
if errorlevel 1 pause
