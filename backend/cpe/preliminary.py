"""Private, immutable analyst-prepared supplements; never imply model generation or approval."""
import hashlib
import json
from .storage import artifact_path


def load_preliminary(run):
    if run.status == 'Invalidated':
        return None
    manifest = artifact_path('preliminary-manifests', run.id)
    content = artifact_path('preliminary-reports', run.id)
    if not manifest.exists() or not content.exists():
        return None
    try:
        meta = json.loads(manifest.read_text())
        body = content.read_bytes()
        if (meta['case_id'] != run.case_id or meta['run_id'] != run.id
                or meta['revision'] != run.revision
                or meta['run_digest'] != run.digest
                or meta['sha256'] != hashlib.sha256(body).hexdigest()):
            return None
        return meta, body
    except (KeyError, ValueError, OSError):
        return None


COMPLETED = {'Findings Ready', 'Partial', 'Awaiting Input', 'Approved'}


def generate_preliminary(db, run, actor='system:worker'):
    """Deterministic, bounded evidence review. Never upgrades a hypothesis to an RCA."""
    import html
    import re
    from datetime import datetime, timezone
    from sqlalchemy import select
    from .db import Case, Event, audit
    from .evidence import active_files, citation, validate_citations

    existing = load_preliminary(run)
    if existing and (existing[0].get('source') != 'Automated evidence review' or existing[0].get('template') == 'preliminary-v2'):
        return existing[0]
    if existing:
        artifact_path('preliminary-history-v1', run.id).write_bytes(existing[1])
    if run.status not in COMPLETED or not run.digest:
        raise ValueError('Complete the investigation before generating a preliminary report')
    case = db.get(Case, run.case_id)
    files = {f.id: f for f in active_files(db, run.case_id, run.evidence_ids)}
    refs = [r for f in run.findings for key in ('evidence', 'counterevidence') for r in f.get(key, [])]
    refs += [r for s in run.stages for r in s.get('evidence', [])]
    validate_citations(db, run.case_id, refs, run.evidence_ids)
    # Only expand files the ordered investigation actually reached, never all case archives.
    product_ids = sorted({r['file_id'] for s in run.stages if s['stage'] == 'Product log analysis'
                          for r in s.get('evidence', [])})
    # Older runs stored mapped paths in the NFS stage; newer runs also pin file IDs.
    reached = {s['component'] for s in run.stages if s['stage'] == 'Product log analysis'}
    selected_ids = set(product_ids)
    for stage in run.stages:
        if stage['stage'] != 'NFS log discovery' or stage['component'] not in reached:
            continue
        selected_ids.update(fid for fid in stage.get('file_ids', []) if fid in files)
        detail = stage.get('detail', '')
        if detail.startswith('Matched '):
            paths = detail[len('Matched '):].split('. Confirm that configured archive prefixes', 1)[0].split(', ')
            selected_ids.update(f.id for f in files.values() if f.path in paths and 'nfs_logs' in f.roles)
    product_ids = sorted(selected_ids)
    scope, rows, hashes = [], [], set()
    for fid in product_ids[:16]:
        f = files[fid]
        if f.sha256 in hashes:
            continue
        hashes.add(f.sha256)
        events = list(db.scalars(select(Event).where(Event.case_id == run.case_id, Event.file_id == fid)
                                 .order_by(Event.line).limit(3001)))
        scope.append({'path': f.path, 'read': min(len(events), 3000), 'truncated': len(events) > 3000})
        rows.extend(citation(e, f) for e in events[:3000])
    all_refs = {r['event_id']: r for r in refs}
    observations, hypotheses = [], []
    counters, failed_codes, certs, successes, restarts = [], [], [], [], []
    for r in rows:
        message = r['excerpt']
        m = re.search(r'Metric Data\s*\[requests=(\d+).*?failed requests=\s*(\d+)', message)
        if m:
            counters.append((r, int(m[1]), int(m[2])))
        if re.search(r'failed_requests\(status_code_5\d\d\)=[1-9]\d*', message):
            failed_codes.append(r)
        if 'no such file' in message.lower() and 'cert' in message.lower():
            certs.append(r)
        if re.search(r'successfully (?:acquired|updated)|successfully added to the cert pool|passing requests=\s*[1-9]|building completed', message, re.I):
            successes.append(r)
    for r in refs:
        if re.search(r'Restart Count:\s*\d+|restartCount', r['excerpt']):
            restarts.append(r)
    counter_count = len(counters)
    counters = [c for c in counters if c[2] > 0][:12] + [c for c in counters if c[2] == 0][-12:]
    for r, total, failed in counters:
        observations.append((f"Request counter sample: {failed} failed of {total} requests. This measures requests, not unique lost records.", [r]))
    if failed_codes:
        observations.append(('HTTP 5xx failures are recorded in aggregate counters; exact requests and failing hop remain unidentified.', failed_codes[:8]))
        hypotheses.append(('1 · Investigate first · Low causal confidence',
            'Transient application processing or downstream forwarding failure',
            'Failed request/status counters support an impact signal, but do not identify the initiating cause.', failed_codes[:8],
            [r for r, total, failed in counters if failed == 0][:8],
            'Successful samples may be from different windows or pods; compare each source and timestamp before inferring recovery.',
            'Recover failing request IDs and exact times. Follow caller → application handler → downstream response. Check retries and final storage before concluding data loss.'))
    if certs:
        observations.append(('An expected certificate file was unavailable. Check each excerpt for fallback behavior; customer impact is not established.', certs[:6]))
        hypotheses.append(('2 · Configuration check · Low causal confidence', 'Certificate provisioning or an intentionally omitted optional certificate',
            'Missing-file records support a configuration check; they do not establish an HTTP failure cause.', certs[:6], successes[:6],
            'Successful authentication or certificate loading elsewhere does not clear every connection. Optionality and intended policy must be verified.',
            'Check expected secret key names, mounted paths and certificate metadata against deployment policy. Correlate the actual failing TLS connection; do not export private keys.'))
    seen = set()
    for f in run.findings:
        key = (f['component'], f['title'])
        if key in seen:
            continue
        seen.add(key)
        observations.append((f"{f['component']}: {f['title']}. {f['explanation']}", f.get('evidence', [])))
        hypotheses.append(('Further check · Causal confidence not established', f['title'],
            'Investigate the mechanism behind this recorded finding; its deeper cause is not independently established.',
            f.get('evidence', []), f.get('counterevidence', []),
            'No contradictory evidence supplied for this finding.' if not f.get('counterevidence') else 'Review the cited counterevidence before accepting this hypothesis.',
            ' '.join(f.get('next_checks', []))))
    if not hypotheses:
        hypotheses.append(('Unresolved', 'Insufficient evidence for a ranked causal hypothesis',
            'No supported failure mechanism was retrieved. Absence of a signature is not proof of health.', [], [],
            'Coverage gaps and unexamined records prevent exclusion of failures.', 'Resolve intake gaps and capture the customer symptom, time window and request identifiers.'))
    esc = lambda x: html.escape(str(x))
    def links(items):
        result = []
        for r in items:
            all_refs[r['event_id']] = r
            result.append(f'<a href="#e{r["event_id"]}">E{r["event_id"]}</a>')
        return ' '.join(result) or 'No supporting citation available.'
    facts = ''.join(f'<li>{esc(t)} {links(rr)}</li>' for t, rr in observations)
    cards = ''.join(f'<article><p class="label">{esc(rank)}</p><h3>{esc(title)}</h3><p>{esc(support)} {links(rr)}</p><h4>Counterevidence and uncertainty</h4><p>{esc(uncertainty)} {links(counter) if counter else ""}</p><h4>Decisive next check</h4><p>{esc(check)}</p></article>' for rank,title,support,rr,counter,uncertainty,check in hypotheses)
    # Pin only displayed evidence, deduplicating byte-identical archive copies by hash+line.
    unique = {}
    for r in sorted(all_refs.values(), key=lambda r: (r.get('timestamp') or '~', r['path'], r['line'])):
        unique.setdefault((r['sha256'], r['line']), r)
    timeline = ''.join(f'<tr><td>{esc(r.get("timestamp") or "Unknown — not chronologically ordered")}</td><td>{esc(r["path"])}:{r["line"]}</td><td>{esc(r["excerpt"][:450])} {links([r])}</td></tr>' for r in list(unique.values())[:100])
    appendix = ''.join(f'<article id="e{r["event_id"]}"><h3>E{r["event_id"]} · {esc(r["path"])}:{r["line"]}</h3><p>SHA-256: {esc(r["sha256"])} · bytes {r["byte_start"]}–{r["byte_end"]}</p><pre>{esc(r["excerpt"])}</pre></article>' for r in all_refs.values())
    scope_html = ''.join(f'<li>{esc(s["path"])}: {s["read"]} lines read; {"limit reached" if s["truncated"] else "complete indexed file"}.</li>' for s in scope)
    gaps = run.coverage.get('gaps', [])
    body = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>{esc(case.title)} — Detailed preliminary investigation</title><style>
body{{font:16px/1.65 system-ui;color:#203b38;max-width:1120px;margin:40px auto;padding:24px}}h1{{font-size:34px}}h2{{border-top:1px solid #cadbd4;padding-top:24px;margin-top:32px}}article{{padding:20px;background:#f3f7f4;margin:16px 0;border-radius:10px}}.label{{color:#166b5c;font-weight:700}}pre,td,p,li,h3{{overflow-wrap:anywhere}}pre{{white-space:pre-wrap}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #ddd;vertical-align:top}}a{{color:#096858}}@media print{{body{{margin:0}}}}
</style></head><body><p class="label">PRELIMINARY · UNAPPROVED · EVIDENCE REVIEW</p><h1>{esc(case.title)} — Detailed preliminary investigation</h1>
<p>Case {esc(case.id)} · Run {run.id} · Evidence revision {run.revision} · Generated {datetime.now(timezone.utc).isoformat()}</p>
<h2>Where to start</h2><p>{'Investigate the cited HTTP 5xx request counters first; recover per-request traces to locate the failing hop.' if failed_codes else 'Review the supported observations and test the hypotheses below against the customer symptom.'} No incident root cause is confirmed by this preliminary report.</p>
<p>Components: {esc(', '.join(run.components))}. Investigation question: {esc(run.question or 'No specific symptom or investigation question supplied.')}</p>
<h2>Scope and evidence quality</h2><p>Generated by deterministic evidence-review-v1; investigation provider: {esc(run.provider)}. This is an automated preliminary review, not an analyst-authored or model-confirmed RCA. It uses this run’s pinned uploads and citations. Supplemental INFO-level review expands only product files reached by that run, up to 16 file IDs and 3,000 lines per unique file. It reviews their captured contents without an incident-time filter; timestamps and file identities must be compared before correlation. Duplicate file hashes are scanned once. No cross-file counter totals are inferred.</p><ul>{scope_html or '<li>No product file citations available to expand.</li>'}</ul><p>Product file IDs available: {len(product_ids)}. Counter samples displayed: {len(counters)} of {counter_count} parsed (up to 12 failed and 12 successful samples). Timeline shows at most 100 selected, deduplicated evidence records. Unknown timestamps remain unknown. This is not an exhaustive archive review.</p>
<h2>Observed facts</h2><ul>{facts or '<li>No supported observation retrieved.</li>'}</ul>
<h2>Assessment of requested symptoms</h2><table><tr><th>Symptom</th><th>Assessment and next check</th></tr>
<tr><td>HTTP errors</td><td>{'Aggregate 5xx failures are cited above. Exact requests and cause require traces.' if failed_codes else 'No parsed HTTP 5xx counter signal in this bounded review. Inspect request logs; this does not rule out HTTP errors.'}</td></tr>
<tr><td>Missing metrics</td><td>Data loss is not established. Compare source, application, receiver and stored record IDs; determine retry/replay outcomes.</td></tr>
<tr><td>Delayed enrichment</td><td>End-to-end delay is not established. Compare source/send/arrival/completion timestamps and queue depth for matching records.</td></tr>
<tr><td>Pod restarts</td><td>Review captured restart state {links(restarts)}. Pod replacement and a container restart are different events. Obtain prior termination state, events and rollout history.</td></tr></table>
<h2>Ranked hypotheses and probable causes to test</h2>{cards}
<h2>Evidence timeline</h2><table><tr><th>Recorded time</th><th>Source</th><th>Selected observation</th></tr>{timeline}</table>
<h2>Investigation path</h2><ul>{''.join('<li>'+esc(s['component']+' · '+s['stage']+' · '+s['outcome']+': '+s['detail'])+'</li>' for s in run.stages)}</ul>
<h2>Missing evidence and next checks</h2><ul>{''.join('<li>'+esc(g)+'</li>' for g in gaps) or '<li>No intake gap recorded; causal confirmation still requires evidence.</li>'}<li>Confirm the incident time, timezone, affected stream and measured customer impact.</li><li>Correlate exact failed requests across verified dependencies; compare successful requests as counterevidence.</li><li>Record each hypothesis as confirmed, rejected or unresolved, with supporting and contradictory citations.</li></ul><pre>{esc(json.dumps(run.coverage, indent=2))}</pre>
<h2>Limits and provenance</h2><p>No final RCA or case approval is performed. A recorded error is not automatically an initiating cause; absence of retrieved errors does not establish health. Historical reports remain tied to their original run. Approved findings remain a separate record.</p><p>Run digest: {esc(run.digest)} · Template: preliminary-v2</p>
<h2>Evidence appendix</h2>{appendix}</body></html>'''.encode()
    meta = dict(case_id=run.case_id, run_id=run.id, revision=run.revision, run_digest=run.digest,
                sha256=hashlib.sha256(body).hexdigest(), source='Automated evidence review', template='preliminary-v2', approved=False)
    dest = artifact_path('preliminary-reports', run.id)
    dest.with_suffix('.tmp').write_bytes(body)
    dest.with_suffix('.tmp').replace(dest)
    manifest = artifact_path('preliminary-manifests', run.id)
    manifest.with_suffix('.tmp').write_text(json.dumps(meta))
    manifest.with_suffix('.tmp').replace(manifest)
    audit(db, actor, run.case_id, 'preliminary_report_generated', meta)
    return meta
