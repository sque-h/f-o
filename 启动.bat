@echo off
chcp 65001 >nul
REM 拉格朗日考勤 · 一键版 启动器
REM 优先运行同目录的 exe；若没有（源码模式）则尝试用 python 启动。

setlocal
set "HERE=%~dp0"
if exist "%HERE%拉格朗日考勤.exe" (
    start "" "%HERE%拉格朗日考勤.exe"
    goto :eof
)
REM 源码模式：找 python
where python >nul 2>nul
if %errorlevel%==0 (
    pushd "%HERE%"
    python attendance_gui.py
    popd
    goto :eof
)
echo 未找到「拉格朗日考勤.exe」也没有 python，请先按说明安装或下载打包版。
pause
