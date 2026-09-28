@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Testataan Liigan verkkoyhteys. Tulos tallennetaan tiedostoon yhteystesti.txt.
call "%~dp0RUN.bat" --check > "%~dp0yhteystesti.txt" 2>&1
type "%~dp0yhteystesti.txt"
echo.
echo Raportti: %~dp0yhteystesti.txt
pause
