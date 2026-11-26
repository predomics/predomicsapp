#!/bin/sh
# PredomicsApp container entrypoint.
#
# The application runs as the unprivileged `app` user (uid 10001). Data volumes
# created by older images are owned by root, so when the container starts as
# root this script fixes the ownership of the data directory once and then
# drops privileges. When the container is started with an explicit non-root
# user (Kubernetes runAsUser, `docker run --user`), it runs the command as is.
#
# PREDOMICS_RUN_AS=root  keep running as root (development bind mounts only).
set -eu

DATA_DIR="${PREDOMICS_DATA_DIR:-/app/data}"

if [ "$(id -u)" = "0" ] && [ "${PREDOMICS_RUN_AS:-app}" != "root" ]; then
    mkdir -p "$DATA_DIR"
    # Only walk/chown when something is not owned by the app user yet.
    if [ -n "$(find "$DATA_DIR" ! -user app -print -quit 2>/dev/null)" ]; then
        echo "entrypoint: fixing ownership of $DATA_DIR for user app (uid 10001)"
        chown -R app:app "$DATA_DIR" || echo "entrypoint: WARNING: could not chown $DATA_DIR" >&2
    fi
    export HOME=/home/app
    exec setpriv --reuid=app --regid=app --init-groups "$@"
fi

exec "$@"
