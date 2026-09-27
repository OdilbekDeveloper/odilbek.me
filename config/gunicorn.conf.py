"""gunicorn configuration, used by the Docker image's CMD."""

import os

# Railway provides PORT; 8000 is the local default.
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# Small and fixed: a personal site's traffic is modest, and memory is what Railway bills.
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = 30
graceful_timeout = 30

# The worker heartbeat file goes to memory; a container's overlay filesystem can stall it.
worker_tmp_dir = "/dev/shm"

accesslog = "-"
errorlog = "-"
