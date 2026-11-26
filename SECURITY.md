# Security

## Reporting a vulnerability

Please do **not** open a public issue for a security problem.

Use GitHub's private reporting instead: on
<https://github.com/predomics/predomicsapp>, open the **Security** tab and
choose **Report a vulnerability**. If that option is not available to you,
contact the maintainers through the address given on
<https://predomics.github.io> and ask for a private channel before sending
details.

Please include the version (`/health` shows it), how the instance is deployed
(base Compose stack, production stack, Helm, other), and the steps to reproduce.
We aim to acknowledge reports within a week.

## Supported versions

Fixes are made on `main` and shipped in the next tagged release. Older tags are
not patched: upgrade to the latest release.

## What operators are responsible for

PredomicsApp is usually installed by a lab on its own server. The deployment
guide has a [security checklist](DEPLOYMENT.md#security-checklist); the points
that matter most:

- use the production stack (TLS, no published application or database ports)
  for anything reachable beyond your own machine;
- set a long random `PREDOMICS_SECRET_KEY` and `POSTGRES_PASSWORD`;
- keep the demo account off (`PREDOMICS_SEED_DEMO`), and close registration
  (`PREDOMICS_REGISTRATION_ENABLED=false`) unless open sign-up is intended —
  every registered user can upload files and launch computations;
- with open sign-up, consider requiring a confirmed email address
  (`PREDOMICS_REQUIRE_EMAIL_VERIFICATION=true`) and a storage quota per user
  (`PREDOMICS_USER_QUOTA_MB`);
- if another proxy sits in front of the bundled NGINX, declare it
  (`NGINX_TRUSTED_PROXY`), otherwise rate limiting cannot tell clients apart;
- never run a public instance with `PREDOMICS_DEBUG=true`;
- back up the database and the data volume, off the server.

## Built-in protections

So that reports can focus on what is not already intended behaviour:

- sessions are JWTs valid 8 hours, invalidated by a password change; API keys
  are stored hashed; repeated failed logins are slowed down (per account and
  per client address) on top of the request rate limit;
- uploaded file names never reach the file system as given, and every write is
  confined to the data directory; uploads have a size limit;
- every project, dataset and job route checks the caller's access to that
  object;
- webhooks can only target public addresses unless the operator allows
  otherwise;
- the production proxy enforces a Content Security Policy without inline
  scripts or `eval`, discards client-supplied `X-Forwarded-For`, and does not
  expose `/metrics`;
- the websocket takes a single-use ticket, not the session token.

## Scope notes

- **Endpoints that are public on purpose** (no authentication, no user data):
  `/health`, `/health/ready`, `/api/samples/` (the demo datasets bundled with
  the application), `/api/admin/templates/public` (parameter templates
  published by the administrator), the Signature Zoo listing (signatures users
  chose to publish, without their email), `/api/public/{token}` (a project its
  owner shared by link), and — unless `PREDOMICS_API_DOCS=false` — the API
  documentation. Reports that these are reachable without login are expected
  behaviour.
- The session token is kept in the browser's local storage; the Content
  Security Policy is the mitigation against script injection reading it.

- The base `docker-compose.yml` is meant for local use: it publishes its ports
  on `127.0.0.1` only and uses a default database password.
- Uploaded datasets and results are stored unencrypted in the data volume;
  protect the host and the backups accordingly.
- Feature identifiers of the `msp_…` form are sent to `biobanks.gmt.bio` to
  fetch annotations (see DEPLOYMENT.md, "Network access").
