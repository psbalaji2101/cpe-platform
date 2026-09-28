import React, { useEffect, useState } from "react";
import { api, post } from "./api";
import { Badge, Empty } from "./ui";

export function TimelinePanel({ caseId, perform, showEvidence }: any) {
  const [data, setData] = useState<any>({ items: [] });
  const load = (cursor = "") =>
    perform(async () => {
      const r = await api(
        `/cases/${caseId}/timeline?` + new URLSearchParams({ cursor }),
      );
      setData({ ...r, items: cursor ? [...data.items, ...r.items] : r.items });
    });
  useEffect(() => {
    load();
  }, [caseId]);
  return (
    <>
      <h2>Cross-file timeline</h2>
      <p>{data.ordering}</p>
      <div className="notice">
        {data.unknown_timestamp_records || 0} records have unknown timestamps
        and remain available in the file explorer.
      </div>
      <div className="panel events">
        {data.items.map((r: any) => (
          <button
            className="event"
            key={r.event_id}
            onClick={() => showEvidence(r)}
          >
            <Badge>{r.severity}</Badge>
            <div>
              <small>
                {r.timestamp} · {r.path}:{r.line}
              </small>
              <code>{r.excerpt}</code>
            </div>
          </button>
        ))}
        {!data.items.length && (
          <Empty
            title="No timestamped evidence"
            detail="Timestamp-unknown entries are not placed in a fabricated sequence."
          />
        )}
      </div>
      {data.next && (
        <button className="secondary" onClick={() => load(data.next)}>
          Load next events
        </button>
      )}
    </>
  );
}

export function ArchiveComparison({ caseId, uploads, perform }: any) {
  const choices = uploads.filter(
    (u: any) => u.status === "Ready" && !u.deleted,
  );
  const [left, setLeft] = useState(""),
    [right, setRight] = useState(""),
    [result, setResult] = useState<any>(null);
  return (
    <div className="panel config-panel">
      <h3>Compare archive versions</h3>
      <p>
        Compare the same relative paths by source hash. This does not assume one
        archive supersedes another.
      </p>
      <div className="form-row">
        {[
          ["Earlier archive", left, setLeft],
          ["Later archive", right, setRight],
        ].map(([label, value, set]: any) => (
          <label key={label}>
            {label}
            <select value={value} onChange={(e) => set(e.target.value)}>
              <option value="">Select an archive</option>
              {choices.map((u: any) => (
                <option key={u.id} value={u.id}>
                  {u.name} · {new Date(u.created * 1000).toLocaleString()}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <button
        className="secondary"
        disabled={!left || !right || left === right}
        onClick={() =>
          perform(async () =>
            setResult(
              await api(
                `/cases/${caseId}/compare?` +
                  new URLSearchParams({ left, right }),
              ),
            ),
          )
        }
      >
        Compare versions
      </button>
      {result && (
        <>
          <p>
            {result.unchanged} unchanged · {result.added.length} added ·{" "}
            {result.removed.length} removed · {result.changed.length} changed
          </p>
          <ul>
            {result.added.map((p: string) => (
              <li key={"a" + p}>Added: {p}</li>
            ))}
            {result.removed.map((p: string) => (
              <li key={"r" + p}>Removed: {p}</li>
            ))}
            {result.changed.map((p: any) => (
              <li key={p.path}>Changed: {p.path}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export function JobControls({ jobs, perform, refresh }: any) {
  return (
    <div className="panel config-panel">
      <h3>Processing jobs</h3>
      {jobs.map((j: any) => (
        <div className="archive" key={j.id}>
          <div>
            <strong>{j.kind}</strong>
            <small>{j.progress}</small>
            {j.error && <p>{j.error}</p>}
          </div>
          <Badge>{j.status}</Badge>
          {["Queued", "Running", "Failed"].includes(j.status) && (
            <button
              className="secondary"
              onClick={() =>
                perform(async () => {
                  await post(
                    `/jobs/${j.id}/${j.status === "Failed" ? "retry" : "cancel"}`,
                  );
                  await refresh();
                })
              }
            >
              {j.status === "Failed" ? "Retry" : "Cancel"}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
