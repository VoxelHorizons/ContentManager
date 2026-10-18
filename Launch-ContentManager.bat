@echo off
setlocal
cd /d "%~dp0"
py -m content_manager gui %*
if errorlevel 1 (
    echo.
    echo Content Manager could not start.
    echo Install the requirements first: py -m pip install -e .
    pause
)
