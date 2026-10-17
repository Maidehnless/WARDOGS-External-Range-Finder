@echo off
setlocal EnableExtensions DisableDelayedExpansion
title WARDOGS Range Finder - Python Setup
color 0B

echo ===========================================================
echo              WARDOGS RANGE FINDER - SETUP
echo ===========================================================
echo.
echo This setup requires administrator permission and internet.
echo It installs Python only if a compatible setup is not found.
echo.

rem Relaunch this same BAT with an Administrator UAC prompt.
fltmc >nul 2>&1
if errorlevel 1 goto :ELEVATE
goto :CHECK_PYTHON

:ELEVATE
echo Requesting administrator permission...
set "WARDOGS_SETUP_FILE=%~f0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { Start-Process -FilePath $env:WARDOGS_SETUP_FILE -Verb RunAs -ErrorAction Stop } catch { Write-Host ('Could not elevate: ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 (
    echo.
    echo [ERROR] Administrator permission was denied or unavailable.
    pause
)
exit /b

:CHECK_PYTHON
echo [1/4] Checking for Python and the Tkinter GUI library...
rem RUN ME.vbs uses: py wd_rf.py. Test that exact Python launcher.
where py >nul 2>&1
if errorlevel 1 goto :NEEDS_INSTALL
py -c "import sys, tkinter, ctypes; sys.exit(0 if (3, 10) <= sys.version_info[:2] < (4, 0) else 1)" >nul 2>&1
if errorlevel 1 goto :NEEDS_INSTALL

echo.
echo [OK] A compatible Python installation is already available.
echo No installation is needed.
py --version
goto :SUCCESS

:NEEDS_INSTALL
set "PY_VERSION=3.13.16"
set "ARCH=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "ARCH=%PROCESSOR_ARCHITEW6432%"

rem Official Python Software Foundation SHA-256 hashes for 3.13.16.
if /i "%ARCH%"=="AMD64" (
    set "PY_FILE=python-3.13.16-amd64.exe"
    set "EXPECTED_SHA256=fb4f9f5d438b2396da0086dc70b935c530cb578e37adc6d354f7ad2037fee83b"
    goto :DOWNLOAD
)
if /i "%ARCH%"=="ARM64" (
    set "PY_FILE=python-3.13.16-arm64.exe"
    set "EXPECTED_SHA256=696e2226062c6ec3622c13f143d28336a856968518e49cb4f4c62513215a4f5d"
    goto :DOWNLOAD
)
if /i "%ARCH%"=="x86" (
    set "PY_FILE=python-3.13.16.exe"
    set "EXPECTED_SHA256=394ca84150ea428db952cb617c1163c49fbc30e47ec53048c26e6ae44265df07"
    goto :DOWNLOAD
)
echo.
echo [ERROR] Unsupported Windows processor architecture: %ARCH%
goto :FAIL

:DOWNLOAD
set "DOWNLOAD_URL=https://www.python.org/ftp/python/%PY_VERSION%/%PY_FILE%"
set "INSTALLER_FILE=%TEMP%\wardogs-python-%PY_VERSION%-%RANDOM%-%RANDOM%.exe"
echo [2/4] Downloading official Python %PY_VERSION% for %ARCH%...
echo       Source: www.python.org
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri $env:DOWNLOAD_URL -OutFile $env:INSTALLER_FILE -UseBasicParsing; $hash=(Get-FileHash -LiteralPath $env:INSTALLER_FILE -Algorithm SHA256).Hash; if ($hash -ine $env:EXPECTED_SHA256) { throw 'SHA-256 checksum does not match the official release.' }; Write-Host '[OK] Download verified against the official SHA-256 checksum.' } catch { Write-Host ('[ERROR] ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 goto :DOWNLOAD_FAILED

echo [3/4] Installing Python for all Windows users...
echo       Includes the Python launcher and Tkinter.
echo       This may require Windows Installer to finish its work.
start "" /wait "%INSTALLER_FILE%" /quiet InstallAllUsers=1 Include_launcher=1 InstallLauncherAllUsers=1 PrependPath=1 Include_tcltk=1 Include_pip=1 Include_test=0
set "INSTALL_RESULT=%errorlevel%"
del /q "%INSTALLER_FILE%" >nul 2>&1
if "%INSTALL_RESULT%"=="3010" goto :REBOOT_REQUIRED
if not "%INSTALL_RESULT%"=="0" goto :INSTALL_FAILED

echo [4/4] Checking the Python installation...
rem Check the pinned version before testing the launcher used by RUN ME.vbs.
py -3.13 -c "import sys, tkinter, ctypes; assert sys.version_info[:2] == (3, 13)" >nul 2>&1
if errorlevel 1 goto :VERIFY_FAILED
py -c "import sys, tkinter, ctypes; sys.exit(0 if sys.version_info[:2] >= (3, 10) and sys.version_info[0] == 3 else 1)" >nul 2>&1
if errorlevel 1 goto :VERIFY_FAILED

echo.
echo [OK] Python %PY_VERSION% installed successfully.
py --version
goto :SUCCESS

:DOWNLOAD_FAILED
echo.
echo [ERROR] Could not securely download and verify Python.
echo Check your internet connection, antivirus or proxy settings.
del /q "%INSTALLER_FILE%" >nul 2>&1
goto :FAIL

:INSTALL_FAILED
echo.
echo [ERROR] The Python installer exited with code %INSTALL_RESULT%.
echo Check whether another Python installer is running.
goto :FAIL

:VERIFY_FAILED
echo.
echo [WARNING] The installer completed, but the Python launcher
echo could not run a compatible Python with Tkinter.
echo Restart Windows and try this setup again, or check installed apps.
goto :FAIL

:REBOOT_REQUIRED
echo.
echo [NOTICE] Python setup requested a Windows restart.
echo Restart your PC before launching RUN ME.vbs.
goto :SUCCESS

:SUCCESS
echo.
echo ===========================================================
echo  SETUP COMPLETE
echo  Place RUN ME.vbs and wd_rf.py in the same folder.
echo  Double-click RUN ME.vbs to start the Range Finder.
echo ===========================================================
echo.
pause
exit /b 0

:FAIL
echo.
echo Setup did not finish. Python was not confirmed ready.
echo.
pause
exit /b 1
