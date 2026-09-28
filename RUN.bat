@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 goto TryPython
py -3 "%~dp0app.py" %*
exit /b %ERRORLEVEL%
:TryPython
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 goto NoPython
python "%~dp0app.py" %*
exit /b %ERRORLEVEL%
:NoPython
echo.
echo Python 3.10 tai uudempi puuttuu tai sita ei loydy.
echo Asenna Python osoitteesta https://www.python.org/downloads/windows/
echo Valitse asennuksessa Add python.exe to PATH, jos valinta on tarjolla.
echo Sulje tama ikkuna asennuksen jalkeen ja avaa KAYNNISTA.bat uudelleen.
echo Ohjelma ei tarvitse pip-paketteja tai API-avaimia.
exit /b 1
