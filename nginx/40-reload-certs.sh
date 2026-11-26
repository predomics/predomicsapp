#!/bin/sh
# Mounted into /docker-entrypoint.d/ of the nginx container.
# Certbot renews certificates in a separate container; nginx only reads them
# when it (re)loads its configuration, so reload periodically in the background.
(
    while :; do
        sleep 21600
        nginx -s reload
    done
) > /dev/null 2>&1 &
