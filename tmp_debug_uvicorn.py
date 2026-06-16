import os
import socket
import subprocess
import sys
import time

cmd = [
    sys.executable,
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "5025",
    "--log-level",
    "debug",
]
print('cmd', cmd)
proc = subprocess.Popen(
    cmd,
    cwd=os.getcwd(),
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    env=os.environ,
    text=True,
)
print('pid', proc.pid)
start = time.time()
started = False
while time.time() - start < 10:
    line = proc.stdout.readline()
    if line:
        print('line:', line.strip())
        if 'Application startup complete' in line or 'Uvicorn running on' in line:
            started = True
            break
    if proc.poll() is not None:
        print('process exited', proc.returncode)
        break
    time.sleep(0.1)
print('started', started, 'poll', proc.poll())
if started:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(('127.0.0.1', 5025))
        print('port connect succeeded')
    except Exception as exc:
        print('port connect failed', exc)
proc.terminate()
try:
    proc.wait(timeout=5)
except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait(timeout=5)
print('exit', proc.returncode)
