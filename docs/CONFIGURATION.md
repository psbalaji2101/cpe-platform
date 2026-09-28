# Configuration reference

All settings use the `CPE_` environment prefix. `backend/cpe/config.py` is the typed source of defaults. Unknown environment variables do not change application behavior.

| Setting | Meaning |
|---|---|
| DATABASE_URL | SQLAlchemy PostgreSQL URL; SQLite is only for development/tests |
| DATA_DIR | Private artifact volume, `/data` in Compose |
| ORIGIN | Exact browser origin for cross-origin mutation rejection |
| SECURE_COOKIES | Set true behind HTTPS |
| ADMIN_EMAIL / ADMIN_PASSWORD | Initial account, used by migration/bootstrap container only |
| RUNTIME_PASSWORD | Password for the restricted application database role; bootstrap only |
| SESSION_HOURS | Session expiry, default 8 hours |
| MAX_UPLOAD_BYTES | Default 8 GiB |
| MAX_EXPANDED_BYTES | Default 100 GiB; measured during extraction |
| MAX_ARCHIVE_FILES | Default 250,000 |
| CHUNK_BYTES | Default 8 MiB; nginx limit must be larger |
| MAX_RECORD_BYTES | Default 1 MiB; oversized physical lines are omitted with visible coverage metadata |
| RECOVERY_DAYS | Default 7 days before purging soft-deleted bytes; finalize with company policy |
| LLM_PROVIDER | `mock` or `compatible` |
| LLM_BASE_URL | Approved company API base, usually ending in `/v1` |
| LLM_MODEL | Exact deployed model identifier |
| LLM_API_KEY / LLM_API_KEY_FILE | Server-side secret or mounted secret file |
| LLM_ALLOWED_HOSTS | Comma-separated exact host allowlist |
| LLM_ALLOW_HTTP | Default false; do not enable for production customer data |
| LLM_TIMEOUT | Request timeout, default 90 seconds |
| LLM_CONTEXT_TOKENS | Reported capacity, default 1,000,000; validate against endpoint |
| LLM_MAX_OUTPUT_TOKENS | Default 4,096 |
| OIDC_ISSUER / OIDC_AUDIENCE / OIDC_JWKS_URL | Optional RS256 bearer-token verification for explicitly provisioned users; not a complete browser SSO flow |

Only settings explicitly present in the Compose environment block are forwarded from `.env`. Add additional settings under `environment` in a Compose override or your Helm/deployment configuration. API and worker must share data, database, model, and limit settings. The bootstrap account password does not rotate existing accounts on every restart.

## Investigation config adapter

The first adapter accepts JSON/YAML with `components`, each requiring `id`, `namespace`, explicit `pod_names`, and optional container/pattern/service mappings. `archive_path_mappings` contains `nfs_export` and `archive_prefix`. See the synthetic example.

Mount discovery supports direct NFS exports and captured PVC-to-PV NFS chains. Container mount paths and subpaths constrain matching. Dynamic subPathExpr and unresolved CSI volumes remain visible evidence gaps. Service traversal uses namespace-aware references, captured selectors and EndpointSlices, and refuses conflicting configured ownership. Pod selectors alone are not resolved by this adapter; provide exact observed pod names until that adapter is extended. Product filename patterns use bounded glob matching, never executable code.

The configuration is a case mapping, not a kubeconfig. Do not upload credentials or raw Kubernetes Secrets. Archived config is evidence; importing the case mapping is a separate, explicit operation.

## Provider contract

The company adapter posts to `BASE_URL/chat/completions`, with the configured model and bearer key. Its only tool is `read_evidence(event_id)` over source IDs already supplied by the server. Unknown tools or out-of-scope IDs fail closed. The final object must contain `summary` and `evidence_ids`. The code allows six bounded model turns and four calls per batch. Redirects and environment proxy inheritance are disabled.

The model summarizes the server-directed investigation; it does not decide authorization, health counts, archive deletion, stage clearance, or report approval. Citation identity validation is not proof of logical correctness, so summaries still require human review.

## PVC/subpath archive mapping

When the pod description captures a PVC mount and static subpath, an archive mapping may contain `namespace`, `pvc_claim`, `mount_subpath`, and `archive_prefix` instead of `nfs_export`. The engine verifies that the subpath mount names the same volume that references the claim. This permits product-log inspection with an explicit coverage gap: the backing PV/NFS export is not verified. Use actual observed archive prefixes. The default UI starts with an empty mapping; the old `example.processor` sample is rejected as an investigation target.

Combined pod descriptions are searched for the selected pod header before fetching its bounded description block; pod descriptions late in a large file are no longer missed by a leading-line retrieval limit.

### Closing storage verification gaps

Upload captured PVC and PV YAML/JSON under Cluster snapshot. For the description-backed mapping, the PVC must identify `spec.volumeName`; that PV must reference the same claim namespace/name and matching UID when supplied, and contain `spec.nfs.server` and `spec.nfs.path`. A new investigation records the verified source file IDs in `coverage.verified_storage` and removes this particular gap. Missing, ambiguous, mismatched or CSI-only objects keep the limitation visible. Product-log analysis is permitted through the description-backed mapping while this verification remains incomplete. Do not treat a present-day snapshot as proof of historical storage configuration.
