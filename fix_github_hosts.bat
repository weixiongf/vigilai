REM ============================================================
REM 作者：冯伟雄
REM 项目：深圳 AI for Human 企业 Agent 挑战赛
REM 时间：2026-05-23 12:30:00
REM ============================================================

@echo off
REM ============================================================
REM GitHub hosts 修复脚本（请以"管理员身份运行"）
REM 把 github.com / codeload.github.com / raw.githubusercontent.com
REM 钉到当前可达的官方 IP，绕过被污染的 DNS。
REM ============================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 请右键此文件，选择 "以管理员身份运行"
    pause
    exit /b 1
)

set HOSTS=%windir%\System32\drivers\etc\hosts

echo. >> "%HOSTS%"
echo # === GitHub fix (added by VigilAI repo init) === >> "%HOSTS%"
echo 140.82.112.3 github.com >> "%HOSTS%"
echo 140.82.112.10 codeload.github.com >> "%HOSTS%"
echo 185.199.108.133 raw.githubusercontent.com >> "%HOSTS%"
echo 185.199.108.154 github.githubassets.com >> "%HOSTS%"
echo # === GitHub fix end === >> "%HOSTS%"

ipconfig /flushdns >nul

echo.
echo [OK] hosts 已添加 GitHub 解析条目，DNS 缓存已刷新。
echo 现在可以关闭此窗口，回到原 PowerShell 通知 AI 继续推送。
echo.
pause
