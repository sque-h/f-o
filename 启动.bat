@echo off
chcp 65001 >nul
REM 拉格朗日考勤 · 源码启动器
REM 需要本机已装 Python 3.9+（安装时记得勾选 "Add Python to PATH"）。
REM 双击即可：首次自动装依赖，然后打开浏览器界面。

setlocal
set "HERE=%~dp0"
pushd "%HERE%"

where python >nul 2>nul
if not "%errorlevel%"=="0" (
    echo.
    echo   没找到 Python。
    echo   请先安装 Python 3.9 或更高版本：https://www.python.org/downloads/
    echo   安装时记得勾选 "Add Python to PATH"。
    echo.
    pause
    popd
    goto :eof
)

if not exist ".deps_ok" (
    echo.
    echo   首次运行，正在安装依赖（需要联网，约 1-2 分钟）...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo   依赖安装失败，请检查网络后重试。
        echo.
        pause
        popd
        goto :eof
    )
    echo ok> ".deps_ok"
)

echo.
echo   正在启动，稍等几秒浏览器会自动打开...
echo   关闭程序：直接关掉这个黑窗口即可。
echo.
python attendance_gui.py

popd
pause
