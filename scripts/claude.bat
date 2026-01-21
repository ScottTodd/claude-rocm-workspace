@echo off
REM Launch Claude Code with the workspace Python venv activated.
REM
REM Setup (one-time):
REM   cd D:\projects\claude-rocm-workspace
REM   py -V:3.12 -m venv 3.12.venv
REM   .\3.12.venv\Scripts\activate.bat
REM   pip install -r ..\TheRock\requirements.txt
REM
REM This ensures tools like pytest are available when Claude runs commands.

setlocal

set SCRIPT_DIR=%~dp0
set WORKSPACE_DIR=%SCRIPT_DIR%..

REM Activate the workspace venv
call "%WORKSPACE_DIR%\3.12.venv\Scripts\activate.bat"

REM Change to workspace directory and launch Claude
cd /d "%WORKSPACE_DIR%"
claude %*
