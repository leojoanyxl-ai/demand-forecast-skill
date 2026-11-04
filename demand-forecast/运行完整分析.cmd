@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "TASK_OPEN=--open"
if /i "%~1"=="--no-open" set "TASK_OPEN="
if /i "%~2"=="--no-open" set "TASK_OPEN="
set "TASK_DEMO="
if /i "%~1"=="--demo" set "TASK_DEMO=--demo"
set "TASK_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%TASK_PY%" goto bundled
where py >nul 2>nul
if not errorlevel 1 goto py_launcher
where python >nul 2>nul
if not errorlevel 1 goto system_python
echo 未找到Python 3。请安装Python 3后重新运行。
set "TASK_EXIT=1"
goto finished
:bundled
"%TASK_PY%" -X utf8 -B scripts\run_skill.py --industry nev %TASK_DEMO% %TASK_OPEN%
set "TASK_EXIT=%errorlevel%"
goto finished
:py_launcher
py -3 -B scripts\run_skill.py --industry nev %TASK_DEMO% %TASK_OPEN%
set "TASK_EXIT=%errorlevel%"
goto finished
:system_python
python -B scripts\run_skill.py --industry nev %TASK_DEMO% %TASK_OPEN%
set "TASK_EXIT=%errorlevel%"
:finished
if defined TASK_OPEN pause
endlocal & exit /b %TASK_EXIT%
