import React, { useState } from "react";
import { post } from "./api";

export function FindingsEditor({ run, perform, refresh }: any) {
  const [open, setOpen] = useState(false),
    [summary, setSummary] = useState(run.summary),
    [findings, setFindings] = useState(JSON.stringify(run.findings, null, 2)),
    [note, setNote] = useState("");
  return (
    <div className="review-editor">
      <button className="secondary" onClick={() => setOpen(!open)}>
        {open ? "Close revision editor" : "Revise findings before approval"}
      </button>
      {open && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            perform(async () => {
              await post(`/runs/${run.id}/revisions`, {
                digest: run.digest,
                summary,
                findings: JSON.parse(findings),
                review_note: note,
              });
              setOpen(false);
              await refresh();
            });
          }}
        >
          <p>
            Create an immutable revision. Prior approvals stay attached to their
            original payload; this revision requires its own approval.
          </p>
          <label>
            Executive summary
            <textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
            />
          </label>
          <label>
            Findings and source references (JSON)
            <textarea
              className="config-editor"
              value={findings}
              onChange={(e) => setFindings(e.target.value)}
            />
          </label>
          <label>
            Reason for revision
            <input
              required
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <button className="primary">Save new findings revision</button>
        </form>
      )}
    </div>
  );
}

export function UserAdministration({ perform }: any) {
  const [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [role, setRole] = useState("investigator"),
    [saved, setSaved] = useState("");
  return (
    <form
      className="panel config-panel"
      onSubmit={(e) => {
        e.preventDefault();
        perform(async () => {
          await post("/admin/users", { email, password, role });
          setSaved(
            `Created ${email} as ${role}. Share cases explicitly to grant access.`,
          );
          setPassword("");
        });
      }}
    >
      <h2>User administration</h2>
      <p>
        New users do not automatically have access to other engineers’ cases.
      </p>
      <div className="form-row">
        <label>
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Role
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option>investigator</option>
            <option>reviewer</option>
            <option>viewer</option>
            <option>admin</option>
          </select>
        </label>
      </div>
      <label>
        Initial password (12+ characters)
        <input
          type="password"
          minLength={12}
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <button className="secondary">Create user</button>
      {saved && <p role="status">{saved}</p>}
    </form>
  );
}
