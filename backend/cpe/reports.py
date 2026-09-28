import html
import json
from datetime import datetime, timezone


def render_report(case, run, reviewer):
    esc = lambda value: html.escape(str(value))
    blocks = []
    for finding in run.findings:
        refs = "".join(f'<li><strong>{esc(r["path"])}:{r["line"]}</strong><pre>{esc(r["excerpt"])}</pre><small>SHA-256 {esc(r["sha256"])} · bytes {r["byte_start"]}–{r["byte_end"]}</small></li>' for r in finding["evidence"])
        blocks.append(f'<section><p class="label">{esc(finding["classification"])}</p><h2>{esc(finding["title"])}</h2><p>{esc(finding["explanation"])}</p><ul>{refs}</ul><p>Next checks: {esc(" ".join(finding["next_checks"]))}</p></section>')
    stages = "".join(f'<tr><td>{esc(s["component"])}</td><td>{esc(s["stage"])}</td><td>{esc(s["outcome"])}</td><td>{esc(s["detail"])}</td></tr>' for s in run.stages)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>{esc(case.title)} — CPE case report</title><style>
body{{font:16px/1.65 system-ui,sans-serif;color:#172d35;background:#fff;max-width:1050px;margin:40px auto;padding:24px}}h1{{font-size:36px}}h2{{font-size:23px}}.label{{color:#087c6e;text-transform:uppercase;letter-spacing:.12em;font-size:12px}}section{{border-top:1px solid #cdd9da;padding-top:20px;margin-top:30px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f6f5;padding:15px}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{text-align:left;border-bottom:1px solid #ddd;padding:10px}}small{{overflow-wrap:anywhere}}@media print{{body{{margin:0;padding:0}}section{{break-inside:avoid}}}}
</style></head><body><p class="label">CPE / Approved investigation record</p><h1>{esc(case.title)}</h1>
<p>{esc(case.customer)} · Case {esc(case.id)} · Evidence revision {run.revision}</p>
<p><strong>Offline captured evidence. Provider: {esc(run.provider)}. Approval does not convert a hypothesis into a confirmed cause.</strong></p>
<section><h2>Executive summary</h2><p>{esc(run.summary)}</p></section>
<section><h2>Investigation path</h2><table><thead><tr><th>Component</th><th>Stage</th><th>Outcome</th><th>Detail</th></tr></thead><tbody>{stages}</tbody></table></section>
{"".join(blocks)}<section><h2>Coverage and unresolved questions</h2><pre>{esc(json.dumps(run.coverage, indent=2))}</pre></section>
<section><h2>Approval and provenance</h2><p>Reviewer: {esc(reviewer)} · Approved: {esc(datetime.fromtimestamp(run.approved_at, timezone.utc).isoformat())}</p><p>Approved payload digest: {esc(run.digest)}</p><p>Run: {esc(run.id)} · Template: report-v1</p></section></body></html>'''
