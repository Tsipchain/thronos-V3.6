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
