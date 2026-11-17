@echo off
setlocal

if not defined PROMETHEUS_CONTAINER_NAME set PROMETHEUS_CONTAINER_NAME=prometheus
set CONTAINER_NAME=%PROMETHEUS_CONTAINER_NAME%

where docker >nul 2>nul
if errorlevel 1 (
  echo docker is required but not installed
  exit /b 127
)

docker restart %CONTAINER_NAME%
if errorlevel 1 exit /b 1

echo Prometheus restarted successfully.
endlocal
