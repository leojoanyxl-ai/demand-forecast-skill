@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo 行业需求预测与经营计划助手
echo 1. 新能源汽车：企业实际数据待补模式
echo 2. ABS：企业实际数据待补模式
echo 3. 新能源汽车：教学企业参数演示
echo 4. ABS：教学企业参数演示
set /p "TASK_CHOICE=请输入1至4："
if "%TASK_CHOICE%"=="1" call "运行行业分析.cmd" nev
if "%TASK_CHOICE%"=="2" call "运行行业分析.cmd" abs
if "%TASK_CHOICE%"=="3" call "运行行业分析.cmd" nev --demo
if "%TASK_CHOICE%"=="4" call "运行行业分析.cmd" abs --demo
endlocal
