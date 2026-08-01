@echo off
setlocal
set CONTAINER=prometheus
set IMAGE=prom/prometheus

echo Stopping Prometheus container...
docker rm -f %CONTAINER% 2>nul

echo Removing Prometheus image...
docker rmi -f %IMAGE% 2>nul

echo Prometheus cleanup complete.
endlocal
