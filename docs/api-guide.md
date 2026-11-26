# API guide

Everything the web interface does goes through the HTTP API, so an analysis
can be scripted end to end. This guide walks through one: authenticate, upload
data, launch a job, follow it, read the results, score new samples.

- Interactive reference of every endpoint: `/api/docs` on your instance
  (Swagger UI; `/api/redoc`, `/api/openapi.json`). An administrator can switch
  it off with `PREDOMICS_API_DOCS=false`.
- The commands below were run as written against a test instance; outputs are
  shortened. Replace `https://predomics.example.org` by your instance and use
  your own files.

```bash
B=https://predomics.example.org
```

## Conventions

- Requests and responses are JSON, except file uploads (`multipart/form-data`).
- Errors have one shape, whatever the status code:

  ```json
  {"error": {"code": "HTTP_422", "message": "Webhook URL must point to a public address"}}
  ```

  Validation errors (`422`) additionally carry `detail`, the list of fields
  that were wrong.
- Every response has an `X-Request-ID` header. Quote it when reporting a
  problem: the administrator can find the request in the logs with it.
- Limits: 100 requests per minute per user by default; logins, password resets
  and uploads have stricter limits. A `429` response carries `Retry-After`
  (seconds).

## 1. Authenticate

Two ways. For scripts, prefer an **API key**.

### Session token

```bash
curl -s -X POST $B/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"ada@example.org","password":"correct-horse-battery"}'
```

```json
{"access_token": "eyJhbGciOiJIUzI1NiIs…", "token_type": "bearer"}
```

Send it as `Authorization: Bearer <token>`. It is valid for 8 hours by default
(`PREDOMICS_ACCESS_TOKEN_EXPIRE_MINUTES`); `POST /api/auth/refresh` with a
still-valid token returns a fresh one. Changing the password invalidates every
token issued before.

After several wrong passwords the server makes you wait (`429`,
`Retry-After: 30`, doubling up to 15 minutes).

### API key

Create one once (web interface: Profile → API keys, or the call below). The key
is shown a single time.

```bash
TOKEN=…   # a session token, only needed to create the key
curl -s -X POST $B/api/auth/api-keys -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"name":"scripts"}'
```

```json
{"id": "194b6ad177c4", "name": "scripts", "prefix": "pk_9jq77", "key": "pk_9jq77v…", "created_at": "…"}
```

Send it in the `X-API-Key` header on every request (not in `Authorization`):

```bash
KEY=pk_9jq77v…
curl -s $B/api/auth/me -H "X-API-Key: $KEY"
```

`GET /api/auth/api-keys` lists your keys (never their value);
`DELETE /api/auth/api-keys/{id}` revokes one.

## 2. Create a project and upload the data

```bash
curl -s -X POST "$B/api/projects/?name=Cirrhosis%20demo" -H "X-API-Key: $KEY"
```

```json
{"project_id": "a59d7e5a63f5", "name": "Cirrhosis demo", "datasets": [], "jobs": [], "…": "…"}
```

Upload each file with its **role** — `xtrain`, `ytrain`, and optionally
`xtest`, `ytest`, `metadata`. Without `role` it is guessed from the file name.

```bash
P=a59d7e5a63f5
curl -s -X POST "$B/api/projects/$P/datasets?role=xtrain" -H "X-API-Key: $KEY" -F "file=@Xtrain.tsv"
curl -s -X POST "$B/api/projects/$P/datasets?role=ytrain" -H "X-API-Key: $KEY" -F "file=@Ytrain.tsv"
curl -s -X POST "$B/api/projects/$P/datasets?role=xtest"  -H "X-API-Key: $KEY" -F "file=@Xtest.tsv"
curl -s -X POST "$B/api/projects/$P/datasets?role=ytest"  -H "X-API-Key: $KEY" -F "file=@Ytest.tsv"
```

```json
{"filename": "Xtrain.tsv", "n_features": 1980, "n_samples": 180, "features_in_rows": true, "…": "…"}
```

Format: tab- or comma-separated text; X has one row per feature and one column
per sample (first column = feature names, first row = sample names); y has one
row per sample (name, class `0`/`1`). Files larger than the instance's limit
(`PREDOMICS_MAX_UPLOAD_MB`, 500 MB by default) are refused with `413`; so is an
upload that would exceed your storage quota, if the instance has one
(`GET /api/auth/me/usage` → `{"used_bytes": …, "quota_bytes": …}`, 0 = no
quota).

The project now lists the files with their identifiers:

```bash
curl -s $B/api/projects/$P -H "X-API-Key: $KEY" \
  | jq -c '[.datasets[].files[] | {role, id}]'
```

```json
[{"role":"xtrain","id":"c7e134ce64f6"},{"role":"ytrain","id":"d69f377fd3d5"},
 {"role":"xtest","id":"0da6d3035986"},{"role":"ytest","id":"301e267ba075"}]
```

To try the API without data of your own, `POST /api/samples/qin2014_cirrhosis/load`
creates a project with the demo dataset already attached
(`GET /api/samples/` lists the demo datasets).

## 3. Launch an analysis

File identifiers go in the query string, the parameters in the JSON body. Only
what differs from the defaults has to be given; `GET /api/docs` describes every
section (`general`, `ga`, `beam`, `mcmc`, `cv`, `voting`, `importance`, …).

```bash
curl -s -X POST "$B/api/analysis/$P/run?x_file_id=c7e134ce64f6&y_file_id=d69f377fd3d5&xtest_file_id=0da6d3035986&ytest_file_id=301e267ba075&job_name=first-run" \
  -H "X-API-Key: $KEY" -H 'Content-Type: application/json' -d '{
    "general": {"algo": "ga", "language": "bin,ter", "data_type": "raw,prev", "fit": "auc", "seed": 42, "thread_number": 2},
    "ga": {"population_size": 500, "max_epochs": 30, "min_epochs": 10}
  }'
```

```json
{"job_id": "ffafb3d3438b", "name": "first-run", "status": "pending", "…": "…"}
```

The job is queued; the instance runs a limited number at a time. Files must
belong to the project (`404` otherwise). `thread_number` is capped by the
server. `POST /api/analysis/{project}/batch` launches a parameter sweep.

## 4. Follow the job

Poll its status:

```bash
J=ffafb3d3438b
curl -s $B/api/analysis/$P/jobs/$J -H "X-API-Key: $KEY" \
  | jq '{status, best_auc, best_k, duration_seconds, error_message}'
```

```json
{"status": "completed", "best_auc": 0.9976, "best_k": 66, "duration_seconds": 3.21, "error_message": null}
```

`status` is `pending`, `running`, `completed` or `failed`. A failed job says
why in `error_message` (a job interrupted by a server restart, or cancelled,
is `failed` with that explanation).

The console output, incrementally — pass the `next_offset` of the previous
answer to receive only what is new:

```bash
curl -s "$B/api/analysis/$P/jobs/$J/logs?offset=0" -H "X-API-Key: $KEY" \
  | jq '{size, next_offset, truncated, tail: .log[-60:]}'
```

```json
{"size": 68082, "next_offset": 68082, "truncated": false, "tail": "…train_auc=0.997640 test_auc=0.935556…"}
```

Stop a pending or running job:
`POST /api/analysis/{project}/jobs/{job}/cancel`. Delete a finished one:
`DELETE /api/analysis/{project}/jobs/{job}`.

### Live progress over a websocket

Browsers cannot send an `Authorization` header on a websocket, and a
credential in a URL ends up in logs. So the stream is opened with a **one-time
ticket**: ask for one, then connect within 30 seconds.

```bash
curl -s -X POST $B/api/auth/ws-ticket -H "Authorization: Bearer $TOKEN"
# {"ticket": "GA_4DL…", "expires_in": 30}
```

```python
import asyncio, json, websockets

async def follow(base_ws, project, job, ticket):
    async with websockets.connect(f"{base_ws}/ws/jobs/{project}/{job}?ticket={ticket}") as ws:
        async for raw in ws:
            msg = json.loads(raw)          # {"type": "status" | "log" | "progress" | "done", …}
            print(msg["type"], str(msg)[:80])
            if msg["type"] == "done":
                break

asyncio.run(follow("wss://predomics.example.org", "a59d7e5a63f5", "ffafb3d3438b", "GA_4DL…"))
```

A ticket works once; the session token is not accepted in the URL.

## 5. Read the results

```bash
curl -s $B/api/analysis/$P/jobs/$J/results -H "X-API-Key: $KEY" > results.json
jq 'keys' results.json
```

```json
["best_individual", "engine", "epsilon", "execution_time", "feature_cooccurrence",
 "feature_discovery", "feature_names", "fold_count", "generation_count",
 "generation_tracking", "population", "population_size", "sample_names",
 "stability", "timing", "zscore_stats"]
```

The best model: its metrics, and `features` as `{feature index: coefficient}`,
the index pointing into `feature_names`.

```bash
jq '.best_individual | {k, auc, accuracy, sensitivity, specificity, threshold, language, data_type}' results.json
jq -r '. as $r | .best_individual.features | to_entries[] | "\($r.feature_names[.key|tonumber] | split(";")[0])\t\(.value)"' results.json | head -3
```

```json
{"k": 66, "auc": 0.9976, "accuracy": 0.9778, "sensitivity": 0.9794, "specificity": 0.9759,
 "threshold": 6.0, "language": "ternary", "data_type": "prevalence"}
```

```text
msp_0024    1
msp_0041    1
msp_0068    -1
```

`population` holds the other models found (the family of best models);
`engine` records the engine version and commits that produced the result. The
file can be several megabytes. Exports for people rather than programs:
`GET /api/export/{project}/jobs/{job}/…` (HTML and PDF reports, CSV tables,
Python and R notebooks — see `/api/docs`).

## 6. Score new samples

Send the values of the features for the new samples: for each feature name, one
value **per sample**, in the order of `sample_names`. Features the model does
not use are ignored; the answer says which were matched.

```bash
curl -s -X POST $B/api/predict/$J -H "X-API-Key: $KEY" -H 'Content-Type: application/json' -d '{
  "sample_names": ["LV15", "HV26", "HV17"],
  "features": {"msp_0024": [0.0012, 0, 0], "msp_0041": [0.0003, 0, 0.0001], "msp_0068": [0, 0.0021, 0.0004]}
}'
```

```json
{"sample_names": ["LV15", "HV26", "HV17"], "scores": [13.0, 0.0, 1.0],
 "predicted_classes": [1, 0, 0], "threshold": 6.0, "matched_features": ["msp_0024", "…"]}
```

(The output above comes from sending all the features of the demo test set.)
A sample is class 1 when its score reaches the threshold. Scores are computed
exactly as the engine does for the model's language and data type. Models the
application cannot score (for instance a z-score model from a job run with
version 2.2.0 or earlier) are refused with `400` and an explanation rather than scored wrongly.

## 7. Be told when a job ends (webhooks)

```bash
curl -s -X POST $B/api/webhooks/ -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"name": "lab-bot", "url": "https://hooks.example.org/predomics", "events": ["job.completed", "job.failed"]}'
```

The answer contains a `secret`, shown once. The URL must be `http(s)` and
resolve to a public address (an instance's administrator can allow intranet
targets with `PREDOMICS_WEBHOOK_ALLOW_PRIVATE=true`); up to 10 webhooks per
user. `POST /api/webhooks/{id}/test` sends a test event.

Each delivery is a `POST` with a JSON body and the header
`X-Webhook-Signature: sha256=<hex>`: the HMAC-SHA256 of the body, keyed with
your secret. The body is JSON with sorted keys, so verify against the raw bytes
you received:

```python
import hashlib, hmac

def is_genuine(raw_body: bytes, signature_header: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header or "")
```

Reject requests that fail this check.

## Administration endpoints

For administrators (`is_admin`), under `/api/admin/` — see `/api/docs` for the
full list:

| Call | Purpose |
|---|---|
| `POST /api/admin/users` `{"email", "password", "full_name"}` | create an account (the way to add users when registration is closed) |
| `GET /api/admin/users`, `PATCH /api/admin/users/{id}`, `DELETE …` | list, activate/deactivate, promote, delete |
| `POST /api/admin/users/{id}/reset-password` `{"new_password"}` | set a user's password |
| `POST /api/admin/retention/run?dry_run=true` | what the retention rules would delete (`false` to do it) |
| `POST /api/admin/backup`, `GET /api/admin/backup/list`, `POST /api/admin/restore` | in-app backups |
| `GET /api/admin/audit-log` | who did what |

Operational endpoints: `GET /health` (liveness, versions), `GET /health/ready`
(database and storage; `503` when degraded), `GET /metrics` (Prometheus, only
with the instance's metrics token and never through the public proxy — see
DEPLOYMENT.md).

## Endpoints that need no authentication

By design, and without user data: `GET /health`, `GET /health/ready`,
`GET /api/samples/` (the demo datasets shipped with the application),
`GET /api/admin/templates/public` (parameter templates published by the
administrator), `GET /api/signature-zoo/` (published signatures, without
contributor emails), `GET /api/public/{token}` (a project its owner chose to
share by link), and the account endpoints (`register`, `login`,
`forgot-password`, `reset-password`, `verify-email`, `resend-verification`).
