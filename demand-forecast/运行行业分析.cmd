@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "TASK_INDUSTRY=%~1"
if /i "%TASK_INDUSTRY%"=="nev" goto valid
if /i "%TASK_INDUSTRY%"=="abs" goto valid
echo 用法：运行行业分析.cmd nev 或 abs，可加 --demo 和 --no-open
exit /b 1
:valid
shift
set "TASK_DEMO="
set "TASK_OPEN=--open"
:args
if "%~1"=="" goto run
if /i "%~1"=="--demo" set "TASK_DEMO=--demo"
if /i "%~1"=="--no-open" set "TASK_OPEN="
shift
goto args
:run
set "TASK_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%TASK_PY%" goto bundled
where py >nul 2>nul
if not errorlevel 1 goto launcher
where python >nul 2>nul
if not errorlevel 1 goto system
echo 未找到Python 3，请安装Python 3.10或以上版本。
exit /b 1
:bundled
"%TASK_PY%" -X utf8 -B scripts/run_skill.py --industry %TASK_INDUSTRY% %TASK_DEMO% %TASK_OPEN%
set "TASK_EXIT=%errorlevel%"
goto finish
:launcher
py -3 -X utf8 -B scripts/run_skill.py --industry %TASK_INDUSTRY% %TASK_DEMO% %TASK_OPEN%
set "TASK_EXIT=%errorlevel%"
goto finish
:system
python -X utf8 -B scripts/run_skill.py --industry %TASK_INDUSTRY% %TASK_DEMO% %TASK_OPEN%
set "TASK_EXIT=%errorlevel%"
:finish
if defined TASK_OPEN pause
endlocal & exit /b %TASK_EXIT%
