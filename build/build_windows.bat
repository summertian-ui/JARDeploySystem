@echo off
REM ============================================================
REM  打包 Windows exe（需在 Windows 10/11 上运行）
REM  用法: 双击运行，或 cmd 中执行 build\build_windows.bat
REM  输出: dist\JARDeploySystem.exe
REM ============================================================
setlocal
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 python，请先安装 Python 3.10+ 并勾选 "Add Python to PATH"
  pause
  exit /b 1
)

echo ==^> 安装依赖...
python -m pip install --upgrade pip
python -m pip install flask paramiko scp pymysql pywebview pyinstaller
if errorlevel 1 (
  echo [错误] 依赖安装失败
  pause
  exit /b 1
)

echo ==^> 打包 exe...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "JARDeploySystem" ^
  --icon "assets\app.ico" ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --collect-submodules webview ^
  --workpath build\pyi ^
  --distpath build\dist ^
  desktop_app.py
if errorlevel 1 (
  echo [错误] 打包失败
  pause
  exit /b 1
)

echo.
echo ==^> 完成: dist\JARDeploySystem.exe
pause
endlocal
