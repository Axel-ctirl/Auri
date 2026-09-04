@echo off
rem Bread's command line on Windows, without installing anything.
rem
rem   bread                 the banner and what you can do
rem   bread ask "..."       one question
rem   bread chat            an interactive session
setlocal
set "BREAD_HOME=%~dp0"
if defined BREAD_PYTHON (
  set "BREAD_PY=%BREAD_PYTHON%"
) else if exist "%BREAD_HOME%.venv\Scripts\python.exe" (
  set "BREAD_PY=%BREAD_HOME%.venv\Scripts\python.exe"
) else (
  set "BREAD_PY=python"
)
set "PYTHONPATH=%BREAD_HOME%backend;%PYTHONPATH%"
"%BREAD_PY%" -m app.cli %*
