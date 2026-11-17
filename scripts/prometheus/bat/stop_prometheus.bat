@echo off
setlocal
if not defined PROMETHEUS_CONTAINER_NAME set PROMETHEUS_CONTAINER_NAME=prometheus
set CONTAINER=%PROMETHEUS_CONTAINER_NAME%
set IMAGE=prom/prometheus

echo Stopping Prometheus container...
docker rm -f %CONTAINER% 2>nul

echo Removing Prometheus image...
docker rmi -f %IMAGE% 2>nul

echo Prometheus cleanup complete.
endlocal
