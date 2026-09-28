# CPE Evidence Workspace

A Dockerized, modular support-engineering application for offline Kubernetes and NFS log investigations. The default model provider is a deterministic mock. Real customer evidence is never needed to exercise the included example.

## Run locally

Requirements: Docker Engine/Desktop with Compose; Python 3 for generating local configuration. Optional host-side Python tests and benchmarks require Python 3.11+ (`make benchmark PYTHON=python3.11` when `python3` is older). Docker tests use the bundled Python 3.11 image.

The Makefile provides the common commands:

```sh
make help       # list commands
make up         # configure, build and deploy
make test       # backend/security tests and frontend build
make test-e2e   # browser tests against the running deployment
make verify     # deploy, test, browser-test, health check
make package    # source ZIP without credentials or dependencies
make status
make logs
make stop       # preserve all data
```

`make benchmark BENCHMARK_MIB=6144 BENCHMARK_LINE_BYTES=4096` runs the optional large synthetic boundary test. It creates substantial temporary data and retained test evidence. Do not run it against a busy production installation.

```sh
python3 scripts/configure.py
docker compose up -d --build
docker compose ps
```

For manual configuration, copy `.env.example` to `.env` and replace all placeholder passwords before starting Compose. The template includes every setting read from `.env` by the supplied Compose file.

Open [the application](http://localhost:8097). The generated `LOCAL_ACCESS.md` contains the local administrator login. Both it and `.env` are private, ignored by Git, and excluded from release archives. The application binds only to the local machine by default. Use your internal TLS ingress and secure cookies before exposing it to other machines.

## Exercise the complete workflow

1. Sign in and choose **Create new case**.
2. Enter a title and customer. The case is saved as a draft.
3. Upload `samples/synthetic-incident.zip` in the NFS logs card. The bundle contains several evidence categories and they are detected automatically. TAR and TAR.GZ equivalents are included.
4. Import `samples/investigation-config.json`, select `demo.processor`, and save the configuration.
5. Once ingestion shows Ready, choose **Create investigation**.
6. Follow Kubernetes checks → NFS discovery → product logs → the storage service → the storage component.
7. Open a citation to inspect its source lines. Ask the chatbot to explain the storage findings.
8. Review findings, then approve to generate and download the self-contained HTML report.

The synthetic case demonstrates an observed storage write failure. The tool deliberately does not label a deeper initiating cause as confirmed without enough evidence. Data, sessions, jobs, and reports survive container restarts through named volumes.

## Implemented modules

| Module | Implementation |
|---|---|
| Interface | React/TypeScript; responsive launcher, intake, dashboard, explorer, stage history, chat, archive management, knowledge catalog, settings |
| API | FastAPI with OpenAPI at `/api/docs` |
| Identity | Password hashing, expiring HttpOnly sessions, CSRF protection, roles, explicit case membership; optional verified OIDC bearer tokens for provisioned users |
| Evidence | Resumable chunk uploads; ZIP/TAR/TAR.GZ; standalone logs/config; bounded extraction; source hashes and byte/line coordinates |
| Search | PostgreSQL event index with trigram message index, structured filters and bounded cursor pagination |
| Workflow | PostgreSQL durable leased job queue, separate worker, progress, immutable run inputs, Kubernetes-first traversal |
| Model | Mock by default; approved-host OpenAI-compatible adapter with bounded `read_evidence` tool calls and structured response validation |
| Governance | Case audit trail, optimistic config edits, digest-bound approval, safe offline HTML, deletion revocation and delayed purge |
| Deployment | Separate web, API, worker, migration and PostgreSQL containers; non-root application processes and health checks |

## Configure the company model later

Set these entries in `.env` through your approved secret process:

```dotenv
CPE_LLM_PROVIDER=compatible
CPE_LLM_BASE_URL=https://approved-model-host.example.internal/v1
CPE_LLM_MODEL=exact-approved-model-id
CPE_LLM_ALLOWED_HOSTS=approved-model-host.example.internal
CPE_LLM_API_KEY=provide-through-your-secret-process
```

Then recreate API and worker:

```sh
docker compose up -d --force-recreate api worker
```

The endpoint must support `/chat/completions`, function tool calls, and tool-result continuation. Schema-enforced JSON mode is not assumed; the adapter validates JSON itself. Key-file support is available through `CPE_LLM_API_KEY_FILE` in the backend; mount a Docker/Kubernetes secret and pass that setting in your deployment override. Never paste keys into the UI or commit them.

The 1M context setting is configurable, but requests use bounded retrieved evidence. Real-model quality, exact API compatibility, TLS trust, rate limits, and capability testing remain required with your actual service. No public-model fallback exists.

## Test

Backend, from `backend/` inside a Python virtual environment:

```sh
pip install -r requirements.txt
PYTHONPATH=. pytest -q
```

Frontend, from `frontend/`:

```sh
npm ci
npm run build
npm exec playwright install chromium
npm run test:e2e
```

The browser suite expects the running local deployment and uses the generated credentials without printing them. It creates synthetic test cases. On Docker Desktop, use the isolated runner when a host browser cannot launch:

```sh
docker build -t cpe-evidence-browser-tests -f frontend/Dockerfile.e2e frontend
docker run --rm --shm-size=1g \
  --mount type=bind,source="$PWD",target=/project \
  --mount type=volume,target=/project/frontend/node_modules \
  cpe-evidence-browser-tests
```

The runner forwards its own localhost:8097 to the Docker Desktop host to test the same origin and CSRF behavior as the real browser. On Linux, add `--add-host=host.docker.internal:host-gateway` if needed. It does not mount the Docker socket.

## Maintain and operate

- [Evidence collection and input format](docs/EVIDENCE_COLLECTION.md)
- [Configuration reference](docs/CONFIGURATION.md)
- [Architecture decisions and implementation boundaries](docs/IMPLEMENTATION_STATUS.md)
- [Operations and recovery](docs/OPERATIONS.md)
- [Test results](docs/TEST_RESULTS.md)

This is a working local deployment and production-candidate foundation. It is not a claim that the entire enterprise specification has been validated: representative 6 GB archive tests, corporate SSO browser integration, high availability, storage policy, and the remaining capabilities in the implementation matrix must be completed before production acceptance.
