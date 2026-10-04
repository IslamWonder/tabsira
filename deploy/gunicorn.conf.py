"""
gunicorn settings of the TABSIRA API in production.

Used by deploy/systemd/tabsira-api.service and by the pre-flight boot of
deploy/api-roll.sh (which overrides the bind address and the worker count on
its command line).

The master reads this file once, when it starts. What may change while it
runs is the number of workers: deploy/api-roll.sh adds and retires workers with
TTIN and TTOU until the count matches API_WORKERS, so changing that value in
the environment file needs no restart. Everything the application itself
reads (database, keys, flags) comes from the environment file through its own
settings, in each worker, so it is fresh whenever a worker is replaced.

No pid file here: the unit passes --pid, and the pre-flight boot must never
write the live API's.
"""

from __future__ import annotations

import os
from pathlib import Path


def _dotenv(path: Path) -> dict[str, str]:
    """Read KEY=VALUE lines; enough for the few keys this file needs."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip().removeprefix("export ").strip()] = value
    return values


_ENV = {**_dotenv(Path(os.environ.get("ENV_FILE", "/srv/tabsira/shared/.env"))), **os.environ}


bind = f"{_ENV.get('API_HOST', '127.0.0.1')}:{_ENV.get('API_PORT', '8000')}"
workers = int(_ENV.get("API_WORKERS") or 2)
worker_class = "uvicorn_worker.UvicornWorker"

# A worker that is being retired (TTOU, a reload, a stop) has this long to finish its requests.
graceful_timeout = 30
# A silent worker is killed after this long; a scan is answered quickly and streams its progress separately.
timeout = 120
keepalive = 5

# Heartbeat files on tmpfs, so a slow disk never makes a healthy worker look dead.
worker_tmp_dir = "/dev/shm"

# Only nginx, on this host, may say who the visitor is (X-Forwarded-For): the
# rate limit and the admin audit log read it. gunicorn hands this list to the
# uvicorn worker as its trusted proxies, so uvicorn honours proxy headers from
# 127.0.0.1 and from nothing else. nginx binds loopback and the API listens
# there only, so no other peer can reach it.
forwarded_allow_ips = "127.0.0.1"

# Recycle a worker now and then, with jitter so they do not all go at once, to bound slow memory growth.
max_requests = 5000
max_requests_jitter = 500

# nginx keeps the access log; the application and gunicorn write to the journal.
accesslog = None
errorlog = "-"
loglevel = "info"
