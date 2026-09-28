# Implementation status and architecture decisions

Date: 27 September 2026. This matrix is the source of truth for what the delivered code actually does. The larger master prompt remains the target specification.

## Working end-to-end

- Login; create/open cases; isolated ownership and explicit collaborator membership.
- Draft intake and upload categories; config import; affected component selection; readiness checks and explicit partial investigation.
- Resumable chunked upload; ZIP/TAR/TAR.GZ and standalone files; immutable source hashes, versions, parsing status and validation errors.
- Archive traversal/link defenses, expansion limits, basic secret redaction, exact physical line/byte evidence references.
- Snapshot health from structured pod objects; error/warning list; captured versions when supplied.
- Search, bounded file windows, surrounding evidence, cursor pagination, time filters, chronological timelines, streamed CSV/JSONL/text exports with CSV formula neutralization.
- Ordered component investigation and shared chatbot workflow, direct and PVC/PV NFS path matching, configured filename discovery, service-inventory/config traversal, cycle limits and visible coverage gaps.
- Persisted findings and stages, immutable reviewer revisions, digest-bound reviewer approval, offline HTML report, revoked evidence access, delayed artifact purge.
- Versioned knowledge records and admin API for users/case membership.
- Separate API/worker processes; PostgreSQL queue; migrations; Docker deployment; restricted runtime DB role with append-only audit permissions.
- Mock synthesis and a configurable company-compatible provider with authorized evidence tools; no live company endpoint was used.

## Deliberate implementation choices

The small initial deployment uses PostgreSQL with a trigram index instead of OpenSearch, a transactional PostgreSQL job table instead of Temporal, and a private Docker artifact volume instead of S3. This makes the delivered deployment executable without operating three additional platforms. These are material deviations from the proposed architecture, not hidden implementations of those platforms. The modules separate these responsibilities for later replacement.

The API applies case authorization on every exposed evidence path. PostgreSQL runtime credentials are not superuser/owner credentials. Full PostgreSQL per-principal row-level security remains unimplemented; application isolation tests do not substitute for that additional defense.

The mock is deterministic triage, not a trained root-cause model. It identifies cited observations and follows supported/configured relationships. It deliberately stops short of claiming a confirmed root cause. Company-model output is supplementary synthesis and requires review.

## Remaining production acceptance work

| Capability | Current boundary / required follow-up |
|---|---|
| Corporate SSO | Local login works; RS256 bearer verification has local signature/claim tests; real IdP integration remains pending. Add and test full IdP browser redirect/callback and organization provisioning policy. |
| Representative scale | A 6 GiB synthetic ZIP64 archive with 1,572,864 records passed upload/indexing in 634.775 seconds. A real 5–6 GB compressed, five-day support bundle still needs representative benchmarking. |
| Parser coverage | Physical-line parser, JSON/YAML metadata and text descriptions; rich multiline event assembly, timestamp timezone inference, binary encodings and vendor-specific adapters need fixtures. |
| Storage mapping | Direct NFS export evidence/config mapping supported; captured PVC/PV NFS chains and static subpaths supported; CSI and dynamic subPathExpr remain unresolved. |
| Dependency certainty | Service JSON and config references supported; captured selector/EndpointSlice backend verification supported; historical identity tracking remains. |
| Knowledge use | Catalog revisions persist; automatic version-applicable knowledge retrieval is not yet connected to the engine. |
| Snapshot/version comparison | Upload revisions and conflicts retained; archive file/hash comparison works; explicit snapshot selection and semantic config diff UI remain. |
| Findings revisions | Approval digest and stale-evidence checks work; immutable reviewer JSON editing works; structured field editing, separate customer-facing report variants, and approval comments remain. |
| Search/export | PostgreSQL cursor/time search, timeline and streamed CSV/JSONL/text work; asynchronous export jobs and OpenSearch adapter remain. |
| Workflow durability | Jobs have cancellation/retry controls. Leased jobs restart at the activity boundary. Ingestion retries rebuild the upload; fine-grained chunk resume, scheduler retry policy and Temporal integration remain. |
| Deletion governance | Immediate app revocation and delayed purge work; restoration UI, legal holds, retention policies and external backup expiry need company policy/integration. |
| Compliance controls | No certification claim. Full RLS, independent audit sink, external malware scanner, enterprise secret manager, encrypted host storage and security assessment remain. |
| High availability | Single-host Compose deployment; clustered PostgreSQL/object storage, Helm rollout and disaster recovery must be validated for the target environment. |
| Model validation | Adapter contract tests use a fake HTTP client; real service rates, context, quality and internal TLS configuration await company endpoint details. |

Do not describe these remaining capabilities as implemented. This release is suitable for local evaluation with synthetic or appropriately approved data; promotion to enterprise production requires closing the applicable gates above.
