# Gunicorn configuration file for dynamic worker scaling
# This allows environment variable control without requiring a shell

import multiprocessing
import os

# Dynamic worker calculation
# Set WEB_CONCURRENCY environment variable to override
# 0 or empty = auto-detect (2 * CPU + 1)
workers_env = os.getenv("WEB_CONCURRENCY", "0")

try:
    workers_count = int(workers_env)
    if workers_count <= 0:
        # Auto-detect: 2 * CPU + 1 (optimal for async workloads)
        workers = multiprocessing.cpu_count() * 2 + 1
    else:
        workers = workers_count
except ValueError:
    # Fallback to auto-detect if invalid value
    workers = multiprocessing.cpu_count() * 2 + 1

# Worker class for async support
worker_class = "uvicorn.workers.UvicornWorker"

# Threading for better CPU utilization
threads = 2

# Connection settings
worker_connections = 1000
keepalive = 5

# Timeouts
timeout = 60
graceful_timeout = 30

# Worker lifecycle management
max_requests = 10000
max_requests_jitter = 1000

# Binding
bind = "0.0.0.0:8000"

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()

# Performance optimizations
preload_app = True
reuse_port = True

# Use shared memory for IPC (faster than disk)
# Fallback to /tmp if /dev/shm not available
import os
worker_tmp_dir = "/dev/shm" if os.path.exists("/dev/shm") else None

# Optional: Server hooks for monitoring
def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info(
        f"Starting Gunicorn with {workers} workers "
        f"({multiprocessing.cpu_count()} CPUs detected)"
    )

def on_reload(server):
    """Called to recycle workers during a reload."""
    server.log.info("Gracefully reloading workers")

def worker_int(worker):
    """Called when a worker receives the SIGINT or SIGQUIT signal."""
    worker.log.info(f"Worker {worker.pid} received INT/QUIT signal")
