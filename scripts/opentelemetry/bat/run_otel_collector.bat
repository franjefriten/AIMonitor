@echo off
setlocal

set SCRIPT_DIR=%~dp0
set CONFIG_PATH=%SCRIPT_DIR%..\otel-collector.yaml
set IMAGE_NAME=otel/opentelemetry-collector-contrib:latest
if not defined OTEL_COLLECTOR_CONTAINER_NAME set OTEL_COLLECTOR_CONTAINER_NAME=otel-collector
if not defined OTEL_COLLECTOR_BEARER_TOKEN set OTEL_COLLECTOR_BEARER_TOKEN=integration-test-token

for /f "tokens=*" %%i in ('docker image inspect %IMAGE_NAME% 2^>nul') do set IMAGE_EXISTS=1
if not defined IMAGE_EXISTS (
  echo Pulling OpenTelemetry Collector image...
  docker pull %IMAGE_NAME%
  if errorlevel 1 exit /b %errorlevel%
)

echo Starting OpenTelemetry Collector container...
docker rm -f %OTEL_COLLECTOR_CONTAINER_NAME% >nul 2>&1
docker run -d --name %OTEL_COLLECTOR_CONTAINER_NAME% -p 4318:4318 -p 13133:13133 -e OTEL_COLLECTOR_BEARER_TOKEN=%OTEL_COLLECTOR_BEARER_TOKEN% -v "%CONFIG_PATH%:/etc/otelcol-contrib/config.yaml:ro" %IMAGE_NAME% --config=/etc/otelcol-contrib/config.yaml
if errorlevel 1 exit /b %errorlevel%

echo OpenTelemetry Collector running with OTLP/HTTP at http://localhost:4318
endlocal
