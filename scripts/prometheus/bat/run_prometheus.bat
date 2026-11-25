@echo off
setlocal

set SCRIPT_DIR=%~dp0
set CONFIG_PATH=%SCRIPT_DIR%..\prometheus.yaml
set IMAGE_NAME=prom/prometheus
if not defined PROMETHEUS_CONTAINER_NAME set PROMETHEUS_CONTAINER_NAME=prometheus
if not defined PROMETHEUS_HOST_PORT set PROMETHEUS_HOST_PORT=9090
set CONTAINER_NAME=%PROMETHEUS_CONTAINER_NAME%
set HOST_PORT=%PROMETHEUS_HOST_PORT%

for /f "tokens=*" %%i in ('docker image inspect %IMAGE_NAME% 2^>nul') do set IMAGE_EXISTS=1
if not defined IMAGE_EXISTS (
  echo Pulling Prometheus image...
  docker pull %IMAGE_NAME%
  if errorlevel 1 exit /b %errorlevel%
)

echo Starting Prometheus container...
docker run -d --name %CONTAINER_NAME% --add-host host.docker.internal:host-gateway -p %HOST_PORT%:9090 -v "%CONFIG_PATH%:/etc/prometheus/prometheus.yml" %IMAGE_NAME%
if errorlevel 1 exit /b %errorlevel%

echo Ready! Prometheus running at http://localhost:%HOST_PORT%
endlocal