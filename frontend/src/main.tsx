import React, { useState, useEffect, useCallback } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  FileText,
  FolderOpen,
  GitBranch,
  Layers,
  LayoutDashboard,
  LogOut,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  UploadCloud,
  X,
  Download,
  AlertTriangle,
  Clock,
  Send,
  Trash2,
  BookOpen,
} from "lucide-react";
import { parse as parseYaml } from "yaml";
import { api, post, setCsrf, upload } from "./api";
import "./styles.css";
import { ProductInventory, ContainerInventory } from "./inventory";
import { StorageEvidenceHelp } from "./storage-evidence";
import { Badge, Empty } from "./ui";
import { FindingsEditor, UserAdministration } from "./review";
import { TimelinePanel, ArchiveComparison, JobControls } from "./history";
import {
  IntakePanel,
  FilesPanel,
  ChatPanel,
  AuditPanel,
  KnowledgeEditor,
} from "./panels";

type Any = Record<string, any>;
function App() {
  const [user, setUser] = useState<Any | null>(null),
    [loading, setLoading] = useState(true),
    [view, setView] = useState("cases"),
    [cases, setCases] = useState<Any[]>([]),
    [caseId, setCaseId] = useState(""),
    [data, setData] = useState<Any | null>(null),
    [tab, setTab] = useState("Overview"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [create, setCreate] = useState(false),
    [newCase, setNewCase] = useState({
      title: "",
      customer: "",
      description: "",
      severity: "Medium",
    }),
    [query, setQuery] = useState(""),
    [login, setLogin] = useState({ email: "admin@cpe.local", password: "" }),
    [settings, setSettings] = useState<Any | null>(null),
    [knowledge, setKnowledge] = useState<Any[]>([]),
    [evidence, setEvidence] = useState<Any | null>(null);
  const perform = async (fn: () => Promise<void>) => {
    setError("");
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const refresh = useCallback(async () => {
    if (!caseId) return;
    const [c, d, u, f, r, j, m] = await Promise.all([
      api(`/cases/${caseId}`),
      api(`/cases/${caseId}/dashboard`),
      api(`/cases/${caseId}/uploads`),
      api(`/cases/${caseId}/files`),
      api(`/cases/${caseId}/runs`),
      api(`/cases/${caseId}/jobs`),
      api(`/cases/${caseId}/messages`),
    ]);
    setData({
      case: c,
      dashboard: d,
      uploads: u,
      files: f,
      runs: r,
      jobs: j,
      messages: m,
    });
  }, [caseId]);
  useEffect(() => {
    api("/auth/me")
      .then((r) => {
        setUser(r.user);
        setCsrf(r.csrf);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    if (user) {
      api("/cases")
        .then(setCases)
        .catch((e) => setError(e.message));
      api("/settings")
        .then(setSettings)
        .catch((e) => setError(e.message));
      api("/knowledge")
        .then(setKnowledge)
        .catch((e) => setError(e.message));
    }
  }, [user, view, caseId]);
  useEffect(() => {
    setData(null);
    if (caseId) {
      refresh().catch((e) => setError(e.message));
      const timer = setInterval(
        () => refresh().catch((e) => setError(e.message)),
        3000,
      );
      return () => clearInterval(timer);
    }
  }, [caseId, refresh]);
  const openCase = (id: string) => {
    setCaseId(id);
    setView("workspace");
    setTab("Overview");
  };
  const showEvidence = (r: Any) =>
    perform(async () => {
      setEvidence(
        await api(
          `/files/${r.file_id}/content?line=${Math.max(1, r.line - 3)}&limit=15`,
        ),
      );
    });
  if (loading) return <div className="loading">Opening your workspace…</div>;
  if (!user)
    return (
      <div className="login-page">
        <div className="login-story">
          <div className="wordmark">
            <Layers /> CPE <span>INTELLIGENCE</span>
          </div>
          <p className="eyebrow">FROM SYMPTOM TO SOURCE</p>
          <h1>
            Every answer.
            <br />
            Backed by evidence.
          </h1>
          <p>
            A focused workspace for complex investigations.
            <br />
            Follow the signal, connect dependencies, and bring
            <br />
            your team to a conclusion they can trust.
          </p>
          <div className="login-path">
            <span>Kubernetes</span>
            <ChevronRight />
            <span>Product logs</span>
            <ChevronRight />
            <span>Root cause</span>
          </div>
          <small>ON-PREMISES · CASE-SCOPED · AUDITABLE</small>
        </div>
        <form
          className="login-form"
          onSubmit={(e) => {
            e.preventDefault();
            perform(async () => {
              const r = await post("/auth/login", login);
              setCsrf(r.csrf);
              setUser(r.user);
            });
          }}
        >
          <div className="eyebrow">YOUR INVESTIGATION WORKSPACE</div>
          <h2>Welcome back</h2>
          <p>Sign in to create a case or continue an investigation.</p>
          <label>
            Email address
            <input
              autoComplete="username"
              type="email"
              value={login.email}
              onChange={(e) => setLogin({ ...login, email: e.target.value })}
              required
            />
          </label>
          <label>
            Password
            <input
              autoComplete="current-password"
              type="password"
              value={login.password}
              onChange={(e) => setLogin({ ...login, password: e.target.value })}
              required
            />
          </label>
          {error && (
            <div role="alert" className="error">
              {error}
            </div>
          )}
          <button className="primary" disabled={busy}>
            Sign in <ArrowRight size={17} />
          </button>
          <small>
            <ShieldCheck size={15} /> Your logs stay inside the approved
            environment.
          </small>
        </form>
      </div>
    );
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="wordmark">
          <Layers /> CPE <span>INTELLIGENCE</span>
        </div>
        <p className="nav-label">WORKSPACE</p>
        {[
          ["cases", "Cases", FolderOpen],
          ["knowledge", "Knowledge", BookOpen],
          ["settings", "Settings", Settings],
        ].map(([id, label, Icon]: any) => (
          <button
            key={id}
            className={
              view === id || (id === "cases" && view === "workspace")
                ? "nav active"
                : "nav"
            }
            onClick={() => {
              setView(id);
              setCaseId("");
            }}
          >
            <Icon size={19} />
            {label}
          </button>
        ))}
        <div className="side-bottom">
          <div className="deployment">
            <span className="dot" /> Private deployment
            <small>
              {settings?.llm.provider === "mock" ? "Mock LLM" : "Company LLM"} ·
              evidence mode
            </small>
          </div>
          <div className="user">
            <div className="avatar">{user.email[0].toUpperCase()}</div>
            <div>
              <strong>{user.email}</strong>
              <small>{user.role}</small>
            </div>
            <button
              className="icon"
              aria-label="Sign out"
              onClick={() =>
                perform(async () => {
                  await post("/auth/logout");
                  setUser(null);
                  setData(null);
                  setCaseId("");
                })
              }
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>
            Support engineering <ChevronRight size={14} />{" "}
            {view === "workspace"
              ? "Case workspace"
              : view[0].toUpperCase() + view.slice(1)}
          </span>
          <div>
            <span className="env-tag">ON-PREMISES</span>
            <CircleHelp size={18} />
          </div>
        </header>
        {error && (
          <div role="alert" className="error global">
            {error}
            <button className="icon" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {view === "cases" && (
          <div className="page">
            <div className="page-title">
              <div>
                <p className="eyebrow">SUPPORT OPERATIONS</p>
                <h1>Your investigations</h1>
                <p>One place for the evidence. A clear path to the cause.</p>
              </div>
              <button className="primary" onClick={() => setCreate(true)}>
                <Plus size={18} /> Create new case
              </button>
            </div>
            <div className="launch-grid">
              <button
                className="launch-card create"
                onClick={() => setCreate(true)}
              >
                <span className="card-icon">
                  <Plus />
                </span>
                <h2>Start with a new case</h2>
                <p>
                  Bring your logs, cluster snapshot, and component mappings.
                  We’ll follow the evidence from there.
                </p>
                <span className="link">
                  Create new case <ArrowRight size={17} />
                </span>
              </button>
              <button
                className="launch-card"
                onClick={() => document.getElementById("case-search")?.focus()}
              >
                <span className="card-icon muted">
                  <FolderOpen />
                </span>
                <h2>Pick up where you left off</h2>
                <p>
                  Open an existing case, add new evidence, or review findings
                  with your team.
                </p>
                <span className="link">
                  Open existing case <ArrowRight size={17} />
                </span>
              </button>
            </div>
            <div className="section-title">
              <h2>
                Recent cases <span className="count">{cases.length}</span>
              </h2>
              <div className="search">
                <Search size={17} />
                <input
                  id="case-search"
                  placeholder="Search cases or customers…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
            </div>
            <div className="panel">
              {cases.length ? (
                <table>
                  <thead>
                    <tr>
                      <th>CASE</th>
                      <th>CUSTOMER</th>
                      <th>PRIORITY</th>
                      <th>STATUS</th>
                      <th>CREATED</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {cases
                      .filter((c) =>
                        (c.title + c.customer)
                          .toLowerCase()
                          .includes(query.toLowerCase()),
                      )
                      .map((c) => (
                        <tr
                          key={c.id}
                          onClick={() => openCase(c.id)}
                          tabIndex={0}
                          onKeyDown={(e) => e.key === "Enter" && openCase(c.id)}
                        >
                          <td>
                            <strong>{c.title}</strong>
                            <small>CASE-{c.id.slice(0, 8).toUpperCase()}</small>
                          </td>
                          <td>{c.customer}</td>
                          <td>
                            <span
                              className={"priority " + c.severity.toLowerCase()}
                            >
                              {c.severity}
                            </span>
                          </td>
                          <td>
                            <Badge>{c.status}</Badge>
                          </td>
                          <td>
                            {new Date(c.created * 1000).toLocaleDateString()}
                          </td>
                          <td>
                            <ChevronRight size={17} />
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              ) : (
                <Empty
                  title="Your first investigation starts here"
                  detail="Create a case and upload evidence. No sample customer data is added automatically."
                />
              )}
            </div>
            <div className="footnote">
              <ShieldCheck size={16} /> Case evidence is isolated. Findings link
              back to their original source.
            </div>
          </div>
        )}
        {view === "workspace" &&
          (!data ? (
            <div className="loading">Loading case evidence…</div>
          ) : (
            <div className="workspace">
              <div className="case-heading">
                <button
                  className="icon"
                  aria-label="Back to cases"
                  onClick={() => {
                    setCaseId("");
                    setView("cases");
                  }}
                >
                  <ArrowLeft size={19} />
                </button>
                <div>
                  <p className="eyebrow">
                    {data.case.customer} / CASE-{caseId.slice(0, 8)}
                  </p>
                  <h1>{data.case.title}</h1>
                </div>
                <Badge>{data.case.status}</Badge>
                <span className="revision">
                  Evidence revision {data.case.revision}
                </span>
              </div>
              <nav className="tabs">
                {[
                  "Overview",
                  "Intake",
                  "Files",
                  "Timeline",
                  "Investigation",
                  "Archives",
                  "Audit",
                  "Jobs",
                ].map((t) => (
                  <button
                    key={t}
                    className={tab === t ? "selected" : ""}
                    onClick={() => setTab(t)}
                  >
                    {t}
                  </button>
                ))}
              </nav>
              <div className="workspace-columns">
                <div className="workspace-main">
                  {tab === "Overview" && (
                    <>
                      <div className="snapshot-banner">
                        <Clock size={17} />
                        <div>
                          <strong>Captured deployment health</strong>
                          <small>
                            {data.dashboard.capture_times.join(", ") ||
                              "Capture time not established"}{" "}
                            · This is not a live cluster connection
                          </small>
                        </div>
                      </div>
                      <div className="metrics">
                        {[
                          ["Observed pods", data.dashboard.total],
                          ["Healthy", data.dashboard.counts.Healthy || 0],
                          [
                            "Failed / degraded",
                            (data.dashboard.counts.Failed || 0) +
                              (data.dashboard.counts.Degraded || 0),
                          ],
                          ["Evidence files", data.dashboard.file_count],
                        ].map(([l, n]) => (
                          <div className="metric" key={l}>
                            <span>{l}</span>
                            <strong>{n}</strong>
                            <small>
                              {l === "Evidence files"
                                ? "Versioned sources"
                                : "Uploaded snapshots"}
                            </small>
                          </div>
                        ))}
                      </div>
                      <ProductInventory
                        products={data.dashboard.products || []}
                      />
                      {!data.case.readiness.ready && (
                        <div className="notice">
                          <AlertTriangle size={19} />
                          <div>
                            <strong>Evidence intake needs attention</strong>
                            <p>{data.case.readiness.issues.join(" · ")}</p>
                            <button
                              className="text-button"
                              onClick={() => setTab("Intake")}
                            >
                              Complete intake <ArrowRight size={14} />
                            </button>
                          </div>
                        </div>
                      )}
                      <div className="section-title">
                        <h2>Pods & containers</h2>
                        <span className="subtle">
                          Observed status, not inferred availability
                        </span>
                      </div>
                      <div className="panel">
                        {data.dashboard.pods.length ? (
                          <table>
                            <thead>
                              <tr>
                                <th>POD</th>
                                <th>STATUS</th>
                                <th>CONTAINERS / IMAGES</th>
                              </tr>
                            </thead>
                            <tbody>
                              {data.dashboard.pods.map((p: Any) => (
                                <tr key={p.uid}>
                                  <td>
                                    <strong>{p.name}</strong>
                                    <small>{p.namespace}</small>
                                  </td>
                                  <td>
                                    <Badge>{p.state}</Badge>
                                    <small>{p.reasons.join(", ")}</small>
                                  </td>
                                  <td>
                                    <ContainerInventory
                                      containers={p.containers || []}
                                    />
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : (
                          <Empty
                            title="No pod snapshot yet"
                            detail="Upload structured pod status to establish captured health. Missing status stays unknown."
                          />
                        )}
                      </div>
                      <div className="section-title">
                        <h2>Recent errors & warnings</h2>
                        <span className="subtle">
                          Latest 25 captured entries
                        </span>
                      </div>
                      <div className="panel events">
                        {data.dashboard.recent.length ? (
                          data.dashboard.recent.map((r: Any) => (
                            <button
                              className="event"
                              key={r.event_id}
                              onClick={() => showEvidence(r)}
                            >
                              <Badge>{r.severity}</Badge>
                              <div>
                                <code>{r.excerpt}</code>
                                <small>
                                  {r.path}:{r.line} ·{" "}
                                  {r.timestamp || "Timestamp unknown"}
                                </small>
                              </div>
                              <ChevronRight size={15} />
                            </button>
                          ))
                        ) : (
                          <Empty
                            title="No indexed errors yet"
                            detail="No matching entries does not establish that the deployment is healthy."
                          />
                        )}
                      </div>
                    </>
                  )}
                  {tab === "Intake" && (
                    <IntakePanel
                      data={data}
                      refresh={refresh}
                      perform={perform}
                      setTab={setTab}
                    />
                  )}
                  {tab === "Files" && (
                    <FilesPanel
                      caseId={caseId}
                      files={data.files}
                      perform={perform}
                      showEvidence={showEvidence}
                    />
                  )}
                  {tab === "Investigation" && (
                    <>
                      <div className="section-title">
                        <div>
                          <h2>Follow the evidence</h2>
                          <p>
                            Server-enforced stages, from the affected pod to its
                            dependencies.
                          </p>
                        </div>
                        <button
                          className="primary"
                          disabled={busy}
                          onClick={() =>
                            perform(async () => {
                              await post(`/cases/${caseId}/investigations`, {});
                              await refresh();
                            })
                          }
                        >
                          <Activity size={16} /> Investigate
                        </button>
                      </div>
                      {data.runs.length ? (
                        data.runs.map((r: Any) => (
                          <div key={r.id} className="run panel">
                            <div className="section-title">
                              <h3>
                                Run {r.id.slice(0, 8)}{" "}
                                <small>
                                  revision {r.revision} · {r.provider}
                                </small>
                              </h3>
                              <Badge>{r.status}</Badge>
                            </div>
                            {r.summary && (
                              <p
                                className={
                                  r.coverage?.gaps?.length && !r.findings.length
                                    ? "notice"
                                    : "summary"
                                }
                              >
                                {r.coverage?.gaps?.length && !r.findings.length
                                  ? "Investigation incomplete. Missing evidence or component mappings prevented assessment. No root-cause or health conclusion is available."
                                  : r.summary}
                              </p>
                            )}
                            <div className="stage-list">
                              {r.stages.map((s: Any, i: number) => (
                                <div className="stage" key={i}>
                                  <div className="stage-dot">{i + 1}</div>
                                  <div>
                                    <small>{s.component}</small>
                                    <h4>
                                      {s.stage} <Badge>{s.outcome}</Badge>
                                    </h4>
                                    <p>{s.detail}</p>
                                    {s.evidence.map((e: Any) => (
                                      <button
                                        key={e.event_id}
                                        className="citation"
                                        onClick={() => showEvidence(e)}
                                      >
                                        <FileText size={12} />
                                        {e.path.split("/").pop()}:{e.line}
                                      </button>
                                    ))}
                                  </div>
                                </div>
                              ))}
                            </div>
                            {r.findings.map((f: Any) => (
                              <div className="finding" key={f.id}>
                                <Badge>{f.classification}</Badge>
                                <h3>{f.title}</h3>
                                <p>{f.explanation}</p>
                                {f.evidence.map((e: Any) => (
                                  <button
                                    className="evidence-line"
                                    key={e.event_id}
                                    onClick={() => showEvidence(e)}
                                  >
                                    <code>{e.excerpt}</code>
                                    <small>
                                      {e.path}:{e.line}{" "}
                                      <ChevronRight size={12} />
                                    </small>
                                  </button>
                                ))}
                              </div>
                            ))}
                            {r.coverage.gaps?.length > 0 && (
                              <div className="notice">
                                <AlertTriangle size={18} />
                                <div>
                                  <div className="coverage-actions">
                                    <strong>
                                      Evidence limitations / next checks
                                    </strong>
                                    <button
                                      className="secondary"
                                      onClick={() => setTab("Intake")}
                                    >
                                      Add evidence in Intake
                                    </button>
                                  </div>
                                  <StorageEvidenceHelp run={r} />
                                  <ul>
                                    {r.coverage.gaps.map((g: string) => (
                                      <li key={g}>{g}</li>
                                    ))}
                                  </ul>
                                </div>
                              </div>
                            )}
                            {["Findings Ready", "Partial", "Awaiting Input", "Approved"].includes(r.status) && r.digest && (
                              <div className="panel report-actions">
                                <h3>Detailed preliminary investigation report</h3>
                                <p>Evidence-based observations, hypotheses, counterevidence, timeline and next checks for this run. Preliminary and unapproved; authorship and analysis limits are identified inside the report.</p>
                                {r.preliminary_report_available ? <>
                                <a className="secondary" target="_blank" rel="noreferrer" href={`/api/runs/${r.id}/preliminary-report?download=false`}>View detailed report</a>
                                <a className="primary" href={`/api/runs/${r.id}/preliminary-report`}><Download size={15} /> Download detailed preliminary HTML</a>
                                </> : <button className="primary" disabled={busy || !["admin", "investigator", "reviewer"].includes(user.role)} onClick={() => perform(async () => { await post(`/runs/${r.id}/preliminary-report`, {}); await refresh(); })}>Generate detailed preliminary report</button>}
                              </div>
                            )}
                            {r.digest &&
                              r.status !== "Invalidated" &&
                              (r.status === "Approved" ||
                                r.findings.length > 0 ||
                                !r.coverage?.gaps?.length) && (
                                <div className="report-actions">
                                  {["admin", "reviewer"].includes(
                                    user.role,
                                  ) && (
                                    <FindingsEditor
                                      run={r}
                                      perform={perform}
                                      refresh={refresh}
                                    />
                                  )}
                                  <span>
                                    <ShieldCheck size={17} /> Review findings
                                    before creating the report.
                                  </span>
                                  {r.status === "Approved" ? (
                                    <a
                                      className="primary"
                                      href={`/api/runs/${r.id}/report`}
                                    >
                                      <Download size={15} /> Download approved findings
                                      HTML
                                    </a>
                                  ) : (
                                    <button
                                      className="primary"
                                      disabled={
                                        busy ||
                                        !["admin", "reviewer"].includes(
                                          user.role,
                                        )
                                      }
                                      onClick={() =>
                                        perform(async () => {
                                          await post(`/runs/${r.id}/approve`, {
                                            digest: r.digest,
                                          });
                                          await refresh();
                                        })
                                      }
                                    >
                                      <CheckCircle2 size={16} /> Approve
                                      findings & create report
                                    </button>
                                  )}
                                </div>
                              )}
                          </div>
                        ))
                      ) : (
                        <Empty
                          title="Ready when your evidence is"
                          detail="Complete intake, then start the Kubernetes-first investigation. Results will appear here."
                        />
                      )}
                    </>
                  )}
                  {tab === "Archives" && (
                    <>
                      <h2>Evidence versions</h2>
                      <ArchiveComparison
                        caseId={caseId}
                        uploads={data.uploads}
                        perform={perform}
                      />
                      <p>
                        Uploads are immutable. New evidence creates a new case
                        revision.
                      </p>
                      {data.uploads.map((u: Any) => (
                        <div className="archive panel" key={u.id}>
                          <FileText />
                          <div>
                            <strong>{u.name}</strong>
                            <small>
                              {(u.size / 1024).toFixed(1)} KB ·{" "}
                              {u.roles.join(", ")} · {u.sha256?.slice(0, 16)}
                            </small>
                            {u.error && <p className="error">{u.error}</p>}
                          </div>
                          <Badge>{u.deleted ? "Deleted" : u.status}</Badge>
                          {!u.deleted && (
                            <button
                              className="icon"
                              aria-label={`Delete ${u.name}`}
                              onClick={() =>
                                perform(async () => {
                                  const preview = await post(
                                    `/uploads/${u.id}/deletion-preview`,
                                  );
                                  if (
                                    window.confirm(
                                      `${preview.warning}\nAffected runs: ${preview.affected_runs.length}. Delete this archive?`,
                                    )
                                  ) {
                                    await api(`/uploads/${u.id}`, {
                                      method: "DELETE",
                                      body: JSON.stringify({
                                        revision: preview.revision,
                                        confirm: true,
                                      }),
                                    });
                                    await refresh();
                                  }
                                })
                              }
                            >
                              <Trash2 size={17} />
                            </button>
                          )}
                        </div>
                      ))}
                    </>
                  )}
                  {tab === "Audit" && <AuditPanel caseId={caseId} />}
                  {tab === "Timeline" && (
                    <TimelinePanel
                      caseId={caseId}
                      perform={perform}
                      showEvidence={showEvidence}
                    />
                  )}
                  {tab === "Jobs" && (
                    <JobControls
                      jobs={data.jobs}
                      perform={perform}
                      refresh={refresh}
                    />
                  )}
                  {data.jobs.some((j: Any) =>
                    ["Queued", "Running"].includes(j.status),
                  ) && (
                    <div className="job-status">
                      <Activity size={17} />
                      {
                        data.jobs.find((j: Any) =>
                          ["Queued", "Running"].includes(j.status),
                        )?.progress
                      }
                    </div>
                  )}
                </div>
                <ChatPanel
                  provider={settings?.llm.provider || "mock"}
                  caseId={caseId}
                  messages={data.messages}
                  refresh={refresh}
                  perform={perform}
                />
              </div>
            </div>
          ))}
        {view === "settings" && (
          <div className="page">
            <p className="eyebrow">ADMINISTRATION</p>
            <h1>Model & deployment settings</h1>
            <p>
              Credentials stay on the server. Change providers through
              deployment configuration.
            </p>
            {user.role === "admin" && <UserAdministration perform={perform} />}
            <div className="panel settings-panel">
              <h2>
                <Bot size={22} /> Model connection
              </h2>
              <Badge>{settings?.llm.provider}</Badge>
              <dl>
                {Object.entries(settings?.llm || {}).map(([k, v]) => (
                  <React.Fragment key={k}>
                    <dt>{k.replaceAll("_", " ")}</dt>
                    <dd>{String(v)}</dd>
                  </React.Fragment>
                ))}
              </dl>
              <p>
                To connect the approved company model, set{" "}
                <code>CPE_LLM_PROVIDER=compatible</code>,{" "}
                <code>CPE_LLM_BASE_URL</code>, <code>CPE_LLM_MODEL</code>,{" "}
                <code>CPE_LLM_ALLOWED_HOSTS</code>, and a server-side key or
                secret file. Restart API and worker.
              </p>
              <div className="notice">
                <ShieldCheck size={18} /> This build uses deterministic evidence
                traversal and optional model synthesis. Production rollout
                requires the validation gates documented in the project.
              </div>
            </div>
          </div>
        )}
        {view === "knowledge" && (
          <div className="page">
            <p className="eyebrow">PRODUCT CONTEXT</p>
            <h1>Knowledge catalog</h1>
            <p>
              Versioned component documentation. Case configuration determines
              the current investigation mappings.
            </p>
            <KnowledgeEditor
              perform={perform}
              reload={async () => setKnowledge(await api("/knowledge"))}
            />
            {knowledge.map((k) => (
              <div className="panel knowledge" key={k.id}>
                <h2>
                  {k.name} <Badge>{k.version}</Badge>
                </h2>
                <pre>{JSON.stringify(k.content, null, 2)}</pre>
              </div>
            ))}
          </div>
        )}
      </main>
      {create && (
        <div className="modal-backdrop">
          <form
            className="modal"
            onSubmit={(e) => {
              e.preventDefault();
              perform(async () => {
                const c = await post("/cases", newCase);
                setCreate(false);
                openCase(c.id);
                setTab("Intake");
                setNewCase({
                  title: "",
                  customer: "",
                  description: "",
                  severity: "Medium",
                });
              });
            }}
          >
            <div className="section-title">
              <h2>Create a new case</h2>
              <button
                type="button"
                className="icon"
                aria-label="Close"
                onClick={() => setCreate(false)}
              >
                <X />
              </button>
            </div>
            <p>Start with the context. Add evidence in the next step.</p>
            <label>
              Case title
              <input
                autoFocus
                required
                value={newCase.title}
                onChange={(e) =>
                  setNewCase({ ...newCase, title: e.target.value })
                }
              />
            </label>
            <label>
              Customer
              <input
                required
                value={newCase.customer}
                onChange={(e) =>
                  setNewCase({ ...newCase, customer: e.target.value })
                }
              />
            </label>
            <label>
              Incident description
              <textarea
                value={newCase.description}
                onChange={(e) =>
                  setNewCase({ ...newCase, description: e.target.value })
                }
              />
            </label>
            <label>
              Severity
              <select
                value={newCase.severity}
                onChange={(e) =>
                  setNewCase({ ...newCase, severity: e.target.value })
                }
              >
                {["Low", "Medium", "High", "Critical"].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <button className="primary" disabled={busy}>
              Create case & add evidence <ArrowRight size={16} />
            </button>
          </form>
        </div>
      )}
      {evidence && (
        <div className="modal-backdrop" onClick={() => setEvidence(null)}>
          <div
            className="modal evidence-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="section-title">
              <div>
                <p className="eyebrow">SOURCE EVIDENCE</p>
                <h2>{evidence.file.path}</h2>
              </div>
              <button
                className="icon"
                aria-label="Close evidence"
                onClick={() => setEvidence(null)}
              >
                <X />
              </button>
            </div>
            <small>SHA-256 {evidence.file.sha256}</small>
            <div className="log-view">
              {evidence.items.map((e: Any) => (
                <div
                  key={e.event_id}
                  className={"log-line " + e.severity.toLowerCase()}
                >
                  <span>{e.line}</span>
                  <code>{e.excerpt}</code>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
