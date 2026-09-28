# Operations and recovery

## Services

`web` serves the UI and proxies `/api`; `api` handles authenticated requests; `worker` consumes leased jobs; `migrate` applies schema migrations and bootstrap; `postgres` persists metadata, indexed evidence and jobs. The database is not published to the host. Only localhost:8097 is exposed.

```sh
docker compose ps
docker compose logs --tail 100 api worker
curl --fail http://localhost:8097/api/health
```

Do not dump `.env`, authentication headers, database connection strings, or model keys into shared diagnostic logs. General worker logs contain job IDs and error classes rather than raw customer messages.

## Start, stop and update

```sh
docker compose up -d --build
docker compose stop
docker compose start
```

Never use `docker compose down -v` unless intentionally destroying the entire local installation. Named volumes retain evidence and metadata across container replacement. Apply source updates and migration changes together and take a backup first. Keep image IDs and the dependency lockfiles for repeatable builds.

## Consistent backup

Before backing up, stop writes by stopping web/API/worker while leaving PostgreSQL running. Back up the database and artifact volume as one maintenance operation. Store backups in an approved encrypted destination, separate from source control.

```sh
docker compose stop web api worker
docker compose exec -T postgres pg_dump -U cpe -d cpe -Fc > /approved/backup/cpe.dump
docker compose run --rm --no-deps -T --user 0 \
  -v /approved/backup:/backup api \
  tar -czf /backup/artifacts.tar.gz -C /data .
docker compose start api worker web
```

`/approved/backup` is a placeholder to replace. The elevated temporary backup container is an explicit operator action; ordinary application containers remain non-root. Backups contain customer data and require the same retention/access controls. A fully automated encrypted backup/restore pipeline is not included.

Restore only into a separate test deployment first. Restore database and artifacts from the same maintenance window, reapply any deletion tombstones issued after that backup, verify evidence hashes and permissions, and then test login, search and report access. Never bring restored deleted content online before reconciliation. Production recovery objectives must be defined and measured by the operations team.

## Worker failures

Jobs are durably stored and claimed with row locks. A Running job whose lease expires after five minutes can be reclaimed. Extraction/indexing emits progress heartbeats; model calls have a shorter timeout. Failed jobs are visible in the Jobs tab, with explicit retry and cancellation controls. This release does not automatically retry permanently failed input; correct a malformed bundle and upload a new version. Multiple long model turns can outlast the current lease between stage heartbeats; keep one worker until lease fencing and independent renewal are implemented and validated. The API and file explorer remain available if the model endpoint fails.

## Deployment hardening

For company rollout: configure TLS, exact origin, Secure cookies, IdP integration, internal model host allowlist, private registry images, approved encrypted storage and backups, container memory/CPU/scratch quotas, network policy, secrets delivery, and access policy. Keep runtime database credentials separate from migration credentials. Test the production profile with the company environment rather than treating the local Compose run as a high-availability deployment.

### Detailed preliminary supplements

Investigation runs can carry an immutable analyst-prepared HTML supplement. The
Investigation panel shows **View detailed report** and **Download detailed preliminary HTML**
when one is attached. Both deliver identical saved bytes. These unapproved supplements
are separate from the automated, approved findings report and do not change its digest.
The mock provider does not automatically generate this richer analysis.

An operator can attach a reviewed local artifact using `scripts/attach_preliminary_report.py`
inside the API container with `PYTHONPATH=/app`. Supply JSON on stdin with `html` and an
`evidence` object containing `case_id`, `run_id`, `revision`, and the cited `evidence`
array (`file_id` and `sha256`). The importer validates active source uploads against the
run, pins its digest and the artifact hash, refuses replacement with different content,
and records a maintenance audit entry. Keep customer artifacts in the private data
volume, outside source distributions. The download requires case access; deletion of
source evidence invalidates the run and removes the supplement. Historical supplements
remain pinned to the original run/revision when newer investigations are created.

### Automatic detailed preliminary reports (preliminary-v2)

Completed investigations and saved findings revisions now generate their own detailed
preliminary HTML automatically. Existing completed runs expose **Generate detailed
preliminary report** in Investigation; investigator/reviewer/admin access is required.
Generation is idempotent and preserves any existing analyst-prepared supplement.
Preview and download return the same artifact, pinned to the run digest and revision.
Approved reports and their approval payloads are unchanged.

The mock-compatible generator is deterministic, not free-form LLM reasoning. It combines
run findings/stage citations with INFO-level request counters and success records from
product files actually reached by that run. Mapped file IDs are pinned in new runs; historical runs recover exact mapped paths from their saved NFS stage, so an uncited newer file is not skipped. Supplemental scanning is limited to 16 file
IDs and 3,000 indexed lines per unique file hash. It does not apply an incident-time filter
to this supplemental scan; the report discloses the scope and requires timestamp/source
comparison. It shows up to 12 failed and 12 successful counter samples and 100 selected
timeline entries. Hash duplicates are scanned once, counters are not summed across files,
and absent signatures never establish health. Hypotheses require engineer validation.
