@echo off
setlocal

set SCRIPT_DIR=%~dp0
set CONFIG_PATH=%SCRIPT_DIR%..\prometheus.yaml
set IMAGE_NAME=prom/prometheus
set CONTAINER_NAME=prometheus

for /f "tokens=*" %%i in ('docker image inspect %IMAGE_NAME% 2^>nul') do set IMAGE_EXISTS=1
if not defined IMAGE_EXISTS (
  echo Pulling Prometheus image...
  docker pull %IMAGE_NAME%
)

echo Starting Prometheus container...
docker rm -f %CONTAINER_NAME% >nul 2>&1

docker run -d --name %CONTAINER_NAME% -p 9090:9090 -v "%CONFIG_PATH%:/etc/prometheus/prometheus.yaml" %IMAGE_NAME%

echo Ready! Prometheus running at http://localhost:9090
endlocal