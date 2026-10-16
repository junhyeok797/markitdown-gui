@echo off
rem Launch MarkItDown GUI on Windows, or add/remove its shortcuts.
rem
rem   run.bat              start the app (opens in your browser)
rem   run.bat --install    add shortcuts to the desktop and the Start menu
rem   run.bat --uninstall  remove those shortcuts
rem
rem Kept ASCII-only with CRLF line endings: cmd misreads other encodings and
rem can jump to the wrong label in LF-only files.
setlocal
cd /d "%~dp0"

set "APP_DIR=%~dp0"
set "SHORTCUT_NAME=MarkItDown GUI.lnk"
rem The inner quotes end cmd's quoting before the pipe, so it needs a caret.
set "UV_INSTALL_CMD=powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex""

if /i "%~1"=="--install" goto install
if /i "%~1"=="--uninstall" goto uninstall
if not "%~1"=="" goto usage

call :find_uv
if defined UV goto launch

echo MarkItDown GUI needs 'uv' to run, but it is not installed.
echo It can be installed with the official installer:
echo   %UV_INSTALL_CMD%
echo.
choice /c YN /n /m "Install uv now? [Y/N] "
if errorlevel 2 goto uv_declined
%UV_INSTALL_CMD%
rem The installer updates PATH for new windows only; find_uv also checks
rem the default install location directly.
call :find_uv
if not defined UV goto uv_failed

:launch
set "LOCKED="
if exist "app.py.lock" set "LOCKED=--locked"
echo Starting MarkItDown GUI. It will open in your browser.
echo First launch may take a few minutes while dependencies are installed.
echo Closing the browser tab or this window stops the app.
echo.
"%UV%" run %LOCKED% app.py
if errorlevel 1 goto app_failed
exit /b 0

:app_failed
echo.
echo MarkItDown GUI stopped unexpectedly. See the messages above.
pause
exit /b 1

:uv_declined
echo.
echo uv is required. Install it with:
echo   %UV_INSTALL_CMD%
echo Then run MarkItDown GUI again.
pause
exit /b 1

:uv_failed
echo.
echo Installing uv failed. Install it manually with:
echo   %UV_INSTALL_CMD%
pause
exit /b 1

:install
rem Paths are passed through environment variables so that quotes or other
rem special characters in the folder name cannot break the PowerShell command.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$shell = New-Object -ComObject WScript.Shell;" ^
  "foreach ($dir in [Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs')) {" ^
  "  $link = $shell.CreateShortcut((Join-Path $dir $env:SHORTCUT_NAME));" ^
  "  $link.TargetPath = Join-Path $env:APP_DIR 'run.bat';" ^
  "  $link.WorkingDirectory = $env:APP_DIR;" ^
  "  $link.IconLocation = (Join-Path $env:APP_DIR 'icon.ico') + ',0';" ^
  "  $link.Description = 'Convert documents to Markdown';" ^
  "  $link.Save();" ^
  "  Write-Host ('Added shortcut: ' + $link.FullName)" ^
  "}"
if errorlevel 1 goto install_failed
echo If you move this folder, run "run.bat --install" again.
exit /b 0

:install_failed
echo Creating shortcuts failed.
exit /b 1

:uninstall
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "foreach ($dir in [Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs')) {" ^
  "  Remove-Item -LiteralPath (Join-Path $dir $env:SHORTCUT_NAME) -ErrorAction SilentlyContinue" ^
  "}"
echo Shortcuts removed.
exit /b 0

:usage
echo Usage: run.bat [--install ^| --uninstall]
exit /b 2

:find_uv
set "UV="
for /f "delims=" %%i in ('where uv.exe 2^>nul') do if not defined UV set "UV=%%i"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "UV=%USERPROFILE%\.cargo\bin\uv.exe"
exit /b 0
