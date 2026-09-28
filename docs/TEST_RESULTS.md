# Validation results

Validated locally on Docker Desktop, 27 September 2026, using synthetic evidence and the mock model.

| Check | Result |
|---|---|
| `make test` | 49 backend tests passed; frontend TypeScript/Vite compilation passed |
| `make test-e2e` | 2 Chromium tests passed in 9.1 seconds: full case/upload/investigation/evidence/chat/approval/report workflow and mobile layout |
| `make verify` | Complete build/deploy/test/browser/health workflow passed on the final source |
| Application restart | Session survived; 8-file manifest unchanged; approved HTML report SHA-256 unchanged |
| `make health` | API returned `status: ok`, version `0.1.0` |
| Concurrent API smoke | 5 clients, 100 requests, 0 errors; p50 22.1 ms, p95 42.3 ms on a small synthetic case |
| PostgreSQL runtime role | Not superuser; cannot create databases; can insert audit records but cannot update or delete them |
| 6 GiB ingestion | 6,442,451,204 archive bytes; 1,572,864 records; upload 70.178 s; upload plus indexing 634.775 s; tail window 15.2 ms |
| 64 MiB ingestion | 130,561 physical lines indexed in 8.75 seconds including upload; tail window retrieved in 12.4 ms (earlier run) |

Backend coverage includes archive traversal/symlink/expansion rejection, TAR variants, case isolation, CSRF, reviewer permissions, stale approvals, immutable reviewer revisions, deletion revocation, late-file failure retrieval, timestamp/export consistency, job cancellation, timelines, hash comparison, namespace-aware service resolution, PVC/PV mappings, provider evidence-tool authorization, YAML alias rejection before expansion, and signed OIDC claim validation with a locally mocked key resolver.

Browser screenshots are `dashboard.png`, `investigation.png`, and `mobile.png`. `synthetic-approved-report.html` was downloaded through the real approval flow. The host browser could not launch under the desktop sandbox; browser tests ran in isolated Chromium within Docker against the deployed application.

One dependency deprecation warning remains in Starlette's use of httpx TestClient. No real company model endpoint, customer archive, corporate IdP, disaster-recovery restore, or multi-host failover was tested. Synthetic throughput does not establish representative customer performance or root-cause accuracy. See `IMPLEMENTATION_STATUS.md` for production acceptance gaps.

The 6 GiB test used one ZIP64 ZIP_STORED file of repetitive 4,096-byte records. It verifies the upload/extraction/indexing size boundary and tail navigation, not realistic compression, mixed-file parsing or model investigation quality. The initial benchmark generator needed ZIP64 enabled before this successful run. The final YAML alias guard does not affect this unstructured log path. Raw measurements are in `ingestion-benchmark-6144MiB.json`.

## NUL-byte ingestion regression

Mixed log content containing NUL bytes now indexes with visible U+2400 symbols. Original bytes, SHA-256, line numbers and byte offsets are preserved; per-file metadata records the replacement count. Regression tests cover mixed UTF-8/binary bytes, redaction, search, failure-message sanitization and successful reingestion clearing prior errors. This is byte-tolerant UTF-8 parsing, not automatic decoding of UTF-16 or arbitrary binary formats.

Relative archive filenames containing colons are accepted as logical names; extracted data still uses generated IDs. Regression tests retain rejection of drive-qualified, absolute, traversal, backslash and NUL paths. The NUL/path patch was validated with the backend suite; the earlier browser and full `make verify` results above refer to the initial platform release.

## Incomplete-investigation corrections

49 backend tests pass after adding incomplete-summary/approval protections, rejection of the saved sample target, late-file pod-description retrieval, and PVC/subpath mapping with negative cross-volume coverage. Frontend TypeScript/Vite compilation passes. Older incomplete runs receive an explanatory warning in the UI without modifying their persisted summaries or approval digests.

Structured lowercase levels (`level=error`, JSON `level: warning`) now normalize to ERROR/WARN. Explicit level fields take precedence over severity words inside the message. Regression coverage includes certificate-style Go logfmt entries.

## Storage verification guidance

51 backend tests pass locally. Tests verify that matching captured PVC/PV bindings clear the storage gap on a new run, and that missing objects, mismatched claim UIDs and non-NFS sources remain unverified. Frontend compilation passes with inline collection guidance and separate heading/action layout. Existing historical runs retain their original evidence assessments.

Evidence-preview limits no longer mark a fully verified PVC/PV mapping as Partial. The regression fixture uses multiline storage snapshots exceeding the citation-preview limit, while genuine analysis retrieval limits remain tracked. Full backend suite: 51 passed; updated investigation regression suite: 6 passed.

### Preliminary report parity fix
- Backend: 52 tests passed, including identical preview/download bytes, integrity failure,
  anonymous denial, and invalidated-run denial for preliminary supplements.
- Docker frontend TypeScript/Vite build passed; API, worker and web rebuilt/deployed.
- Deployed supplement preview/download SHA-256 matched the original analyst HTML exactly.
- Health endpoint returned OK. This change attaches analyst-authored supplements; it does
  not claim mock-model generation of the detailed hypothesis report.

### Automatic per-run detailed reports
- 55 backend tests passed, including automatic generation, idempotency, deletion revocation,
  pinned-upload isolation, mapped files without error citations, INFO request counters, HTML escaping and evidence-anchor integrity.
- Docker TypeScript/Vite build passed.
