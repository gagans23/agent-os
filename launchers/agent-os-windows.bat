@echo off
REM ===========================================================================
REM  agent-os - double-click to start (Windows).
REM
REM  Keep this file inside the agent-os folder. The first run sets up a small
REM  local environment (a couple of minutes); every run after that just opens
REM  the web UI in your browser. You don't type anything - this window only
REM  shows progress. To stop agent-os, close this window.
REM ===========================================================================
setlocal
cd /d "%~dp0\.."

echo Starting agent-os...
echo.

if exist ".venv\Scripts\agent-os.exe" goto :launch

echo First run: setting up a local environment. This can take a couple of minutes...
echo.
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
%PY% --version >nul 2>nul || goto :nopy
%PY% -m venv .venv || goto :nopy
call ".venv\Scripts\activate.bat"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet "ninja-harness @ git+https://github.com/gagans23/ninja-harness.git" || goto :nogit
python -m pip install --quiet -e . || goto :fail
goto :run

:launch
call ".venv\Scripts\activate.bat"

:run
echo.
echo Opening the web UI in your browser... (close this window to stop agent-os)
agent-os ui %*
goto :eof

:nopy
echo.
echo agent-os needs Python 3.11+ . Opening the download page...
echo Install it (tick "Add Python to PATH"), then double-click this again.
start https://www.python.org/downloads/
pause
goto :eof

:nogit
echo.
echo Could not fetch the eval gate. This needs Git installed.
echo Opening the Git download page - install it, then double-click this again.
start https://git-scm.com/download/win
pause
goto :eof

:fail
echo.
echo Setup did not finish. See the messages above.
pause
goto :eof
