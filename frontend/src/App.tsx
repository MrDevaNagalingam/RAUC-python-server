import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  Activity,
  AlertCircle,
  ArrowUpRight,
  Boxes,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  Clock3,
  Cpu,
  FileClock,
  HardDriveDownload,
  Layers3,
  LayoutDashboard,
  LogOut,
  Menu,
  Package,
  Plus,
  RefreshCw,
  Rocket,
  Search,
  Settings2,
  ShieldCheck,
  Upload,
  Users,
  X,
} from "lucide-react";
import { api, requestKey, setCsrf, uploadFirmware } from "./services/api";
import {
  Badge,
  bytes,
  Empty,
  Field,
  Modal,
  Progress,
  when,
} from "./components/ui";
import type {
  Audit,
  Deployment,
  DeploymentEvent,
  Distribution,
  Firmware,
  Module,
  Settings,
  Summary,
  Target,
  User,
} from "./types";

const pages = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "targets", label: "Targets", icon: Cpu },
  { id: "firmware", label: "Firmware", icon: Package },
  { id: "modules", label: "Software modules", icon: Boxes },
  { id: "releases", label: "Distributions", icon: Layers3 },
  { id: "deployments", label: "Deployments", icon: Rocket },
  { id: "history", label: "Update history", icon: FileClock },
  { id: "settings", label: "Configuration", icon: Settings2 },
  { id: "users", label: "Users", icon: Users, admin: true },
  { id: "audit", label: "Audit logs", icon: ShieldCheck, admin: true },
];
interface Data {
  targets: Target[];
  firmware: Firmware[];
  modules: Module[];
  releases: Distribution[];
  deployments: Deployment[];
  summary: Summary | null;
  settings: Settings | null;
  users: User[];
  audit: Audit[];
}
const initial: Data = {
  targets: [],
  firmware: [],
  modules: [],
  releases: [],
  deployments: [],
  summary: null,
  settings: null,
  users: [],
  audit: [],
};
type Dialog = {
  kind: string;
  target?: Target;
  artifact?: Firmware;
  release?: Distribution;
  deployment?: Deployment;
  user?: User;
  token?: string;
};
const descriptions: Record<string, string> = {
  overview: "A live view of your embedded fleet and software delivery.",
  targets: "Manage device identities, connectivity and reported attributes.",
  firmware: "Store RAUC bundles with checksums and version metadata.",
  modules: "Package one complete OS bundle for the unchanged updater.",
  releases: "Version deployable software and inspect its contents.",
  deployments: "Assign releases deliberately and follow target feedback.",
  history: "Review completed actions and their installation evidence.",
  settings: "Effective server configuration for this instance.",
  users: "Manage dashboard access with separate administrator credentials.",
  audit: "Trace administrator actions and device security events.",
};

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [page, setPage] = useState(location.hash.slice(1) || "overview");
  const [data, setData] = useState<Data>(initial);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [updated, setUpdated] = useState<string | null>(null);
  const [mobile, setMobile] = useState(false);
  const [search, setSearch] = useState("");
  const [showDeleted, setShowDeleted] = useState(false);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [dialogError, setDialogError] = useState("");
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [selectedTarget, setSelectedTarget] = useState("");
  const [selectedRelease, setSelectedRelease] = useState("");
  const [assignmentKey, setAssignmentKey] = useState(requestKey());
  const [detail, setDetail] = useState<Deployment | null>(null);
  const [timeline, setTimeline] = useState<DeploymentEvent[]>([]);

  const navigate = useCallback((next: string) => {
    location.hash = next;
    setPage(next);
    setMobile(false);
    setSearch("");
    setError("");
  }, []);
  useEffect(() => {
    const route = () => setPage(location.hash.slice(1) || "overview");
    const expire = () => {
      setUser(null);
      setCsrf("");
      setData(initial);
      setDialog(null);
      setDetail(null);
    };
    window.addEventListener("hashchange", route);
    window.addEventListener("session-expired", expire);
    api<{ user: User; csrf_token: string }>("/auth/me")
      .then((result) => {
        setUser(result.user);
        setCsrf(result.csrf_token);
      })
      .catch(() => {})
      .finally(() => setInitializing(false));
    return () => {
      window.removeEventListener("hashchange", route);
      window.removeEventListener("session-expired", expire);
    };
  }, []);

  const refresh = useCallback(async () => {
    if (!user) return;
    setRefreshing(true);
    try {
      const [
        targets,
        firmware,
        modules,
        releases,
        deployments,
        summary,
        settings,
        users,
        audit,
      ] = await Promise.all([
        api<Target[]>("/targets?include_deleted=true"),
        api<Firmware[]>("/firmware"),
        api<Module[]>("/software-modules"),
        api<Distribution[]>("/distributions"),
        api<Deployment[]>("/deployments"),
        api<Summary>("/dashboard/summary"),
        api<Settings>("/settings"),
        user.role === "admin"
          ? api<User[]>("/users")
          : Promise.resolve([] as User[]),
        user.role === "admin"
          ? api<Audit[]>("/audit-logs")
          : Promise.resolve([] as Audit[]),
      ]);
      setData({
        targets,
        firmware,
        modules,
        releases,
        deployments,
        summary,
        settings,
        users,
        audit,
      });
      setUpdated(new Date().toISOString());
      setError("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRefreshing(false);
    }
  }, [user]);
  useEffect(() => {
    if (user) {
      void refresh();
      const interval = setInterval(() => void refresh(), 5000);
      return () => clearInterval(interval);
    }
  }, [refresh, user]);
  useEffect(() => {
    if (!detail || !user) return;
    let alive = true;
    const load = async () => {
      try {
        const [deployment, events] = await Promise.all([
          api<Deployment>(`/deployments/${detail.id}`),
          api<DeploymentEvent[]>(`/deployments/${detail.id}/events`),
        ]);
        if (alive) {
          setDetail(deployment);
          setTimeline(events);
        }
      } catch (err) {
        if (alive) setError((err as Error).message);
      }
    };
    void load();
    const timer = setInterval(load, 3000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [detail?.id, user]);

  const open = (next: Dialog) => {
    setDialog(next);
    setDialogError("");
    setUploadProgress(null);
    setAssignmentKey(requestKey());
    if (next.kind === "deployment") {
      setSelectedTarget(next.target ? String(next.target.id) : "");
      setSelectedRelease("");
    }
  };
  const close = () => {
    if (!busy) {
      setDialog(null);
      setDialogError("");
    }
  };
  const canWrite = user?.role === "admin" || user?.role === "operator";
  const isAdmin = user?.role === "admin";
  const targetName = (id: number) =>
    data.targets.find((t) => t.id === id)?.name || `Target #${id}`;
  const release = data.releases.find((r) => String(r.id) === selectedRelease);
  const releaseModule = data.modules.find((m) => m.id === release?.module_id);
  const releaseArtifact = data.firmware.find(
    (a) => a.id === releaseModule?.artifact_id,
  );
  const filtered = <T,>(items: T[]) =>
    items.filter((item) =>
      JSON.stringify(item).toLowerCase().includes(search.toLowerCase()),
    );

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const result = await api<{ user: User; csrf_token: string }>(
        "/auth/login",
        "POST",
        Object.fromEntries(form),
      );
      setCsrf(result.csrf_token);
      setUser(result.user);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dialog) return;
    const form = new FormData(event.currentTarget);
    const values = Object.fromEntries(form) as Record<string, string>;
    setBusy(true);
    setDialogError("");
    let replacement: Dialog | null = null;
    try {
      switch (dialog.kind) {
        case "target": {
          const result = await api<{ token: string }>(
            "/targets",
            "POST",
            values,
          );
          replacement = { kind: "token", token: result.token };
          break;
        }
        case "edit-target":
          await api(`/targets/${dialog.target!.id}`, "PATCH", {
            name: values.name,
            description: values.description,
            enabled: values.enabled === "on",
            polling_interval_seconds: values.polling_interval_seconds
              ? Number(values.polling_interval_seconds)
              : null,
          });
          break;
        case "rotate": {
          const result = await api<{ token: string }>(
            `/targets/${dialog.target!.id}/rotate-token`,
            "POST",
          );
          replacement = { kind: "token", token: result.token };
          break;
        }
        case "revoke":
          await api(`/targets/${dialog.target!.id}/revoke-token`, "POST");
          break;
        case "delete-target":
          if (
            values.controller_id_confirmation !== dialog.target!.controller_id
          ) {
            throw new Error(
              "Type the exact controller ID to confirm deletion.",
            );
          }
          await api(`/targets/${dialog.target!.id}`, "DELETE");
          break;
        case "restore-target":
          await api(`/targets/${dialog.target!.id}/restore`, "POST");
          break;
        case "purge-target":
          if (values.controller_id_confirmation !== dialog.target!.controller_id) {
            throw new Error(
              "Type the exact controller ID to confirm permanent deletion.",
            );
          }
          await api(`/targets/${dialog.target!.id}/permanent`, "DELETE", {
            controller_id_confirmation: values.controller_id_confirmation,
          });
          break;
        case "firmware":
          await uploadFirmware(form, setUploadProgress);
          break;
        case "withdraw":
          await api(`/firmware/${dialog.artifact!.id}`, "DELETE");
          break;
        case "restore-firmware":
          await api(`/firmware/${dialog.artifact!.id}/restore`, "POST");
          break;
        case "module":
          await api("/software-modules", "POST", {
            ...values,
            artifact_id: Number(values.artifact_id),
          });
          break;
        case "release":
          await api("/distributions", "POST", {
            ...values,
            module_id: Number(values.module_id),
          });
          break;
        case "edit-release":
          await api(`/distributions/${dialog.release!.id}`, "PATCH", {
            description: values.description,
          });
          break;
        case "deployment":
          await api("/deployments", "POST", {
            request_key: assignmentKey,
            target_id: Number(selectedTarget),
            distribution_id: Number(selectedRelease),
            mode: values.mode,
            expected_compatible: values.expected_compatible,
            expected_version: values.expected_version,
            operator_confirmed: true,
            approval_note: values.approval_note,
          });
          break;
        case "cancel":
          await api(`/deployments/${dialog.deployment!.id}/cancel`, "POST");
          break;
        case "retry":
          await api(`/deployments/${dialog.deployment!.id}/retry`, "POST", {
            request_key: assignmentKey,
            operator_confirmed: true,
            approval_note: values.approval_note,
          });
          break;
        case "user":
          await api("/users", "POST", values);
          break;
        case "toggle-user":
          await api(`/users/${dialog.user!.id}`, "PATCH", {
            is_active: !dialog.user!.is_active,
          });
          break;
      }
      setDialog(replacement);
      setNotice("Changes saved.");
      void refresh();
    } catch (err) {
      setDialogError((err as Error).message);
      if (dialog.kind === "firmware") setUploadProgress(null);
    } finally {
      setBusy(false);
    }
  }

  function deploymentsTable(items: Deployment[]) {
    return items.length ? (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Action / target</th>
              <th>Distribution</th>
              <th>Mode</th>
              <th>Status</th>
              <th>Progress</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id}>
                <td>
                  <button
                    className="link"
                    onClick={() => {
                      setDetail(d);
                      setTimeline([]);
                    }}
                  >
                    #{d.id} · {targetName(d.target_id)}
                  </button>
                </td>
                <td>
                  <strong>{d.snapshot.distribution_name}</strong>
                  <small>v{d.snapshot.distribution_version}</small>
                </td>
                <td>{d.mode.replaceAll("_", " ")}</td>
                <td>
                  <Badge value={d.internal_status} />
                </td>
                <td>
                  <Progress value={d.progress} />
                </td>
                <td>{when(d.created_at)}</td>
                <td>
                  <button
                    className="icon-button"
                    aria-label={`View deployment ${d.id}`}
                    onClick={() => {
                      setDetail(d);
                      setTimeline([]);
                    }}
                  >
                    <ChevronRight size={18} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ) : (
      <Empty title="No deployments yet">
        Create a distribution, then explicitly assign it to a target.
      </Empty>
    );
  }

  if (initializing)
    return (
      <div className="loading">
        <Activity size={28} /> Connecting to OTA Control…
      </div>
    );
  if (!user)
    return (
      <div className="login">
        <div className="login-story">
          <div className="brand">
            <span className="brand-icon">
              <Layers3 />
            </span>
            <b>
              OTA<span>CONTROL</span>
            </b>
          </div>
          <div>
            <span className="eyebrow">EMBEDDED SOFTWARE DELIVERY</span>
            <h1>
              A clear view.
              <br />
              Every target.
              <br />
              Every release.
            </h1>
            <p>
              Manage signed RAUC bundles and follow your fleet’s update journey,
              from assignment to installation feedback.
            </p>
            <div className="login-features">
              <span>
                <ShieldCheck /> Separate device credentials
              </span>
              <span>
                <Activity /> hawkBit DDI v1
              </span>
              <span>
                <Cpu /> Existing RAUC updater
              </span>
            </div>
          </div>
          <small>Firmware management · Operator-controlled deployments</small>
        </div>
        <div className="login-side">
          <form onSubmit={login} className="login-form">
            <span className="eyebrow">WORKSPACE ACCESS</span>
            <h2>Welcome back</h2>
            <p>Sign in to your OTA management server.</p>
            {error && (
              <div className="error" role="alert">
                <AlertCircle size={18} />
                {error}
              </div>
            )}
            <Field label="Username">
              <input
                name="username"
                autoComplete="username"
                required
                autoFocus
              />
            </Field>
            <Field label="Password">
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                required
              />
            </Field>
            <button className="primary full" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
              <ArrowUpRight size={18} />
            </button>
            <div className="login-help">
              <CircleHelp size={18} />
              <p>
                First time here? Create an administrator on the host with{" "}
                <code>ota admin-create admin</code>.
              </p>
            </div>
          </form>
        </div>
      </div>
    );

  return (
    <div className="app-shell">
      <aside className={mobile ? "sidebar open" : "sidebar"}>
        <div className="brand">
          <span className="brand-icon">
            <Layers3 />
          </span>
          <b>
            OTA<span>CONTROL</span>
          </b>
          <button
            className="mobile-close icon-button"
            onClick={() => setMobile(false)}
            aria-label="Close navigation"
          >
            <X />
          </button>
        </div>
        <div className="workspace">
          <span className="workspace-symbol">P</span>
          <div>
            <strong>Firmware workspace</strong>
            <small>{data.settings?.app_env || "Connecting"}</small>
          </div>
          <ChevronRight size={16} />
        </div>
        <span className="nav-caption">MANAGEMENT</span>
        <nav>
          {pages
            .filter((p) => !p.admin || isAdmin)
            .map((p) => (
              <a
                href={`#${p.id}`}
                key={p.id}
                className={page === p.id ? "active" : ""}
                onClick={(event) => {
                  event.preventDefault();
                  navigate(p.id);
                }}
              >
                <p.icon size={18} />
                {p.label}
                {p.id === "targets" && (
                  <span className="nav-count">
                    {data.targets.filter((t) => !t.deleted_at).length}
                  </span>
                )}
              </a>
            ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="server-label">
            <span />
            Server workspace
          </div>
          <p>Installation and boot confirmation are tracked separately.</p>
          <div className="user-box">
            <span className="avatar">
              {user.username.slice(0, 2).toUpperCase()}
            </span>
            <div>
              <strong>{user.username}</strong>
              <small>{user.role}</small>
            </div>
            <button
              className="icon-button"
              title="Sign out"
              onClick={async () => {
                try {
                  await api("/auth/logout", "POST");
                  setCsrf("");
                  setUser(null);
                  setData(initial);
                  setDetail(null);
                  setDialog(null);
                } catch (err) {
                  setError((err as Error).message);
                }
              }}
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div>
            <button
              className="icon-button mobile-menu"
              onClick={() => setMobile(true)}
              aria-label="Open navigation"
            >
              <Menu />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>
              {pages.find((p) => p.id === page)?.label || "Overview"}
            </strong>
          </div>
          <div>
            <span className="live">
              <span />
              Refreshes every 5s
            </span>
            <button
              className="icon-button"
              disabled={refreshing}
              onClick={() => void refresh()}
              title="Refresh data"
            >
              <RefreshCw size={17} className={refreshing ? "spin" : ""} />
            </button>
            <span className="avatar small">
              {user.username.slice(0, 2).toUpperCase()}
            </span>
          </div>
        </header>
        <div className="content">
          <div className="page-heading">
            <div>
              <span className="eyebrow">FLEET OPERATIONS</span>
              <h1>{pages.find((p) => p.id === page)?.label || "Overview"}</h1>
              <p>{descriptions[page]}</p>
            </div>
            <div className="heading-actions">
              {page === "targets" && isAdmin && (
                <button
                  className="primary"
                  onClick={() => open({ kind: "target" })}
                >
                  <Plus size={17} /> Add target
                </button>
              )}
              {page === "firmware" && canWrite && (
                <button
                  className="primary"
                  onClick={() => open({ kind: "firmware" })}
                >
                  <Upload size={17} /> Upload firmware
                </button>
              )}
              {page === "modules" && canWrite && (
                <button
                  className="primary"
                  onClick={() => open({ kind: "module" })}
                >
                  <Plus size={17} /> Create module
                </button>
              )}
              {page === "releases" && canWrite && (
                <button
                  className="primary"
                  onClick={() => open({ kind: "release" })}
                >
                  <Plus size={17} /> Create distribution
                </button>
              )}
              {(page === "deployments" || page === "overview") && canWrite && (
                <button
                  className="primary"
                  onClick={() => open({ kind: "deployment" })}
                >
                  <Rocket size={17} /> New deployment
                </button>
              )}
              {page === "users" && isAdmin && (
                <button
                  className="primary"
                  onClick={() => open({ kind: "user" })}
                >
                  <Plus size={17} /> Add user
                </button>
              )}
            </div>
          </div>
          {error && (
            <div className="error" role="alert">
              <AlertCircle size={18} />
              {error}
            </div>
          )}
          {notice && (
            <div className="notice" role="status">
              <CheckCircle2 size={18} />
              {notice}
              <button
                className="icon-button"
                aria-label="Dismiss notice"
                onClick={() => setNotice("")}
              >
                <X size={16} />
              </button>
            </div>
          )}

          {page === "overview" && (
            <>
              <div className="metrics">
                {[
                  [
                    "Total targets",
                    data.summary?.total_targets ?? 0,
                    Cpu,
                    `${data.summary?.online_targets ?? 0} online · ${data.summary?.offline_targets ?? 0} offline`,
                  ],
                  [
                    "Firmware versions",
                    data.summary?.firmware_versions ?? 0,
                    Package,
                    "Immutable bundle checksums",
                  ],
                  [
                    "Active deployments",
                    data.summary?.active_deployments ?? 0,
                    Rocket,
                    `${data.summary?.pending_deployments ?? 0} waiting for target`,
                  ],
                  [
                    "Successful installations",
                    data.summary?.successful_installations ?? 0,
                    CheckCircle2,
                    `${data.summary?.failed_installations ?? 0} reported failures`,
                  ],
                ].map(([label, value, Icon, hint]) => {
                  const MetricIcon = Icon as typeof Cpu;
                  return (
                    <article className="metric" key={String(label)}>
                      <div>
                        <span>{String(label)}</span>
                        <MetricIcon size={18} />
                      </div>
                      <strong>{String(value)}</strong>
                      <small>{String(hint)}</small>
                    </article>
                  );
                })}
              </div>
              <div className="overview-grid">
                <section className="card fleet-card">
                  <div className="section-heading">
                    <div>
                      <h2>Fleet connectivity</h2>
                      <p>Inferred from authenticated device activity</p>
                    </div>
                    <Activity size={20} />
                  </div>
                  <div className="fleet-stats">
                    <div className="fleet-number">
                      {data.summary?.online_targets ?? 0}
                      <small>targets online</small>
                    </div>
                    <div className="fleet-breakdown">
                      {["Online", "Offline", "Never Connected", "Disabled"].map(
                        (status) => (
                          <div key={status}>
                            <Badge value={status} />
                            <b>
                              {
                                data.targets.filter(
                                  (t) => t.connection_status === status,
                                ).length
                              }
                            </b>
                          </div>
                        ),
                      )}
                    </div>
                  </div>
                  <button
                    className="text-action"
                    onClick={() => navigate("targets")}
                  >
                    View all targets <ArrowUpRight size={16} />
                  </button>
                </section>
                <section className="card workflow-card">
                  <div className="section-heading">
                    <div>
                      <h2>Release workflow</h2>
                      <p>Prepare software before assigning it</p>
                    </div>
                    <Layers3 size={20} />
                  </div>
                  {[
                    {
                      n: "01",
                      name: "Upload a signed bundle",
                      note: "Store and checksum the .raucb artifact",
                      to: "firmware",
                    },
                    {
                      n: "02",
                      name: "Create a module and distribution",
                      note: "Version the deployable release",
                      to: "modules",
                    },
                    {
                      n: "03",
                      name: "Review and assign",
                      note: "Confirm identity, compatibility and recovery",
                      to: "deployments",
                    },
                  ].map((step) => (
                    <button
                      className="workflow-step"
                      key={step.n}
                      onClick={() => navigate(step.to)}
                    >
                      <span>{step.n}</span>
                      <div>
                        <strong>{step.name}</strong>
                        <small>{step.note}</small>
                      </div>
                      <ChevronRight size={16} />
                    </button>
                  ))}
                </section>
              </div>
              <section className="card">
                <div className="section-heading">
                  <div>
                    <h2>Recent deployments</h2>
                    <p>Latest assignments and target-reported progress</p>
                  </div>
                  <button
                    className="text-action"
                    onClick={() => navigate("deployments")}
                  >
                    View all <ArrowUpRight size={16} />
                  </button>
                </div>
                {deploymentsTable(data.deployments.slice(0, 6))}
              </section>
              <div className="evidence-note">
                <ShieldCheck size={18} />
                <p>
                  An installation success confirms the target’s installation
                  report. A successful boot requires separate evidence and stays
                  unknown here.
                </p>
              </div>
            </>
          )}

          {[
            "targets",
            "firmware",
            "modules",
            "releases",
            "deployments",
            "history",
            "users",
            "audit",
          ].includes(page) && (
            <div className="list-toolbar">
              {page === "targets" && isAdmin && (
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={showDeleted}
                    onChange={(event) => setShowDeleted(event.target.checked)}
                  />
                  Show deleted targets
                </label>
              )}
              <div className="search">
                <Search size={17} />
                <input
                  aria-label="Search current list"
                  placeholder={`Search ${pages.find((p) => p.id === page)?.label.toLowerCase()}…`}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <span>
                {updated
                  ? `Updated ${new Date(updated).toLocaleTimeString()}`
                  : "Loading data…"}
              </span>
            </div>
          )}

          {page === "targets" && (
            <section className="card">
              {filtered(
                data.targets.filter((t) => showDeleted || !t.deleted_at),
              ).length ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Target</th>
                        <th>Hardware</th>
                        <th>Connectivity</th>
                        <th>Last seen</th>
                        <th>Installed / running</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {filtered(
                        data.targets.filter(
                          (t) => showDeleted || !t.deleted_at,
                        ),
                      ).map((t) => (
                        <tr key={t.id}>
                          <td>
                            <strong>{t.name}</strong>
                            <small>
                              {t.tenant} / {t.controller_id}
                            </small>
                          </td>
                          <td>
                            {t.attributes.model || "Unknown model"}
                            <small>
                              Revision {t.attributes.hw_revision || "unknown"} ·{" "}
                              {t.attributes.mac_address || "Unknown MAC"}
                            </small>
                            <details>
                              <summary>All attributes</summary>
                              <pre>{JSON.stringify(t.attributes, null, 2)}</pre>
                            </details>
                          </td>
                          <td>
                            <Badge value={t.connection_status} />
                          </td>
                          <td>{when(t.last_seen_at)}</td>
                          <td>
                            {t.last_installed_version ||
                              "No installation reported"}
                            <small>
                              Running: {t.running_firmware || "Unknown"}
                            </small>
                          </td>
                          <td>
                            <div className="row-actions">
                              {isAdmin && !t.deleted_at && (
                                <button
                                  className="secondary compact"
                                  onClick={() =>
                                    open({ kind: "edit-target", target: t })
                                  }
                                >
                                  Manage
                                </button>
                              )}
                              {isAdmin && !t.deleted_at && (
                                <button
                                  className="danger compact"
                                  disabled={!!t.deployment?.active}
                                  title={
                                    t.deployment?.active
                                      ? "Active deployment must finish before deleting this target"
                                      : "Delete target"
                                  }
                                  onClick={() =>
                                    open({ kind: "delete-target", target: t })
                                  }
                                >
                                  Delete
                                </button>
                              )}
                              {isAdmin && t.deleted_at && (
                                <button
                                  className="secondary compact"
                                  onClick={() =>
                                    open({ kind: "restore-target", target: t })
                                  }
                                >
                                  Restore
                                </button>
                              )}
                              {isAdmin && t.deleted_at && (
                                <button
                                  className="danger compact"
                                  onClick={() =>
                                    open({ kind: "purge-target", target: t })
                                  }
                                >
                                  Delete permanently
                                </button>
                              )}
                              {canWrite && !t.deleted_at && (
                                <button
                                  className="secondary compact"
                                  disabled={
                                    !t.enabled || !!t.deployment?.active
                                  }
                                  onClick={() =>
                                    open({ kind: "deployment", target: t })
                                  }
                                >
                                  Deploy
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty title="No targets found">
                  Add a target to generate its device credential, then configure
                  the existing updater.
                </Empty>
              )}
            </section>
          )}

          {page === "firmware" && (
            <>
              <div className="info-strip">
                <ShieldCheck size={18} />
                <span>
                  Uploaded bundles are checksummed. Signature and compatibility
                  verification remain mandatory on the RAUC target.
                </span>
              </div>
              <section className="card">
                {filtered(data.firmware).length ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Firmware</th>
                          <th>Compatible device</th>
                          <th>Artifact</th>
                          <th>Availability</th>
                          <th>Uploaded</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {filtered(data.firmware).map((a) => (
                          <tr key={a.id}>
                            <td>
                              <strong>{a.name}</strong>
                              <small>
                                v{a.version} · {a.vendor || "No vendor"}
                              </small>
                            </td>
                            <td>
                              <code>{a.compatible}</code>
                            </td>
                            <td>
                              {a.filename}
                              <small>{bytes(a.size)}</small>
                              <details>
                                <summary>Checksums</summary>
                                <div className="hashes">
                                  <small>SHA-256</small>
                                  <code>{a.sha256}</code>
                                  <small>SHA-1 · updater verification</small>
                                  <code>{a.sha1}</code>
                                  <small>
                                    Signature:{" "}
                                    {a.signature_status
                                      .replaceAll("_", " ")
                                      .toLowerCase()}
                                  </small>
                                </div>
                              </details>
                            </td>
                            <td>
                              <Badge
                                value={a.available ? "Available" : "Withdrawn"}
                              />
                            </td>
                            <td>{when(a.created_at)}</td>
                            <td>
                              {canWrite && a.available && (
                                <button
                                  className="secondary compact"
                                  onClick={() =>
                                    open({ kind: "withdraw", artifact: a })
                                  }
                                >
                                  Withdraw
                                </button>
                              )}
                              {canWrite && !a.available && (
                                <button
                                  className="secondary compact"
                                  onClick={() =>
                                    open({ kind: "restore-firmware", artifact: a })
                                  }
                                >
                                  Restore
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty title="No firmware found">
                    Upload a .raucb bundle with its version and compatible
                    string.
                  </Empty>
                )}
              </section>
            </>
          )}

          {page === "modules" && (
            <section className="card">
              {filtered(data.modules).length ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Module</th>
                        <th>Type</th>
                        <th>Artifact</th>
                        <th>Vendor</th>
                        <th>Description</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered(data.modules).map((m) => (
                        <tr key={m.id}>
                          <td>
                            <strong>{m.name}</strong>
                            <small>
                              v{m.version} · #{m.id}
                            </small>
                          </td>
                          <td>
                            <Badge value={m.type} />
                          </td>
                          <td>
                            {data.firmware.find((a) => a.id === m.artifact_id)
                              ?.filename || `Artifact #${m.artifact_id}`}
                          </td>
                          <td>{m.vendor || "—"}</td>
                          <td>{m.description || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty title="No software modules found">
                  Associate an uploaded RAUC bundle with an OS module.
                </Empty>
              )}
            </section>
          )}

          {page === "releases" && (
            <div className="release-grid">
              {filtered(data.releases).length ? (
                filtered(data.releases).map((r) => {
                  const module = data.modules.find((m) => m.id === r.module_id);
                  const artifact = data.firmware.find(
                    (a) => a.id === module?.artifact_id,
                  );
                  return (
                    <article className="card release-card" key={r.id}>
                      <div className="release-header">
                        <span className="release-icon">
                          <Layers3 size={23} />
                        </span>
                        <Badge
                          value={
                            artifact?.available ? "Available" : "Unavailable"
                          }
                        />
                      </div>
                      <h2>{r.name}</h2>
                      <p className="release-version">Version {r.version}</p>
                      <p>{r.description || "No description provided."}</p>
                      <dl>
                        <dt>Software module</dt>
                        <dd>
                          {module?.name} {module?.version}
                        </dd>
                        <dt>Artifact</dt>
                        <dd>{artifact?.filename || "Unknown"}</dd>
                        <dt>Compatible</dt>
                        <dd>
                          <code>{artifact?.compatible || "Unknown"}</code>
                        </dd>
                      </dl>
                      {canWrite && (
                        <button
                          className="secondary full"
                          onClick={() =>
                            open({ kind: "edit-release", release: r })
                          }
                        >
                          Edit description
                        </button>
                      )}
                    </article>
                  );
                })
              ) : (
                <section className="card span-all">
                  <Empty title="No distributions found">
                    Create a versioned distribution from an OS module.
                  </Empty>
                </section>
              )}
            </div>
          )}

          {(page === "deployments" || page === "history") && (
            <section className="card">
              {deploymentsTable(
                filtered(
                  data.deployments.filter(
                    (d) => page !== "history" || !d.active,
                  ),
                ),
              )}
            </section>
          )}

          {page === "settings" && data.settings && (
            <section className="card settings-card">
              <div className="section-heading">
                <div>
                  <h2>Server configuration</h2>
                  <p>Effective values loaded at server startup</p>
                </div>
                <Badge value={data.settings.app_env} />
              </div>
              <dl className="settings-list">
                {Object.entries(data.settings).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key.replaceAll("_", " ")}</dt>
                    <dd>{String(value)}</dd>
                  </div>
                ))}
              </dl>
              <div className="info-strip">
                <Settings2 size={18} />
                <span>
                  Change these values in the host’s environment configuration
                  and restart the server. Secrets and database credentials are
                  never displayed.
                </span>
              </div>
              <div className="settings-policy">
                <h3>Supported updater behavior</h3>
                <p>
                  Forced and Download Only · One OS module with one RAUC bundle
                  · TargetToken authentication · Single HTTP byte ranges
                </p>
                <h3>Boot confirmation</h3>
                <p>
                  Unknown until independently verified. This server does not
                  request device reboots.
                </p>
              </div>
            </section>
          )}

          {page === "users" && isAdmin && (
            <section className="card">
              {filtered(data.users).length ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Username</th>
                        <th>Role</th>
                        <th>Status</th>
                        <th>Created</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {filtered(data.users).map((u) => (
                        <tr key={u.id}>
                          <td>
                            <strong>{u.username}</strong>
                            {u.id === user.id && <small>Your account</small>}
                          </td>
                          <td>
                            <Badge value={u.role} />
                          </td>
                          <td>
                            <Badge
                              value={u.is_active ? "Available" : "Disabled"}
                            />
                          </td>
                          <td>{when(u.created_at)}</td>
                          <td>
                            <button
                              className="secondary compact"
                              disabled={u.id === user.id}
                              onClick={() =>
                                open({ kind: "toggle-user", user: u })
                              }
                            >
                              {u.is_active ? "Disable" : "Enable"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty title="No users found" />
              )}
            </section>
          )}

          {page === "audit" && isAdmin && (
            <section className="card">
              <div className="section-heading">
                <div>
                  <h2>Recent audit events</h2>
                  <p>Latest 100 events · Security and administrative history</p>
                </div>
                <ShieldCheck size={20} />
              </div>
              {filtered(data.audit).length ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Operation</th>
                        <th>Actor</th>
                        <th>Resource</th>
                        <th>Details</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered(data.audit).map((a) => (
                        <tr key={a.id}>
                          <td>{when(a.timestamp)}</td>
                          <td>
                            <code>{a.operation}</code>
                          </td>
                          <td>{a.actor}</td>
                          <td>
                            {a.resource_type}{" "}
                            {a.resource_id ? `#${a.resource_id}` : ""}
                          </td>
                          <td>
                            <details>
                              <summary>Inspect</summary>
                              <pre>{JSON.stringify(a.details, null, 2)}</pre>
                            </details>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty title="No matching audit events" />
              )}
            </section>
          )}
          {!pages.some((p) => p.id === page) && (
            <Empty title="Page not found">
              <button className="link" onClick={() => navigate("overview")}>
                Return to overview
              </button>
            </Empty>
          )}
          <footer>
            <span>
              OTA Control <b>v0.2</b>
            </span>
            <span>hawkBit DDI v1 · RAUC</span>
          </footer>
        </div>
      </main>

      {dialog && (
        <Modal
          title={
            {
              target: "Add a target",
              "edit-target": "Manage target",
              rotate: "Rotate device token",
              revoke: "Revoke device token",
              "delete-target": "Delete target",
              "restore-target": "Restore target",
              "purge-target": "Delete target permanently",
              token: "Device credential created",
              firmware: "Upload firmware",
              withdraw: "Withdraw firmware",
              "restore-firmware": "Restore firmware",
              module: "Create software module",
              release: "Create distribution",
              "edit-release": "Edit distribution",
              deployment: "Review deployment assignment",
              cancel: "Cancel assignment",
              retry: "Retry failed deployment",
              user: "Add user",
              "toggle-user": "Change user access",
            }[dialog.kind] || "Review action"
          }
          close={close}
          busy={busy}
        >
          {dialog.kind === "token" ? (
            <div className="modal-body">
              <div className="info-strip">
                <ShieldCheck size={20} />
                <span>
                  Save this token now. It is shown only once and grants access
                  only to this device’s DDI resources.
                </span>
              </div>
              <Field label="TargetToken">
                <textarea
                  readOnly
                  rows={3}
                  value={dialog.token}
                  onFocus={(e) => e.currentTarget.select()}
                />
              </Field>
              <p>
                Provision it privately into the target updater’s{" "}
                <code>auth_token</code> setting.
              </p>
              <button className="primary full" onClick={close}>
                I have saved the credential
              </button>
            </div>
          ) : (
            <form onSubmit={submit}>
              <div className="modal-body">
                {dialogError && (
                  <div className="error" role="alert">
                    <AlertCircle size={18} />
                    {dialogError}
                  </div>
                )}
                {dialog.kind === "target" && (
                  <>
                    <Field label="Tenant">
                      <input
                        name="tenant"
                        defaultValue="DEFAULT"
                        pattern="[A-Za-z0-9_-]{1,64}"
                        required
                      />
                    </Field>
                    <Field label="Controller ID">
                      <input
                        name="controller_id"
                        pattern="[A-Za-z0-9_.-]{1,128}"
                        placeholder="gateway-002"
                        required
                      />
                    </Field>
                    <Field label="Display name">
                      <input name="name" required maxLength={255} />
                    </Field>
                    <Field label="Description">
                      <textarea name="description" maxLength={2048} />
                    </Field>
                    <p className="muted">
                      A fresh device token will be generated. Creating a target
                      does not assign firmware.
                    </p>
                  </>
                )}
                {dialog.kind === "edit-target" && (
                  <>
                    <p>
                      <code>
                        {dialog.target!.tenant} / {dialog.target!.controller_id}
                      </code>
                    </p>
                    <Field label="Display name">
                      <input
                        name="name"
                        defaultValue={dialog.target!.name}
                        required
                        maxLength={255}
                      />
                    </Field>
                    <Field label="Description">
                      <textarea
                        name="description"
                        defaultValue={dialog.target!.description}
                        maxLength={2048}
                      />
                    </Field>
                    <Field
                      label="Polling interval override (seconds)"
                      hint="Leave blank to use the server default."
                    >
                      <input
                        type="number"
                        name="polling_interval_seconds"
                        min={1}
                        max={86399}
                        defaultValue={
                          dialog.target!.polling_interval_seconds ?? ""
                        }
                      />
                    </Field>
                    <label className="checkbox">
                      <input
                        name="enabled"
                        type="checkbox"
                        defaultChecked={dialog.target!.enabled}
                      />
                      Target enabled
                    </label>
                    <div className="danger-zone">
                      <p>Device credential operations</p>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() =>
                          open({ kind: "rotate", target: dialog.target })
                        }
                      >
                        Rotate token
                      </button>
                      <button
                        type="button"
                        className="danger"
                        onClick={() =>
                          open({ kind: "revoke", target: dialog.target })
                        }
                      >
                        Revoke token
                      </button>
                    </div>
                  </>
                )}
                {["rotate", "revoke"].includes(dialog.kind) && (
                  <>
                    <p>
                      Target: <strong>{dialog.target!.name}</strong> ·{" "}
                      <code>{dialog.target!.controller_id}</code>
                    </p>
                    <div className="warning">
                      The current credential will stop authenticating subsequent
                      device requests.{" "}
                      {dialog.kind === "rotate"
                        ? "Save the replacement token and provision it on the target."
                        : "The target will remain unable to authenticate until you rotate and provision a new token."}
                    </div>
                    <label className="checkbox">
                      <input type="checkbox" required />I confirm this device
                      credential change.
                    </label>
                  </>
                )}
                {dialog.kind === "delete-target" && (
                  <>
                    <p>
                      Delete <strong>{dialog.target!.name}</strong> ·{" "}
                      <code>
                        {dialog.target!.tenant}/{dialog.target!.controller_id}
                      </code>
                      ?
                    </p>
                    <div className="warning">
                      The target will disappear from the normal fleet list and
                      its device tokens will be revoked. Deployment and audit
                      history remain available. This does not uninstall firmware
                      or change the physical device.
                    </div>
                    <Field label="Type the controller ID to confirm deletion">
                      <input
                        name="controller_id_confirmation"
                        required
                        autoComplete="off"
                        placeholder={dialog.target!.controller_id}
                      />
                    </Field>
                  </>
                )}
                {dialog.kind === "restore-target" && (
                  <>
                    <p>
                      Restore <strong>{dialog.target!.name}</strong> ·{" "}
                      <code>{dialog.target!.controller_id}</code> to the fleet?
                    </p>
                    <p>
                      The target stays disabled and its previous tokens stay
                      revoked. Enable it through Manage, then rotate and
                      privately provision a new token before reconnecting.
                    </p>
                  </>
                )}
                {dialog.kind === "purge-target" && (
                  <>
                    <p>
                      Permanently delete <strong>{dialog.target!.name}</strong> ·{" "}
                      <code>
                        {dialog.target!.tenant}/{dialog.target!.controller_id}
                      </code>?
                    </p>
                    <div className="warning">
                      This cannot be undone. The target, its device tokens,
                      attributes, deployment history and deployment events will
                      be removed. Audit logs and firmware bundles are retained.
                      You can then create a new target with the same controller ID.
                    </div>
                    <Field label="Type the controller ID to confirm permanent deletion">
                      <input
                        name="controller_id_confirmation"
                        required
                        autoComplete="off"
                        placeholder={dialog.target!.controller_id}
                      />
                    </Field>
                  </>
                )}
                {dialog.kind === "firmware" && (
                  <>
                    <Field
                      label="RAUC bundle"
                      hint="Upload the original signed .raucb without repackaging it."
                    >
                      <input name="file" type="file" accept=".raucb" required />
                    </Field>
                    <div className="form-grid">
                      <Field label="Firmware name">
                        <input name="name" required maxLength={255} />
                      </Field>
                      <Field label="Version">
                        <input name="version" required maxLength={128} />
                      </Field>
                    </div>
                    <Field label="RAUC compatible string">
                      <input
                        name="compatible"
                        placeholder="phyboard-segin-imx6ul-7"
                        required
                        maxLength={255}
                      />
                    </Field>
                    <Field label="Vendor">
                      <input name="vendor" maxLength={255} />
                    </Field>
                    <Field label="Description">
                      <textarea name="description" maxLength={8192} />
                    </Field>
                    <p className="muted">
                      Maximum: {data.settings?.max_upload_size_mb} MB. Uploading
                      does not assign firmware. The server records checksums;
                      signature status remains unverified.
                    </p>
                    {uploadProgress !== null && (
                      <>
                        <Progress value={uploadProgress} />
                        <p role="status">
                          {uploadProgress === 100
                            ? "Transfer finished. Calculating checksums and publishing…"
                            : "Uploading firmware…"}
                        </p>
                      </>
                    )}
                  </>
                )}
                {dialog.kind === "withdraw" && (
                  <>
                    <p>
                      Withdraw{" "}
                      <strong>
                        {dialog.artifact!.name} {dialog.artifact!.version}
                      </strong>{" "}
                      from new assignments?
                    </p>
                    <p>
                      Active deployments block withdrawal. Historical metadata
                      and stored bundle contents are retained.
                    </p>
                  </>
                )}
                {dialog.kind === "restore-firmware" && (
                  <>
                    <p>
                      Restore{" "}
                      <strong>
                        {dialog.artifact!.name} {dialog.artifact!.version}
                      </strong>{" "}
                      for new assignments?
                    </p>
                    <p>
                      This reuses the stored bundle and its original metadata.
                      Restoring does not assign firmware to any target.
                    </p>
                  </>
                )}
                {dialog.kind === "module" && (
                  <>
                    <Field label="Module name">
                      <input name="name" required maxLength={255} />
                    </Field>
                    <Field label="Version">
                      <input name="version" required maxLength={128} />
                    </Field>
                    <Field label="OS artifact">
                      <select name="artifact_id" required defaultValue="">
                        <option value="" disabled>
                          Select an available bundle
                        </option>
                        {data.firmware
                          .filter((a) => a.available)
                          .map((a) => (
                            <option key={a.id} value={a.id}>
                              {a.name} {a.version} · {a.filename}
                            </option>
                          ))}
                      </select>
                    </Field>
                    <Field label="Vendor">
                      <input name="vendor" maxLength={255} />
                    </Field>
                    <Field label="Description">
                      <textarea name="description" maxLength={8192} />
                    </Field>
                    <p className="muted">
                      This updater supports one OS module with one complete RAUC
                      bundle.
                    </p>
                  </>
                )}
                {dialog.kind === "release" && (
                  <>
                    <Field label="Distribution name">
                      <input name="name" required maxLength={255} />
                    </Field>
                    <Field label="Version">
                      <input name="version" required maxLength={128} />
                    </Field>
                    <Field label="Software module">
                      <select name="module_id" defaultValue="" required>
                        <option value="" disabled>
                          Select an OS module
                        </option>
                        {data.modules.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.name} {m.version}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Description">
                      <textarea name="description" maxLength={8192} />
                    </Field>
                  </>
                )}
                {dialog.kind === "edit-release" && (
                  <>
                    <p>
                      {dialog.release!.name} · v{dialog.release!.version}
                    </p>
                    <Field label="Description">
                      <textarea
                        name="description"
                        defaultValue={dialog.release!.description}
                        maxLength={8192}
                      />
                    </Field>
                    <p className="muted">
                      Release contents are stable. Create a new version to
                      change the included module.
                    </p>
                  </>
                )}
                {dialog.kind === "deployment" && (
                  <>
                    <div className="warning">
                      Assigning Forced mode allows the target to download and
                      install on its next poll. Review the exact device, bundle
                      and recovery path before confirming.
                    </div>
                    <Field label="Target">
                      <select
                        required
                        value={selectedTarget}
                        onChange={(e) => setSelectedTarget(e.target.value)}
                      >
                        <option value="" disabled>
                          Select an enabled target
                        </option>
                        {data.targets
                          .filter((t) => t.enabled && !t.deployment?.active)
                          .map((t) => (
                            <option key={t.id} value={t.id}>
                              {t.name} · {t.tenant}/{t.controller_id}
                            </option>
                          ))}
                      </select>
                    </Field>
                    <Field label="Distribution">
                      <select
                        required
                        value={selectedRelease}
                        onChange={(e) => setSelectedRelease(e.target.value)}
                      >
                        <option value="" disabled>
                          Select a distribution
                        </option>
                        {data.releases.map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.name} {r.version}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Mode">
                      <select name="mode">
                        <option value="forced">
                          Forced · download and install
                        </option>
                        <option value="download_only">
                          Download Only · verify checksum, skip installation
                        </option>
                        <option disabled>Soft · unsupported</option>
                        <option disabled>Time Forced · unsupported</option>
                      </select>
                    </Field>
                    {releaseArtifact && (
                      <div className="assignment-summary">
                        <strong>{releaseArtifact.filename}</strong>
                        <p>
                          {bytes(releaseArtifact.size)} · compatible:{" "}
                          <code>{releaseArtifact.compatible}</code>
                        </p>
                        <small>
                          SHA-256: <code>{releaseArtifact.sha256}</code>
                        </small>
                        <p>Signature status: not verified by server</p>
                      </div>
                    )}
                    <div className="form-grid">
                      <Field label="Type the exact release version">
                        <input
                          name="expected_version"
                          required
                          placeholder={release?.version}
                        />
                      </Field>
                      <Field label="Type the exact compatible string">
                        <input
                          name="expected_compatible"
                          required
                          placeholder={releaseArtifact?.compatible}
                        />
                      </Field>
                    </div>
                    <Field
                      label="Approval and recovery note"
                      hint="Record bundle trust verification, target identity and the available recovery path."
                    >
                      <textarea
                        name="approval_note"
                        minLength={10}
                        maxLength={2048}
                        required
                      />
                    </Field>
                    <label className="checkbox">
                      <input type="checkbox" required />I have verified the
                      intended device, compatible string, version, signature
                      trust and recovery path, and approve this assignment.
                    </label>
                  </>
                )}
                {dialog.kind === "cancel" && (
                  <p>
                    Cancel assignment <strong>#{dialog.deployment!.id}</strong>{" "}
                    before the target discovers it? A discovered action cannot
                    be canceled through this interface.
                  </p>
                )}
                {dialog.kind === "retry" && (
                  <>
                    <div className="warning">
                      This creates a new action linked to failed action #
                      {dialog.deployment!.id}. Delayed feedback for the previous
                      action will not affect this attempt.
                    </div>
                    <p>
                      {targetName(dialog.deployment!.target_id)} ·{" "}
                      {dialog.deployment!.snapshot.distribution_name}{" "}
                      {dialog.deployment!.snapshot.distribution_version}
                    </p>
                    <Field label="Retry approval and recovery note">
                      <textarea
                        name="approval_note"
                        minLength={10}
                        maxLength={2048}
                        required
                      />
                    </Field>
                    <label className="checkbox">
                      <input type="checkbox" required />I rechecked the target,
                      bundle and recovery path and approve this retry.
                    </label>
                  </>
                )}
                {dialog.kind === "user" && (
                  <>
                    <Field label="Username">
                      <input
                        name="username"
                        pattern="[A-Za-z0-9_.-]{1,64}"
                        autoComplete="off"
                        required
                      />
                    </Field>
                    <Field
                      label="Initial password"
                      hint="At least 12 characters. Share privately."
                    >
                      <input
                        name="password"
                        type="password"
                        minLength={12}
                        maxLength={256}
                        autoComplete="new-password"
                        required
                      />
                    </Field>
                    <Field label="Role">
                      <select name="role" defaultValue="viewer">
                        <option value="viewer">
                          Viewer · inspect fleet and releases
                        </option>
                        <option value="operator">
                          Operator · upload and assign releases
                        </option>
                        <option value="admin">
                          Administrator · manage credentials and users
                        </option>
                      </select>
                    </Field>
                  </>
                )}
                {dialog.kind === "toggle-user" && (
                  <p>
                    {dialog.user!.is_active ? "Disable" : "Enable"} account{" "}
                    <strong>{dialog.user!.username}</strong>? Disabling also
                    revokes its active sessions.
                  </p>
                )}
              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  className="secondary"
                  disabled={busy}
                  onClick={close}
                >
                  Cancel
                </button>
                <button
                  className={
                    [
                      "deployment",
                      "retry",
                      "revoke",
                      "delete-target",
                      "purge-target",
                    ].includes(dialog.kind)
                      ? "danger"
                      : "primary"
                  }
                  disabled={busy}
                >
                  {busy
                    ? "Saving…"
                    : dialog.kind === "purge-target"
                      ? "Delete permanently"
                      : dialog.kind === "deployment"
                        ? "Confirm assignment"
                        : dialog.kind === "delete-target"
                          ? "Delete target"
                          : dialog.kind === "firmware"
                            ? "Upload bundle"
                            : dialog.kind === "retry"
                              ? "Confirm retry"
                              : "Confirm"}
                </button>
              </div>
            </form>
          )}
        </Modal>
      )}

      {detail && !dialog && (
        <Modal title={`Deployment #${detail.id}`} close={() => setDetail(null)}>
          <div className="modal-body detail-body">
            <div className="deployment-title">
              <div>
                <h3>
                  {detail.snapshot.distribution_name}{" "}
                  <span>v{detail.snapshot.distribution_version}</span>
                </h3>
                <p>
                  {targetName(detail.target_id)} ·{" "}
                  {detail.mode.replaceAll("_", " ")}
                </p>
              </div>
              <Badge value={detail.internal_status} />
            </div>
            <Progress value={detail.progress} />
            <dl className="detail-facts">
              <div>
                <dt>Assigned</dt>
                <dd>{when(detail.created_at)}</dd>
              </div>
              <div>
                <dt>Completed</dt>
                <dd>
                  {detail.completed_at
                    ? when(detail.completed_at)
                    : "In progress"}
                </dd>
              </div>
              <div>
                <dt>Attempt</dt>
                <dd>
                  {detail.attempt_count}
                  {detail.retry_of ? ` · retry of #${detail.retry_of}` : ""}
                </dd>
              </div>
              <div>
                <dt>Boot confirmation</dt>
                <dd>
                  <Badge value={detail.boot_confirmation} />
                </dd>
              </div>
              <div>
                <dt>Bundle</dt>
                <dd>{detail.snapshot.filename}</dd>
              </div>
              <div>
                <dt>Compatible</dt>
                <dd>{detail.snapshot.compatible}</dd>
              </div>
            </dl>
            {detail.error_message && (
              <div className="error">{detail.error_message}</div>
            )}
            <h3>Deployment timeline</h3>
            <p className="muted">
              Target messages are preserved as reported. Times below use your
              local timezone.
            </p>
            <div className="timeline">
              {timeline.length ? (
                timeline.map((e) => (
                  <article key={e.id}>
                    <span className="timeline-dot" />
                    <div>
                      <header>
                        <strong>{e.kind.replaceAll(".", " ")}</strong>
                        <time>{when(e.received_at)}</time>
                      </header>
                      <p>{e.message || "No detail message"}</p>
                      {e.device_time && (
                        <small>Device timestamp: {e.device_time} UTC</small>
                      )}
                      {Object.keys(e.raw).length > 0 && (
                        <details>
                          <summary>Raw feedback</summary>
                          <pre>{JSON.stringify(e.raw, null, 2)}</pre>
                        </details>
                      )}
                    </div>
                  </article>
                ))
              ) : (
                <p className="muted">Loading events…</p>
              )}
            </div>
            {canWrite && (
              <div className="row-actions">
                {detail.internal_status === "WAITING_FOR_TARGET" &&
                  detail.active && (
                    <button
                      className="secondary"
                      onClick={() =>
                        open({ kind: "cancel", deployment: detail })
                      }
                    >
                      Cancel undiscovered assignment
                    </button>
                  )}
                {!detail.active &&
                  ["INSTALL_FAILED", "REJECTED"].includes(
                    detail.internal_status,
                  ) && (
                    <button
                      className="danger"
                      onClick={() =>
                        open({ kind: "retry", deployment: detail })
                      }
                    >
                      Review retry
                    </button>
                  )}
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
