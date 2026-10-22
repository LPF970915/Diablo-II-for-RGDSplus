@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
title Diablo II for RGDSplus - Fresh player installation
set "PYTHONUTF8=1"
set "D2_IMPORT_SOURCE=%~1"
if not defined D2_IMPORT_SOURCE set /p "D2_IMPORT_SOURCE=Enter your original Diablo II + Lord of Destruction folder: "
"%~dp0game-import\python\python.exe" "%~dp0game-import\install_assets.py"
set "D2_IMPORT_EXIT=%ERRORLEVEL%"
if not "%D2_IMPORT_EXIT%"=="0" echo Import failed. Read the message above. Existing saves and the original installation were not replaced.
pause
exit /b %D2_IMPORT_EXIT%
