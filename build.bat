@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Audit Coworker — Build

echo ============================================================
echo   Audit Coworker 一键打包脚本
echo ============================================================
echo.

:: ------- 检查 Node.js -------
where node >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] 未找到 Node.js，请安装 Node.js ^>= 20
    pause
    exit /b 1
)

:: ------- 检查 Python -------
where python >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] 未找到 Python，请安装 Python ^>= 3.12
    pause
    exit /b 1
)

:: ------- 检查/安装 PyInstaller -------
python -m PyInstaller --version >nul 2>&1
if !errorlevel! neq 0 (
    echo [INFO] 正在安装 PyInstaller ...
    pip install pyinstaller
)
python -m PyInstaller --version >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] PyInstaller 安装失败
    pause
    exit /b 1
)

:: ============================================================
:: Step 1: 构建前端
:: ============================================================
echo.
echo [1/3] 构建前端 ...
pushd frontend
if not exist node_modules (
    echo      npm install ...
    call npm install
)
if !errorlevel! neq 0 (
    echo [ERROR] npm install 失败
    popd
    pause
    exit /b 1
)
call npm run build
if !errorlevel! neq 0 (
    echo [ERROR] 前端构建失败
    popd
    pause
    exit /b 1
)
popd
echo [OK] 前端构建完成 — frontend\dist

:: ============================================================
:: Step 2: 安装后端依赖
:: ============================================================
echo.
echo [2/3] 检查后端 Python 依赖 ...
pip install -r backend\requirements.txt -q
if !errorlevel! neq 0 (
    echo [ERROR] 后端依赖安装失败
    pause
    exit /b 1
)
echo [OK] 后端依赖就绪

:: ============================================================
:: Step 3: PyInstaller 打包
:: ============================================================
echo.
echo [3/3] PyInstaller 打包中 (可能需要几分钟) ...
python -m PyInstaller audit_coworker.spec --noconfirm --clean
if !errorlevel! neq 0 (
    echo [ERROR] PyInstaller 打包失败
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   打包完成!
echo   输出目录: dist\AuditCoworker\
echo   可执行文件: dist\AuditCoworker\AuditCoworker.exe
echo ============================================================
echo.
echo 你可以将 dist\AuditCoworker 文件夹整体拷贝到目标机器运行,
echo 或使用 Inno Setup 编译 installer.iss 生成安装程序。
echo.
pause
