import React, { useState, useEffect } from "react";
import {
  Activity,
  ArrowRight,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  FileText,
  FolderOpen,
  GitBranch,
  Search,
  ShieldCheck,
  UploadCloud,
  Download,
  AlertTriangle,
  Send,
} from "lucide-react";
import { parse as parseYaml } from "yaml";
import { api, post, upload } from "./api";
import { Badge, Empty } from "./ui";
import { roles, defaultConfig } from "./defaults";
type Any = Record<string, any>;
export function IntakePanel({ data, refresh, perform, setTab }: any) {
  const [config, setConfig] = useState(
      JSON.stringify(
        Object.keys(data.case.config).length ? data.case.config : defaultConfig,
        null,
        2,
      ),
    ),
    [selected, setSelected] = useState<string[]>(data.case.components),
    [progress, setProgress] = useState<Any>({}),
    [partial, setPartial] = useState(false);
  let names: string[] = [];
  try {
    names = JSON.parse(config).components.map((c: Any) => c.id);
  } catch {}
  return (
    <>
      <div className="section-title">
        <div>
          <p className="eyebrow">CASE SETUP</p>
          <h2>Build your evidence set</h2>
          <p>Upload once. Keep the source. Follow every finding back.</p>
        </div>
        <Badge>{data.case.readiness.ready ? "Ready" : "Draft intake"}</Badge>
      </div>
      <div className="upload-grid">
        {roles.map(([role, title, help], i) => (
          <div className="upload-card" key={role}>
            <div className="upload-card-heading">
              <span className="step-number">{i + 1}</span>
              <h3>{title}</h3>
              {data.case.readiness.roles.includes(role) && (
                <CheckCircle2 className="green" size={19} />
              )}
            </div>
            <p>{help}</p>
            <label className="dropzone">
              <UploadCloud size={23} />
              <strong>{progress[role] || "Choose files to upload"}</strong>
              <span>Or select the same file to resume</span>
              <input
                type="file"
                multiple
                aria-label={title}
                accept=".tar,.tar.gz,.tgz,.zip,.log,.txt,.json,.yaml,.yml"
                onChange={(e) => {
                  const files = Array.from(e.target.files || []);
                  perform(async () => {
                    for (const f of files) {
                      await upload(data.case.id, f, [role], (p) =>
                        setProgress((v: Any) => ({
                          ...v,
                          [role]: `${f.name} · ${p}%`,
                        })),
                      );
                    }
                    setProgress((v: Any) => ({
                      ...v,
                      [role]: "Uploaded · processing",
                    }));
                    await refresh();
                  });
                }}
              />
            </label>
            {data.uploads
              .filter((u: Any) => u.roles.includes(role) && !u.deleted)
              .map((u: Any) => (
                <div className="upload-item" key={u.id}>
                  <span>{u.name}</span>
                  <Badge>{u.status}</Badge>
                </div>
              ))}
          </div>
        ))}
      </div>
      <div className="panel config-panel">
        <div className="section-title">
          <div>
            <h3>6 · Affected components & investigation config</h3>
            <p>
              Import your actual component mapping: namespace, affected pod
              names, container names, log patterns and NFS archive paths. Sample
              mappings do not identify your deployment.
            </p>
          </div>
          <label className="secondary file-button">
            <UploadCloud size={15} /> Import config
            <input
              type="file"
              accept=".json,.yaml,.yml"
              aria-label="Import config"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f)
                  perform(async () => {
                    setConfig(
                      JSON.stringify(parseYaml(await f.text()), null, 2),
                    );
                  });
              }}
            />
          </label>
        </div>
        <textarea
          aria-label="Investigation configuration"
          className="config-editor"
          value={config}
          onChange={(e) => setConfig(e.target.value)}
        />
        <div className="component-chips">
          {names.map((n) => (
            <label key={n}>
              <input
                type="checkbox"
                checked={selected.includes(n)}
                onChange={(e) =>
                  setSelected(
                    e.target.checked
                      ? [...selected, n]
                      : selected.filter((x) => x !== n),
                  )
                }
              />
              {n}
            </label>
          ))}
        </div>
        <button
          className="secondary"
          onClick={() =>
            perform(async () => {
              await api(`/cases/${data.case.id}/intake`, {
                method: "PUT",
                body: JSON.stringify({
                  revision: data.case.revision,
                  config: JSON.parse(config),
                  components: selected,
                }),
              });
              await refresh();
            })
          }
        >
          <Check size={16} /> Save configuration & selection
        </button>
      </div>
      <div className="panel review-panel">
        <h3>Review & investigate</h3>
        <p>
          Kubernetes checks → NFS log discovery → Product failures → Related
          components
        </p>
        {data.case.readiness.issues.map((g: string) => (
          <p key={g} className="gap">
            <AlertTriangle size={14} />
            {g}
          </p>
        ))}
        <label className="checkbox">
          <input
            type="checkbox"
            checked={partial}
            onChange={(e) => setPartial(e.target.checked)}
          />{" "}
          Explicitly continue with available evidence (gaps remain unknown)
        </label>
        <button
          className="primary"
          disabled={!data.case.readiness.ready && !partial}
          onClick={() =>
            perform(async () => {
              await post(`/cases/${data.case.id}/investigations`, { partial });
              await refresh();
              setTab("Investigation");
            })
          }
        >
          <Activity size={16} /> Create investigation
        </button>
      </div>
    </>
  );
}

export function FilesPanel({ caseId, files, perform, showEvidence }: any) {
  const [q, setQ] = useState(""),
    [file, setFile] = useState(""),
    [severity, setSeverity] = useState(""),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [format, setFormat] = useState("csv"),
    [results, setResults] = useState<Any[]>([]),
    [next, setNext] = useState<number | null>(null);
  const search = (after = 0) =>
    perform(async () => {
      const r = await api(
        `/cases/${caseId}/search?` +
          new URLSearchParams({
            q,
            file_id: file,
            severity,
            start: start
              ? new Date(start).toISOString().replace("Z", "+00:00")
              : "",
            end: end ? new Date(end).toISOString().replace("Z", "+00:00") : "",
            after: String(after),
          }),
      );
      setResults(after ? [...results, ...r.items] : r.items);
      setNext(r.next);
    });
  useEffect(() => {
    search();
  }, []);
  return (
    <>
      <h2>Log & file explorer</h2>
      <p>
        Search indexed evidence. Open any result to inspect surrounding source
        lines.
      </p>
      <div className="filter-bar">
        <input
          placeholder="Search errors, IDs, or messages…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
        />
        <select
          aria-label="File filter"
          value={file}
          onChange={(e) => setFile(e.target.value)}
        >
          <option value="">All files</option>
          {files.map((f: Any) => (
            <option key={f.id} value={f.id}>
              {f.path}
            </option>
          ))}
        </select>
        <select
          aria-label="Severity filter"
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
        >
          <option value="">All levels</option>
          <option>ERROR</option>
          <option>WARN</option>
          <option>INFO</option>
        </select>
        <button className="primary" onClick={() => search()}>
          <Search size={16} /> Search
        </button>
      </div>
      <div className="form-row">
        <label>
          From (your local time)
          <input
            type="datetime-local"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <label>
          To (your local time)
          <input
            type="datetime-local"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </label>
      </div>
      <div className="section-title">
        <span>{results.length} loaded results</span>
        <select
          aria-label="Export format"
          style={{ width: "100px" }}
          value={format}
          onChange={(e) => setFormat(e.target.value)}
        >
          <option value="csv">CSV</option>
          <option value="jsonl">JSONL</option>
          <option value="txt">Text</option>
        </select>
        <a
          className="secondary"
          href={
            `/api/cases/${caseId}/export?` +
            new URLSearchParams({
              q,
              severity,
              file_id: file,
              format,
              start: start
                ? new Date(start).toISOString().replace("Z", "+00:00")
                : "",
              end: end
                ? new Date(end).toISOString().replace("Z", "+00:00")
                : "",
            })
          }
        >
          <Download size={15} /> Export results
        </a>
      </div>
      <div className="panel events">
        {results.map((r) => (
          <button
            className="event"
            key={r.event_id}
            onClick={() => showEvidence(r)}
          >
            <Badge>{r.severity}</Badge>
            <div>
              <code>{r.excerpt}</code>
              <small>
                {r.path}:{r.line} · {r.timestamp || "Unknown time"}
              </small>
            </div>
          </button>
        ))}
        {!results.length && (
          <Empty
            title="No matching entries"
            detail="Try a different query or wait for indexing to finish."
          />
        )}
      </div>
      {next && (
        <button className="secondary" onClick={() => search(next)}>
          Load more
        </button>
      )}
    </>
  );
}
export function ChatPanel({
  caseId,
  messages,
  refresh,
  perform,
  provider,
}: any) {
  const [text, setText] = useState(""),
    [intent, setIntent] = useState("explain");
  return (
    <aside className="chat-panel">
      <div className="chat-heading">
        <span className="bot-icon">
          <Bot size={20} />
        </span>
        <div>
          <strong>Investigation assistant</strong>
          <small>Grounded in this case's evidence</small>
        </div>
      </div>
      <div className="chat-scope">
        <ShieldCheck size={13} /> CASE-SCOPED · {String(provider).toUpperCase()}{" "}
        PROVIDER
      </div>
      <div className="messages">
        {messages.length ? (
          messages.map((m: Any) => (
            <div className={"message " + m.role} key={m.id}>
              <small>{m.role === "user" ? "You" : "CPE assistant"}</small>
              <p>{m.text}</p>
            </div>
          ))
        ) : (
          <div className="chat-empty">
            <GitBranch size={30} />
            <h3>Follow a failure together</h3>
            <p>
              I’ll start with Kubernetes, locate the product logs, and follow
              related services.
            </p>
            {[
              "Why is this pod restarting?",
              "Explain the latest findings",
              "What evidence is missing?",
            ].map((s) => (
              <button key={s} onClick={() => setText(s)}>
                {s}
                <ArrowRight size={14} />
              </button>
            ))}
          </div>
        )}
      </div>
      <form
        className="chat-compose"
        onSubmit={(e) => {
          e.preventDefault();
          perform(async () => {
            await post(`/cases/${caseId}/chat`, { question: text, intent });
            setText("");
            await refresh();
          });
        }}
      >
        <select
          aria-label="Chat mode"
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
        >
          <option value="explain">Explain existing evidence</option>
          <option value="investigate">Run staged investigation</option>
        </select>
        <textarea
          aria-label="Ask the assistant"
          placeholder="Ask about this case…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          required
        />
        <div>
          <small>Check supporting evidence before approval.</small>
          <button
            className="primary"
            aria-label="Send message"
            disabled={!text.trim()}
          >
            <Send size={16} />
          </button>
        </div>
      </form>
    </aside>
  );
}
export function AuditPanel({ caseId }: any) {
  const [rows, setRows] = useState<Any[]>([]);
  useEffect(() => {
    api(`/cases/${caseId}/audit`).then(setRows);
  }, [caseId]);
  return (
    <div className="panel">
      <table>
        <thead>
          <tr>
            <th>ACTION</th>
            <th>TIME</th>
            <th>DETAIL</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.action}</td>
              <td>{new Date(r.created * 1000).toLocaleString()}</td>
              <td>
                <code>{JSON.stringify(r.detail)}</code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function KnowledgeEditor({ perform, reload }: any) {
  const [name, setName] = useState(""),
    [version, setVersion] = useState("1"),
    [content, setContent] = useState('{"purpose":"","dependencies":[]}');
  return (
    <form
      className="panel config-panel"
      onSubmit={(e) => {
        e.preventDefault();
        perform(async () => {
          await post("/knowledge", {
            name,
            version,
            content: JSON.parse(content),
          });
          setName("");
          await reload();
        });
      }}
    >
      <div className="form-row">
        <label>
          Component name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </label>
        <label>
          Version
          <input
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            required
          />
        </label>
      </div>
      <label>
        Documentation JSON
        <textarea
          className="config-editor"
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
      </label>
      <button className="secondary">Save immutable revision</button>
    </form>
  );
}
