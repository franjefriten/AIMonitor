@echo off
setlocal enabledelayedexpansion

if "%~1"=="" (
  set CONTAINER_NAME=kafka
) else (
  set CONTAINER_NAME=%~1
)

echo Stopping Kafka container '%CONTAINER_NAME%'...
docker rm -f %CONTAINER_NAME% >nul 2>&1

echo Removing Kafka-related Docker volumes...
for /f "delims=" %%V in ('docker volume ls -q --filter name=kafka 2^>nul') do (
  echo   -> removing volume %%V
  docker volume rm -f %%V >nul 2>&1
)

docker volume prune -f >nul 2>&1

echo Kafka container and related volumes have been cleaned.
endlocal
