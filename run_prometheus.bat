@echo off
setlocal

:: Get cwd and set absolute path for docker container
set "CONFIG_PATH=%CD%\prometheus.yaml"

echo Setup prometheus docker container...
docker run -d ^
  --name "prometheus" ^
  -p "9090:9090" ^
  -v "%CONFIG_PATH%:/etc/prometheus/prometheus.yaml" ^
  "prom/prometheus"

echo Ready! Prometheus running in http://localhost:9090
pause