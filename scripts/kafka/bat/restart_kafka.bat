@echo off
setlocal

set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..\..\..") do set REPO_ROOT=%%~fI

where docker >nul 2>nul
if errorlevel 1 (
  echo docker is required but not installed
  exit /b 127
)

call "%SCRIPT_DIR%stop_kafka_container.bat"
call "%SCRIPT_DIR%run_kafka.bat"

echo Kafka restarted successfully.
endlocal
