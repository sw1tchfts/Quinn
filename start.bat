@echo off
REM Launch the LoL Damage Predictor web server and open the page.
REM Double-click to run, or call from a terminal in the repo root.

setlocal
set HOST=127.0.0.1
set PORT=8765
set URL=http://%HOST%:%PORT%/

REM Pick whichever Python launcher exists.
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    set PYTHON=py -3
) else (
    where python >nul 2>&1
    if %ERRORLEVEL%==0 (
        set PYTHON=python
    ) else (
        echo [start.bat] Python is not on PATH. Install Python 3.9+ and retry.
        pause
        exit /b 1
    )
)

REM Best-effort: install requests on first run if missing.
%PYTHON% -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo [start.bat] Installing dependency: requests
    %PYTHON% -m pip install --quiet requests
)

REM Open the browser shortly after the server starts.
start "" "%URL%"

REM Run the server in this window so you can Ctrl+C to stop it.
%PYTHON% -m lol_damage.server --host %HOST% --port %PORT%

endlocal
