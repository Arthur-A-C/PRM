#!/bin/sh
# PRM container entrypoint. Inside a container "localhost" is the container itself, so a database URL
# copied from the Windows .env (127.0.0.1/localhost) is pointed at the Docker host instead.
# Nothing else is changed; the URL itself (credentials included) is never printed.
set -eu

if [ -n "${PRM_DATABASE_URL:-}" ]; then
  PRM_DATABASE_URL="$(python - <<'PY'
import os
from urllib.parse import urlsplit, urlunsplit
url = os.environ["PRM_DATABASE_URL"]
target = os.environ.get("PRM_DOCKER_DB_HOST", "host.docker.internal")
parts = urlsplit(url)
if parts.hostname in {"127.0.0.1", "localhost", "::1"} and target:
    credentials, _, hostport = parts.netloc.rpartition("@")
    port = f":{parts.port}" if parts.port else ""
    netloc = (credentials + "@" if credentials else "") + target + port
    url = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
print(url)
PY
)"
  export PRM_DATABASE_URL
fi

exec "$@"
