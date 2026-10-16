from fastapi import FastAPI
import socket
import sys
import time
import psutil

app = FastAPI()
START_TIME = time.time()

@app.get("/api/python/health")
def health():
    return {"status": "ok", "service": "python-api"}

@app.get("/api/python/status")
def status():
    return {
        "status": "running",
        "service": "Python Microservice",
        "pythonVersion": sys.version.split()[0],
        "hostname": socket.gethostname(),
        "cpuPercent": psutil.cpu_percent(interval=0.1),
        "memoryPercent": psutil.virtual_memory().percent,
        "uptimeSec": round(time.time() - START_TIME, 1),
    }
