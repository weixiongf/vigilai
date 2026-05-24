@echo off
REM ============================================================
REM 作者：冯伟雄
REM 项目：深圳 AI for Human 企业 Agent 挑战赛
REM 时间：2026-05-23 12:30:00
REM
REM 功能说明：战略雷达项目一键启动脚本，支持服务健康检查、
REM           Django/Celery 启停、数据迁移、静态资源同步，
REM           并通过 Ctrl+C 循环停止/重启 Django 服务。
REM ============================================================

chcp 65001 >nul
title 战略雷达 - 服务启动器
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "VENV_ACT=.venv\Scripts\activate.bat"
set "DJANGO_TITLE=战略雷达-Django"
set "WORKER_TITLE=战略雷达-CeleryWorker"
set "BEAT_TITLE=战略雷达-CeleryBeat"
set "DJANGO_PORT=8000"
set "REDIS_PORT=6379"
set "PG_PORT=5432"

if not exist "%VENV_ACT%" (
    echo [错误] 未发现虚拟环境 %VENV_ACT%
    echo        请先创建并安装依赖后再运行本脚本。
    pause
    exit /b 1
)

:main_menu
cls
echo ============================================================
echo                  战略雷达 - 服务启动器
echo ============================================================
echo   [1] 启动所有服务（Django + Celery Worker + Celery Beat） 
echo   [2] 重新启动所有服务（Django） 
echo   [3] 数据迁移（makemigrations + migrate） 
echo   [4] 静态资源同步（collectstatic） 
echo   [5] 服务健康检查（Redis / PostgreSQL / Django 端口） 
echo   [6] 仅停止已运行的服务 
echo   [7] 退出终端 
echo ============================================================
echo.
choice /C 1234567 /N /M "请选择 [1-7]: "
set "CHOICE=%errorlevel%"
if "%CHOICE%"=="7" goto exit_app
if "%CHOICE%"=="6" goto stop_only
if "%CHOICE%"=="5" goto health_only
if "%CHOICE%"=="4" goto run_collectstatic
if "%CHOICE%"=="3" goto run_migrate
if "%CHOICE%"=="2" goto restart_from_main
if "%CHOICE%"=="1" goto start_all
goto main_menu

REM ============================================================
REM 从主菜单触发：重新启动全部服务（Django + Celery）
REM ============================================================
:restart_from_main
echo.
echo ------ 重新启动全部服务 ------ 
call :check_port "Redis" 127.0.0.1 %REDIS_PORT%
if errorlevel 1 (
    echo [错误] Redis 未在 127.0.0.1:%REDIS_PORT% 监听，无法重启服务。 
    echo.
    pause
    goto main_menu
)
call :check_port "PostgreSQL" 127.0.0.1 %PG_PORT%
if errorlevel 1 (
    echo [错误] PostgreSQL 未在 127.0.0.1:%PG_PORT% 监听，无法重启服务。 
    echo. 
    pause
    goto main_menu
)
echo 正在停止已有服务... 
call :stop_services
timeout /t 1 >nul
call :do_collectstatic
call :launch_services
goto running_menu

REM ============================================================
REM 启动全部服务
REM ============================================================
:start_all
echo.
echo ------ 检查依赖服务 ------ 
call :check_port "Redis" 127.0.0.1 %REDIS_PORT%
if errorlevel 1 (
    echo [错误] Redis 未在 127.0.0.1:%REDIS_PORT% 监听，请先启动 Redis。 
    echo.
    pause
    goto main_menu
)
call :check_port "PostgreSQL" 127.0.0.1 %PG_PORT%
if errorlevel 1 (
    echo [错误] PostgreSQL 未在 127.0.0.1:%PG_PORT% 监听，请先启动 PostgreSQL。 
    echo.
    pause
    goto main_menu
)
echo [OK] 依赖服务正常。 
echo.

call :check_port "Django" 127.0.0.1 %DJANGO_PORT%
if not errorlevel 1 (
    echo [警告] 检测到 Django 已在 :%DJANGO_PORT% 端口运行。 
    choice /C YN /N /M "是否先关闭已有服务再重启 ? [Y/N]: "
    if errorlevel 2 (
        echo 已取消启动。 
        timeout /t 2 >nul
        goto main_menu
    )
    call :stop_services
)

call :launch_services
goto running_menu

REM ============================================================
REM 服务运行中子菜单
REM ============================================================
:running_menu
cls
echo ============================================================
echo                    服务运行中
echo ------------------------------------------------------------
echo   Django       : http://127.0.0.1:%DJANGO_PORT%/ 
echo   Celery Worker: 独立窗口 [%WORKER_TITLE%] 
echo   Celery Beat  : 独立窗口 [%BEAT_TITLE%] 
echo ============================================================
echo   [1] 停止 Django（保留 Celery） 
echo   [2] 停止全部服务并返回主菜单 
echo   [3] 重启全部服务 
echo   [4] 查看服务状态 
echo   ★ 在此按 Ctrl+C 将停止全部服务并回到主菜单 
echo ============================================================
choice /C 1234 /N /M "请选择 [1-4] (Ctrl+C 回主菜单): "
set "RC=%errorlevel%"
if "%RC%"=="0" goto ctrlc_first
if "%RC%"=="4" goto running_status
if "%RC%"=="3" goto restart_all
if "%RC%"=="2" goto stop_back_main
if "%RC%"=="1" goto stop_django_only
goto running_menu

:running_status
echo.
call :check_port "Django"      127.0.0.1 %DJANGO_PORT%
call :check_port "Redis"       127.0.0.1 %REDIS_PORT%
call :check_port "PostgreSQL"  127.0.0.1 %PG_PORT%
echo.
pause
goto running_menu

:stop_django_only
echo.
echo [Ctrl+C 流程] 正在停止 Django 服务... 
call :kill_by_title "%DJANGO_TITLE%"
echo [OK] Django 已停止（Celery 仍在运行）。 
echo.
choice /C 12 /N /M "[1] 重启全部服务（含 Celery）   [2] 返回主菜单 (再次 Ctrl+C 同 [2]) : "
set "RC=%errorlevel%"
if "%RC%"=="0" goto stop_back_main
if "%RC%"=="2" goto stop_back_main
if "%RC%"=="1" (
    echo 为保证代码与数据同步，将连带重启 Celery Worker / Beat ...
    call :stop_services
    timeout /t 1 >nul
    call :do_collectstatic
    call :launch_services
    goto running_menu
)
goto running_menu

:ctrlc_first
echo.
echo [Ctrl+C] 已捕获，正在停止全部服务... 
call :stop_services
echo [OK] 全部服务已停止，正在返回主菜单... 
timeout /t 1 >nul
goto main_menu

:restart_all
echo.
echo 正在重启全部服务... 
call :stop_services
timeout /t 1 >nul
call :do_collectstatic
call :launch_services
goto running_menu

:stop_back_main
echo.
echo 正在停止全部服务... 
call :stop_services
echo [OK] 已返回主菜单。 
timeout /t 1 >nul
goto main_menu

REM ============================================================
REM 仅停止 / 仅检测 / 数据迁移 / 静态资源
REM ============================================================
:stop_only
echo.
call :stop_services
echo.
pause
goto main_menu

:health_only
echo.
echo ------ 健康检查 ------ 
call :check_port "Redis"       127.0.0.1 %REDIS_PORT%
call :check_port "PostgreSQL"  127.0.0.1 %PG_PORT%
call :check_port "Django"      127.0.0.1 %DJANGO_PORT%
echo.
pause
goto main_menu

:run_migrate
echo.
echo ------ 数据迁移 ------ 
call :check_port "PostgreSQL" 127.0.0.1 %PG_PORT%
if errorlevel 1 (
    echo [错误] PostgreSQL 未启动，无法迁移。
    pause
    goto main_menu
)
call "%VENV_ACT%" && python manage.py makemigrations && python manage.py migrate
echo.
echo [完成] 数据迁移结束。
pause
goto main_menu

:run_collectstatic
echo.
echo ------ 静态资源同步 ------ 
call "%VENV_ACT%" && python manage.py collectstatic --noinput
echo.
echo [完成] 静态资源同步结束。
pause
goto main_menu

:exit_app
echo.
choice /C YN /N /M "退出前是否停止所有已启动服务 ? [Y/N]: " 
if errorlevel 2 goto :final_exit
call :stop_services
:final_exit
echo 再见。
timeout /t 1 >nul
endlocal
exit /b 0

REM ============================================================
REM 子例程：端口检测   用法: call :check_port 名称 主机 端口
REM ============================================================
:check_port
set "_NAME=%~1"
set "_HOST=%~2"
set "_PORT=%~3"
powershell -NoProfile -Command "$c = New-Object System.Net.Sockets.TcpClient; try { $iar = $c.BeginConnect('%_HOST%', %_PORT%, $null, $null); if ($iar.AsyncWaitHandle.WaitOne(800)) { $c.EndConnect($iar); $c.Close(); exit 0 } else { $c.Close(); exit 1 } } catch { exit 1 }"
if errorlevel 1 (
    echo   [×] %_NAME%   %_HOST%:%_PORT%   未监听
    exit /b 1
) else (
    echo   [√] %_NAME%   %_HOST%:%_PORT%   正常
    exit /b 0
)

REM ============================================================
REM 子例程：按窗口标题杀进程   用法: call :kill_by_title 标题
REM ============================================================
:kill_by_title
taskkill /F /FI "WINDOWTITLE eq %~1*" >nul 2>&1
exit /b 0

REM ============================================================
REM 子例程：启动 Django / Celery
REM ============================================================
:launch_django
echo 正在启动 Django (Daphne ASGI) ... 
REM 使用 daphne 而非 runserver: runserver 是 WSGI 同步 server, 会缓冲
REM StreamingHttpResponse 导致 SSE 不是真流式. daphne 是 ASGI server,
REM 原生支持 chunked transfer + 不缓冲 generator yield 出的每一帧.
start "%DJANGO_TITLE%" cmd /k "chcp 65001 >nul & cd /d %~dp0 & call %VENV_ACT% & python -m daphne -b 0.0.0.0 -p %DJANGO_PORT% config.asgi:application"
exit /b 0

:launch_worker
echo 正在启动 Celery Worker ... 
start "%WORKER_TITLE%" cmd /k "chcp 65001 >nul & cd /d %~dp0 & call %VENV_ACT% & celery -A config worker -l info -P solo"
exit /b 0

:launch_beat
echo 正在启动 Celery Beat ... 
start "%BEAT_TITLE%" cmd /k "chcp 65001 >nul & cd /d %~dp0 & call %VENV_ACT% & celery -A config beat -l info"
exit /b 0

:launch_services
call :launch_django
timeout /t 1 >nul
call :launch_worker
timeout /t 1 >nul
call :launch_beat
echo.
echo [OK] 服务已在独立窗口中启动。
timeout /t 2 >nul
exit /b 0

REM ============================================================
REM 子例程：静默执行 collectstatic（重启前同步静态资源）
REM ============================================================
:do_collectstatic
echo 正在同步静态资源 (collectstatic --noinput) ... 
pushd "%~dp0" >nul
call "%VENV_ACT%" >nul 2>&1
python manage.py collectstatic --noinput >nul 2>&1 
if errorlevel 1 (
    echo   [!] collectstatic 返回非零状态，已忽略并继续重启。 
) else (
    echo   [OK] 静态资源已同步到 staticfiles/ 。 
)
popd >nul
exit /b 0

:stop_services
REM 1) 关闭服务窗口（cmd 顶层）
call :kill_by_title "%DJANGO_TITLE%"
call :kill_by_title "%WORKER_TITLE%"
call :kill_by_title "%BEAT_TITLE%"
REM 2) 兼底：按命令行特征杀掉旧 Celery / runserver 子进程 
REM    避免 cmd 窗口被关后 python.exe 子进程脱离变孤儿进程导致重启冲突 
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe' -or $_.Name -eq 'celery.exe') -and $_.CommandLine -match 'celery\s+-A|celery worker|celery beat|manage\.py\s+runserver|daphne|config\.asgi' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
taskkill /F /IM celery.exe >nul 2>&1
echo [OK] 已尝试停止全部服务（含旧 Celery Worker / Beat 子进程）。 
exit /b 0
