@echo off
setlocal
set CONTAINER=kafka

echo Stopping Kafka container...
docker stop %CONTAINER% >nul 2>nul
echo Kafka container stopped.
endlocal
