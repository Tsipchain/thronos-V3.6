# Gunicorn configuration for Thronos blockchain nodes
# Handles graceful scheduler shutdown before worker processes exit

import os

# Bind configuration
bind = f"0.0.0.0:{os.getenv('PORT', 8000)}"

# Worker configuration
workers = 1  # Single worker to avoid scheduler conflicts
worker_class = "gthread"
threads = 32  # Match CPU cores for maximum concurrency
timeout = 120
graceful_timeout = 30

# Do NOT preload: with preload_app=True, gunicorn imports the WSGI app
# BEFORE binding the port. server.py module-level init (Redis, AI, file I/O)
# can take 30-60s, causing Render/Railway "No open HTTP ports" timeout.
# With preload_app=False and workers=1, gunicorn binds the port first,
# then the single worker imports server.py. No scheduler duplication risk.
preload_app = False

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Worker lifecycle hooks
def worker_exit(server, worker):
    """
    Called when a worker exits. This runs BEFORE the worker's thread pool shuts down,
    giving us a chance to gracefully stop schedulers before they try to submit jobs
    to a defunct executor.
    """
    print(f"[GUNICORN] Worker {worker.pid} exiting, shutting down schedulers...")

    # Import here to avoid issues during config loading
    try:
        from server import _shutdown_all_schedulers
        _shutdown_all_schedulers()
        print(f"[GUNICORN] Schedulers shut down successfully for worker {worker.pid}")
    except Exception as e:
        print(f"[GUNICORN] Error shutting down schedulers: {e}")

def on_exit(server):
    """
    Called when the Gunicorn master process exits.
    """
    print("[GUNICORN] Master process exiting")
