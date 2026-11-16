@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
title TaskRadar 停止器
set "ROOT=%~dp0"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=5173"
set "BACKEND_PID="
set "FRONTEND_PID="
set "BACKEND_NAME="
set "FRONTEND_NAME="
set "FOUND=0"

echo ============================================
echo   TaskRadar 停止服务
echo ============================================
echo.

if exist "%ROOT%.run\ports.txt" (
    for /f "usebackq tokens=1,2 delims== " %%A in ("%ROOT%.run\ports.txt") do (
        if /i "%%A"=="BACKEND" set "BACKEND_PORT=%%B"
        if /i "%%A"=="FRONTEND" set "FRONTEND_PORT=%%B"
    )
    echo 已读取端口文件：.run\ports.txt
) else (
    echo [提示] 未找到 .run\ports.txt，无法确认本项目服务实际使用的端口。
    echo 为避免误结束其他项目的进程，本次不执行任何结束操作。
    echo.
    echo 如果服务是通过 start.bat 启动的，重新运行一次 start.bat 生成端口文件后再停止；
    echo 也可以直接在被启动的窗口里按 Ctrl+C 结束进程。
    echo.
    pause
    exit /b 0
)
echo.

call :find_pid %BACKEND_PORT% BACKEND_PID BACKEND_NAME
call :find_pid %FRONTEND_PORT% FRONTEND_PID FRONTEND_NAME

if defined BACKEND_PID (
    echo 将结束：后端端口 %BACKEND_PORT% - PID !BACKEND_PID! - !BACKEND_NAME!
    set "FOUND=1"
) else (
    echo 端口 %BACKEND_PORT% 已空闲，无需结束。
)

if defined FRONTEND_PID (
    echo 将结束：前端端口 %FRONTEND_PORT% - PID !FRONTEND_PID! - !FRONTEND_NAME!
    set "FOUND=1"
) else (
    echo 端口 %FRONTEND_PORT% 已空闲，无需结束。
)
echo.

if "!FOUND!"=="0" (
    echo 两个端口都已空闲，TaskRadar 服务未在运行。
    echo.
    pause
    exit /b 0
)

set "CONFIRM="
set /p "CONFIRM=确认结束以上进程吗？(Y/N): "
if /i not "!CONFIRM!"=="Y" (
    echo 已取消，未结束任何进程。
    echo.
    pause
    exit /b 0
)

if defined BACKEND_PID (
    echo 正在结束后端 PID !BACKEND_PID! ...
    taskkill /PID !BACKEND_PID! /T /F >nul 2>&1
    if errorlevel 1 (
        echo [警告] 结束后端进程失败，可能已经自行退出。
    ) else (
        echo 后端进程已结束。
    )
)

if defined FRONTEND_PID (
    echo 正在结束前端 PID !FRONTEND_PID! ...
    taskkill /PID !FRONTEND_PID! /T /F >nul 2>&1
    if errorlevel 1 (
        echo [警告] 结束前端进程失败，可能已经自行退出。
    ) else (
        echo 前端进程已结束。
    )
)

timeout /t 2 /nobreak >nul 2>&1
if errorlevel 1 "%ROOT%backend\.venv\Scripts\python.exe" -c "import time; time.sleep(2)" >nul 2>&1
echo.
call :check_port_state %BACKEND_PORT% 后端
call :check_port_state %FRONTEND_PORT% 前端
echo.
pause
exit /b 0

:find_pid
set "FPORT=%~1"
set "FPID="
set "FNAME=未知进程"
for /f "tokens=5" %%A in ('netstat -ano ^| findstr /R /C:":%FPORT% .*LISTENING"') do (
    if not "%%A"=="0" set "FPID=%%A"
)
if not defined FPID exit /b 0
for /f "usebackq tokens=1 delims=," %%N in (`tasklist /FI "PID eq !FPID!" /NH /FO CSV`) do set "FNAME=%%~N"
set "%~2=!FPID!"
set "%~3=!FNAME!"
exit /b 0

:check_port_state
netstat -ano | findstr /R /C:":%~1 .*LISTENING" >nul 2>&1
if errorlevel 1 (
    echo 端口 %~1（%~2）已释放。
) else (
    echo [警告] 端口 %~1（%~2）仍被占用，请手动检查。
)
exit /b 0
