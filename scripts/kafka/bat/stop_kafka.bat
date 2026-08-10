@echo off
setlocal
set CONTAINER=kafka
set IMAGE=apache/kafka:latest

echo Stopping Kafka container...
docker rm -f %CONTAINER% 2>nul

echo Removing Kafka image...
docker rmi -f %IMAGE% 2>nul

echo Kafka cleanup complete.
endlocal
