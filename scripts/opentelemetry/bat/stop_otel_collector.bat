@echo off
setlocal
if not defined OTEL_COLLECTOR_CONTAINER_NAME set OTEL_COLLECTOR_CONTAINER_NAME=otel-collector
set IMAGE=otel/opentelemetry-collector-contrib:latest

echo Stopping OpenTelemetry Collector container...
docker rm -f %OTEL_COLLECTOR_CONTAINER_NAME% 2>nul

echo Removing OpenTelemetry Collector image...
docker rmi -f %IMAGE% 2>nul

echo OpenTelemetry Collector cleanup complete.
endlocal
