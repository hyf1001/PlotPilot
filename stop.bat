@echo off
chcp 65001 >/dev/null
echo ========================================
echo 正在关闭所有前后端服务...
echo ========================================
echo.

echo [1/3] 关闭所有 Node.js 进程...
taskkill /F /IM node.exe /T >/dev/null 2>&1
if %errorlevel% equ 0 (
    echo   √ Node.js 进程已关闭
) else (
    echo   - × Node.js 进程不存在
)

echo [2/3] 关闭所有 Python 进程...
taskkill /F /IM python.exe /T >/dev/null 2>&1
if %errorlevel% equ 0 (
    echo   √ Python 进程已关闭
) else (
    echo   - × Python 进程不存在
)

echo [3/3] 清理端口占用...
for %%p in (3000 3001 3002 3003 3004 3005 3006 3007 3008 3009 3010 8007) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%%p ^| findstr LISTENING 2^>nul') do (
        taskkill /F /PID %%a >/dev/null 2>&1
    )
)
echo   √ 端口已清理

echo.
echo ========================================
echo √ 所有前后端服务已关闭
echo ========================================
echo.
pause
