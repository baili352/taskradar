@echo off
chcp 65001 >nul
setlocal EnableExtensions
title TaskRadar 启动器
set "ROOT=%~dp0"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT="

echo ============================================
echo   TaskRadar 一键启动
echo ============================================
echo.

if not exist "%ROOT%backend\.venv\Scripts\python.exe" (
    echo [错误] 未找到后端虚拟环境：backend\.venv\Scripts\python.exe
    echo 请先在项目根目录执行：
    echo     py -3.11 -m venv backend\.venv
    echo     backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "%ROOT%frontend\node_modules" (
    echo [错误] 未找到前端依赖：frontend\node_modules
    echo 请先执行：
    echo     cd frontend
    echo     npm install
    echo.
    pause
    exit /b 1
)

if not exist "%ROOT%backend\.env" (
    echo [错误] 未找到 backend\.env
    echo 请先复制示例配置，再填写自己的配置：
    echo     copy backend\.env.example backend\.env
    echo 注意：backend\.env 含密钥，不要提交到仓库。
    echo.
    pause
    exit /b 1
)

call :port_in_use %BACKEND_PORT%
if errorlevel 1 (
    echo [错误] 端口 %BACKEND_PORT% 已被占用，启动器不会结束其他进程。
    echo 请先关闭占用该端口的程序，或双击 stop.bat 清理本项目进程后重试。
    echo 查看占用：netstat -ano ^| findstr :%BACKEND_PORT%
    echo.
    pause
    exit /b 1
)

for %%P in (5173 5174 5175) do (
    if not defined FRONTEND_PORT (
        call :port_in_use %%P
        if errorlevel 1 (
            echo 端口 %%P 已被占用，尝试下一个端口...
        ) else (
            set "FRONTEND_PORT=%%P"
            if not "%%P"=="5173" echo 前端将使用备用端口 %%P。
        )
    )
)

if not defined FRONTEND_PORT (
    echo [错误] 端口 5173、5174、5175 均已被占用。
    echo 请先关闭其中一个程序后重试；启动器不会结束其他进程。
    echo.
    pause
    exit /b 1
)

if not exist "%ROOT%.run" mkdir "%ROOT%.run" >nul 2>&1
> "%ROOT%.run\ports.txt" (
    echo BACKEND=%BACKEND_PORT%
    echo FRONTEND=%FRONTEND_PORT%
)

echo 正在启动后端（端口 %BACKEND_PORT%）...
start "TaskRadar 后端" /D "%ROOT%backend" cmd /k ""%ROOT%backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --port %BACKEND_PORT%"

echo 正在启动前端（端口 %FRONTEND_PORT%）...
start "TaskRadar 前端" /D "%ROOT%frontend" cmd /k "npm run dev -- --port %FRONTEND_PORT% --strictPort"

echo.
echo 正在等待后端就绪（最多 60 秒）...
set /a WAITED=0

:wait_health
"%ROOT%backend\.venv\Scripts\python.exe" -c "import json,sys,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:%BACKEND_PORT%/api/health', timeout=2)); sys.exit(0 if d.get('status')=='ok' else 1)" >nul 2>&1
if not errorlevel 1 goto healthy
if %WAITED% GEQ 60 goto health_timeout
timeout /t 2 /nobreak >nul 2>&1
if errorlevel 1 "%ROOT%backend\.venv\Scripts\python.exe" -c "import time; time.sleep(2)" >nul 2>&1
set /a WAITED+=2
goto wait_health

:healthy
echo 后端就绪（等待 %WAITED% 秒）。
set "FRONTEND_URL=http://127.0.0.1:%FRONTEND_PORT%"
echo 正在打开前端：%FRONTEND_URL%
start "" "%FRONTEND_URL%"
echo.
echo ============================================
echo 后端地址：http://127.0.0.1:%BACKEND_PORT%
echo 前端地址：%FRONTEND_URL%
echo 停止方式：双击 stop.bat，或在对应窗口按 Ctrl+C 后关闭窗口。
echo ============================================
echo.
echo 按任意键关闭本窗口（服务会继续运行）。
pause >nul
exit /b 0

:health_timeout
echo.
echo [错误] 等待 60 秒后后端仍未就绪。
echo 请查看标题为「TaskRadar 后端」的窗口中的报错信息，修复后重新运行 start.bat。
echo 常见原因：backend\.env 配置错误、依赖未安装完整、8000 端口冲突。
echo.
pause
exit /b 1

:port_in_use
netstat -ano | findstr /R /C:":%~1 .*LISTENING" >nul 2>&1
if errorlevel 1 exit /b 0
exit /b 1
