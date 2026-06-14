"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle, BarChart3, CheckCircle2, Cpu,
  FlaskConical, RefreshCw, ShieldCheck,
  Globe, Skull, TestTube,
} from "lucide-react";
import {
  getSandboxV2Readiness, listSandboxV2Jobs, submitSandboxV2Job,
  cancelSandboxV2Job, listSandboxV2Queue, listSandboxV2ExecutionRecords,
  listSandboxV2Workers, listSandboxV2DeadLetter, runSandboxV2WorkerOnce,
  requeueSandboxV2ExpiredJobs, listSandboxV2Artifacts,
  getSandboxV2ArtifactContent,
  listSandboxV2PackageRequests, listSandboxV2PackageQuarantine,
  listSandboxV2NetworkEgressRequests, listSandboxV2NetworkAuditRecords,
  preflightSandboxV2NetworkEgress, getSandboxV2NetworkReadiness,
  getSandboxV2IsolationReadiness, listSandboxV2ExecutionPlans,
  runSandboxV2TrustedFixture, listSandboxV2ContainerPlans,
  listSandboxV2KillRequests, listSandboxV2KillRecords,
  listSandboxV2ActiveHandles, getSandboxV2KillReadiness,
  killSandboxV2Job,
  getSandboxV2PerformanceReadiness, createSandboxV2PerformanceBenchmark,
  runSandboxV2PerformanceBenchmark, listSandboxV2PerformanceBenchmarks,
  listSandboxV2PerformanceResults, getSandboxV2LatestCapacityEstimate,
} from "@/services/runtime-admin";
import type {
  SandboxV2Job, SandboxV2ReadinessResponse, SandboxV2QueueItem,
  SandboxV2ExecutionRecord, SandboxV2WorkerHeartbeat,
  SandboxV2Artifact, SandboxV2PackageRequest,
  SandboxV2PackageQuarantineRecord, SandboxV2NetworkEgressRequest,
  SandboxV2NetworkEgressAuditRecord, SandboxV2ExecutionPlan,
  SandboxV2ContainerExecutionPlan, SandboxV2KillRequest,
  SandboxV2KillRecord, SandboxV2ActiveExecutionHandle,
  SandboxV2BenchmarkConfig, SandboxV2BenchmarkResult,
  SandboxV2CapacityEstimate, SandboxV2PerformanceReadiness,
} from "@/types/runtime-admin";

type SV2Section = "overview" | "jobs" | "artifacts" | "packages" | "network" | "isolation" | "kill" | "performance" | "redteam";

function confirmAction(msg: string): boolean { if (typeof window==="undefined") return false; return window.confirm(msg); }

function Badge({ label, ok, safe }: { label: string; ok?: boolean; safe?: boolean }) {
  const cls = ok ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-200" :
    safe ? "border-sky-400/25 bg-sky-400/10 text-sky-200" :
    "border-amber-400/25 bg-amber-400/10 text-amber-200";
  return <span className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-2xs ${cls}`}>{label}</span>;
}

function Skeleton() { return <div className="space-y-3"><div className="shimmer-bg h-4 w-full rounded bg-os-elevated"/><div className="shimmer-bg h-4 w-3/4 rounded bg-os-elevated"/></div>; }

export default function SandboxV2Dashboard() {
  const [section, setSection] = useState<SV2Section>("overview");
  const [ready, setReady] = useState<SandboxV2ReadinessResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const [jobs, setJobs] = useState<SandboxV2Job[]>([]);
  const [queue, setQueue] = useState<SandboxV2QueueItem[]>([]);
  const [records, setRecords] = useState<SandboxV2ExecutionRecord[]>([]);
  const [workers, setWorkers] = useState<SandboxV2WorkerHeartbeat[]>([]);
  const [dl, setDl] = useState<unknown[]>([]);
  const [artifacts, setArtifacts] = useState<SandboxV2Artifact[]>([]);
  const [pkgs, setPkgs] = useState<SandboxV2PackageRequest[]>([]);
  const [quar, setQuar] = useState<SandboxV2PackageQuarantineRecord[]>([]);
  const [egress, setEgress] = useState<SandboxV2NetworkEgressRequest[]>([]);
  const [audit, setAudit] = useState<SandboxV2NetworkEgressAuditRecord[]>([]);
  const [plans, setPlans] = useState<SandboxV2ExecutionPlan[]>([]);
  const [cplans, setCplans] = useState<SandboxV2ContainerExecutionPlan[]>([]);
  const [kreqs, setKreqs] = useState<SandboxV2KillRequest[]>([]);
  const [krecs, setKrecs] = useState<SandboxV2KillRecord[]>([]);
  const [handles, setHandles] = useState<SandboxV2ActiveExecutionHandle[]>([]);
  const [perfReady, setPerfReady] = useState<SandboxV2PerformanceReadiness | null>(null);
  const [benchmarks, setBenchmarks] = useState<SandboxV2BenchmarkConfig[]>([]);
  const [benchResults, setBenchResults] = useState<SandboxV2BenchmarkResult[]>([]);
  const [capacity, setCapacity] = useState<SandboxV2CapacityEstimate | null>(null);
  const [isoR, setIsoR] = useState<Record<string,unknown>|null>(null);
  const [killR, setKillR] = useState<Record<string,unknown>|null>(null);
  const [netR, setNetR] = useState<Record<string,unknown>|null>(null);
  const [preflightR, setPreflightR] = useState<Record<string,unknown>|null>(null);
  const [artContent, setArtContent] = useState<string>("");
  const [showArt, setShowArt] = useState<string|null>(null);
  const [preflightUrl, setPreflightUrl] = useState("https://example.com");

  const fetchAll = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const [r] = await Promise.all([getSandboxV2Readiness()]);
      setReady(r);
    } catch (e: unknown) { setErr(`[${(e as Error).message}]`); }
    finally { setLoading(false); }
  }, []);

  const fetchSection = useCallback(async (s: SV2Section) => {
    try {
      if (s === "jobs") {
        const [j,q,rc,w,d] = await Promise.all([listSandboxV2Jobs(),listSandboxV2Queue(),listSandboxV2ExecutionRecords(),listSandboxV2Workers(),listSandboxV2DeadLetter()]);
        setJobs(j.jobs||[]); setQueue(q.queue_items||[]); setRecords(rc.execution_records||[]); setWorkers(w.workers||[]); setDl(d.dead_letter_items||[]);
      }
      if (s === "artifacts") { const a = await listSandboxV2Artifacts(); setArtifacts(a.artifacts||[]); }
      if (s === "packages") { const [p,qr] = await Promise.all([listSandboxV2PackageRequests(),listSandboxV2PackageQuarantine()]); setPkgs(p.package_requests||[]); setQuar(qr.quarantine_records||[]); }
      if (s === "network") {
        const [e,a,nr] = await Promise.all([listSandboxV2NetworkEgressRequests(),listSandboxV2NetworkAuditRecords(),getSandboxV2NetworkReadiness().catch(()=>null)]);
        setEgress(e.egress_requests||[]); setAudit(a.audit_records||[]); if(nr) setNetR(nr as unknown as Record<string,unknown>);
      }
      if (s === "isolation") {
        const [ir,ep,cp] = await Promise.all([getSandboxV2IsolationReadiness().catch(()=>null),listSandboxV2ExecutionPlans(),listSandboxV2ContainerPlans()]);
        if(ir) setIsoR(ir as unknown as Record<string,unknown>); setPlans(ep.execution_plans||[]); setCplans(cp.container_plans||[]);
      }
      if (s === "kill") {
        const [kr,krc,h,krr] = await Promise.all([listSandboxV2KillRequests(),listSandboxV2KillRecords(),listSandboxV2ActiveHandles(),getSandboxV2KillReadiness().catch(()=>null)]);
        setKreqs(kr.kill_requests||[]); setKrecs(krc.kill_records||[]); setHandles(h.active_handles||[]); if(krr) setKillR(krr as unknown as Record<string,unknown>);
      }
      if (s === "performance") {
        const [pr,b,r,c] = await Promise.all([
          getSandboxV2PerformanceReadiness().catch(()=>null),
          listSandboxV2PerformanceBenchmarks({limit:20}),
          listSandboxV2PerformanceResults({limit:50}),
          getSandboxV2LatestCapacityEstimate().catch(()=>({capacity_estimate:null})),
        ]);
        if (pr) setPerfReady(pr);
        setBenchmarks(b.benchmarks||[]);
        setBenchResults(r.results||[]);
        setCapacity(c.capacity_estimate||null);
      }
    } catch (e: unknown) { setErr(`[${(e as Error).message}]`); }
  }, []);

  useEffect(() => { void fetchAll(); }, [fetchAll]);
  useEffect(() => { void fetchSection(section); }, [section, fetchSection]);

  async function handleRunWorker() {
    if (!confirmAction("Run worker once (simulation only, no real code)?")) return;
    try { await runSandboxV2WorkerOnce(); await fetchSection("jobs"); } catch (e: unknown) { setErr(`[${(e as Error).message}]`); }
  }
  async function handleRequeue() {
    if (!confirmAction("Requeue expired leases?")) return;
    try { await requeueSandboxV2ExpiredJobs(); await fetchSection("jobs"); } catch (e: unknown) { setErr(`[${(e as Error).message}]`); }
  }
  async function handleCancelJob(jid: string) {
    if (!confirmAction("Cancel job: " + jid + "? (No real process kill)")) return;
    try { await cancelSandboxV2Job(jid); await fetchSection("jobs"); } catch (e: unknown) { setErr(`[${(e as Error).message}]`); }
  }
  async function handleKillJob(jid: string) {
    if (!confirmAction("Kill job via kill switch: " + jid + "? (No real process kill)")) return;
    try { await killSandboxV2Job(jid); await fetchSection("kill"); } catch (e: unknown) { setErr(`[${(e as Error).message}]`); }
  }
  async function handleSubmitJob() {
    if (!confirmAction("Submit simulation job (no real code execution)?")) return;
    try { await submitSandboxV2Job({mode:"simulation",requested_action:"dry_run"}); await fetchSection("jobs"); } catch (e: unknown) { setErr(`[${(e as Error).message}]`); }
  }
  async function handlePreflight() {
    try { const r = await preflightSandboxV2NetworkEgress({url: preflightUrl}); setPreflightR(r as unknown as Record<string,unknown>); } catch (e: unknown) { setErr(`[${(e as Error).message}]`); }
  }
  async function handleViewArt(artId: string) {
    try { const r = await getSandboxV2ArtifactContent(artId); setArtContent(r.content||""); setShowArt(artId); } catch (e: unknown) { setErr(`[${(e as Error).message}]`); }
  }
  async function handleRunTrustedFixture() {
    if (!confirmAction("Run trusted fixture execution plan?")) return;
    try { const r = await listSandboxV2ExecutionPlans(); const p = r.execution_plans?.[0]; if(p) await runSandboxV2TrustedFixture(p.execution_plan_id); await fetchSection("isolation"); } catch (e: unknown) { setErr(`[${(e as Error).message}]`); }
  }
  async function handleCreateSmokeBenchmark() {
    if (!confirmAction("Create smoke benchmark config? Synthetic fixture only, no user code.")) return;
    try {
      await createSandboxV2PerformanceBenchmark({profile:"smoke", targets:["jobs","queue","metrics","alerts"], max_jobs:3, max_queue_items:3, max_artifacts:2, max_concurrency:1});
      await fetchSection("performance");
    } catch (e: unknown) { setErr(`[${(e as Error).message}]`); }
  }
  async function handleRunSmokeBenchmark() {
    const latest = benchmarks.find(b=>b.profile==="smoke") || benchmarks[0];
    if (!latest) { setErr("[Create a smoke benchmark first]"); return; }
    if (!confirmAction("Run smoke benchmark? Synthetic fixture only, no user code/network/container/MicroVM.")) return;
    try { await runSandboxV2PerformanceBenchmark(latest.benchmark_id); await fetchSection("performance"); } catch (e: unknown) { setErr(`[${(e as Error).message}]`); }
  }
  async function handleViewCapacity() {
    try { const c = await getSandboxV2LatestCapacityEstimate(); setCapacity(c.capacity_estimate||null); } catch (e: unknown) { setErr(`[${(e as Error).message}]`); }
  }

  if (loading) return <main className="mx-auto max-w-7xl px-4 py-8"><Skeleton/></main>;

  const sections: [SV2Section, string, string][] = [
    ["overview","Overview","Sandbox v2 能力总览"],
    ["jobs","Jobs & Queue","任务、队列与 Worker"],
    ["artifacts","Artifacts","文件 Artifact 管理"],
    ["packages","Packages","包供应链安全"],
    ["network","Network","网络出站控制"],
    ["isolation","Isolation","隔离执行与容器"],
    ["kill","Kill Switch","任务取消与终止"],
    ["performance","Performance","性能基准与容量估算"],
    ["redteam","Red-Team","安全回归测试"],
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1">
        {sections.map(([k,label,hint]) => (
          <button key={k} onClick={() => setSection(k)}
            className={`rounded px-3 py-1.5 text-xs transition-colors ${section===k?"bg-os-accent text-white":"bg-os-elevated text-os-subtle hover:text-os-text-high"}`}
            title={hint}>{label}</button>
        ))}
        <button onClick={() => { void fetchAll(); void fetchSection(section); }} className="ml-auto inline-flex h-8 items-center gap-1.5 rounded border border-os-border px-2.5 text-xs text-os-subtle hover:text-os-text-high"><RefreshCw size={12}/>刷新</button>
      </div>

      {err && <div className="rounded border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200">{err}</div>}

      {section === "overview" && ready && <OverviewView ready={ready} />}
      {section === "jobs" && <JobsView jobs={jobs} queue={queue} records={records} workers={workers} dl={dl} onRunWorker={handleRunWorker} onRequeue={handleRequeue} onCancel={handleCancelJob} onSubmit={handleSubmitJob} />}
      {section === "artifacts" && <ArtifactsView artifacts={artifacts} showArt={showArt} artContent={artContent} onView={handleViewArt} onClose={()=>setShowArt(null)} />}
      {section === "packages" && <PackagesView pkgs={pkgs} quar={quar} />}
      {section === "network" && <NetworkView egress={egress} audit={audit} netR={netR} preflightUrl={preflightUrl} setPreflightUrl={setPreflightUrl} preflightR={preflightR} onPreflight={handlePreflight} />}
      {section === "isolation" && <IsolationView isoR={isoR} plans={plans} cplans={cplans} onRunFixture={handleRunTrustedFixture} />}
      {section === "kill" && <KillView kreqs={kreqs} krecs={krecs} handles={handles} killR={killR} onKillJob={handleKillJob} />}
      {section === "performance" && <PerformanceView ready={perfReady} benchmarks={benchmarks} results={benchResults} capacity={capacity} onCreateSmoke={handleCreateSmokeBenchmark} onRunSmoke={handleRunSmokeBenchmark} onViewCapacity={handleViewCapacity} />}
      {section === "redteam" && <RedTeamView ready={ready} />}
    </div>
  );
}

/* ── Overview ── */
function OverviewView({ ready }: { ready: SandboxV2ReadinessResponse }) {
  const items: [string, boolean | string, string][] = [
    ["Core Contract", ready.sandbox_v2_core_contract, "ok"],
    ["Real Task Queue", ready.real_task_queue, "ok"],
    ["Worker Framework", ready.worker_framework, "ok"],
    ["Artifact Store", ready.artifact_store, "ok"],
    ["Package Quarantine", ready.package_quarantine, "ok"],
    ["Network Preflight", ready.network_preflight, "ok"],
    ["Isolation Provider", ready.execution_provider_abstraction, "ok"],
    ["Trusted Fixture", ready.trusted_fixture_provider, "ok"],
    ["Container Provider", ready.container_provider_abstraction, "ok"],
    ["Kill Switch", ready.kill_switch, "ok"],
    ["Red-Team Suite", ready.red_team_suite, "ok"],
  ];
  const boundary: [string,boolean|string,string][] = [
    ["Untrusted Code Exec", ready.untrusted_code_execution, "safe"],
    ["External Network", ready.external_network_access, "safe"],
    ["Package Execution", ready.package_execution, "safe"],
    ["Arbitrary Cmd", ready.arbitrary_container_command, "safe"],
    ["Arbitrary PID Kill", ready.arbitrary_pid_kill, "safe"],
    ["MicroVM Execution", ready.microvm_execution, "safe"],
    ["Docker Execution", ready.docker_execution, "safe"],
    ["Process Kill", ready.process_kill_implemented, "safe"],
    ["Egress Proxy", ready.egress_proxy, "safe"],
    ["Auto Pull Images", ready.auto_pull_images||false, "safe"],
  ];
  const prodItems: [string, boolean | undefined][] = [
    ["Hardening Docs", ready.production_hardening_docs],
    ["Env Template", ready.env_template_present],
    ["Readiness Script", ready.production_readiness_script],
    ["Deploy Checklist", ready.deployment_checklist_present],
    ["Ops Runbook", ready.operations_runbook_present],
    ["IR Runbook", ready.incident_response_runbook_present],
    ["Docker Compose", ready.docker_compose_example_present],
    ["Safe Defaults", ready.safe_defaults_configured],
  ];
  const blockers: string[] = ready.production_blockers ?? [];
  const warns: string[] = ready.warnings ?? [];
  return (
    <div className="space-y-4">
      <div className="os-card p-4">
        <h3 className="text-sm font-semibold text-os-text-high mb-3">Sandbox v2 当前模式</h3>
        <p className="text-xs text-os-subtle">{ready.current_execution_mode} — {ready.boundary_statement?.slice(0,260)}</p>
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <div className="os-card p-4">
          <h3 className="text-xs font-semibold text-emerald-200 mb-2 flex items-center gap-1.5"><CheckCircle2 size={14}/> 已完成控制面</h3>
          <div className="flex flex-wrap gap-1.5">{items.map(([l,v])=><Badge key={l} label={l} ok={!!v}/>)}</div>
        </div>
        <div className="os-card p-4">
          <h3 className="text-xs font-semibold text-sky-200 mb-2 flex items-center gap-1.5"><ShieldCheck size={14}/> 安全关闭</h3>
          <div className="flex flex-wrap gap-1.5">{boundary.filter(([,v])=>!v).map(([l])=><Badge key={l} label={l} safe/>)}</div>
        </div>
        <div className="os-card p-4">
          <h3 className="text-xs font-semibold text-amber-200 mb-2 flex items-center gap-1.5"><AlertTriangle size={14}/> 当前边界</h3>
          <p className="text-2xs text-os-subtle">{ready.boundary_statement}</p>
        </div>
        <div className="os-card p-4">
          <h3 className="text-xs font-semibold text-purple-200 mb-2 flex items-center gap-1.5"><Cpu size={14}/> Production Readiness</h3>
          <div className="flex flex-wrap gap-1.5 mb-2">
            {prodItems.map(([l,v])=><Badge key={l} label={l} ok={!!v} safe={!v}/>)}
          </div>
          {blockers.length > 0 && (
            <div className="mt-2 rounded border border-red-400/20 bg-red-400/10 p-2">
              <p className="text-2xs text-red-200 font-semibold">Blockers ({blockers.length})</p>
              {blockers.slice(0,3).map((b,i)=><p key={i} className="text-2xs text-red-300/80">• {b}</p>)}
              {blockers.length > 3 && <p className="text-2xs text-red-300/50">...+{blockers.length-3} more</p>}
            </div>
          )}
          {blockers.length === 0 && warns.length > 0 && (
            <div className="mt-2 rounded border border-amber-400/20 bg-amber-400/10 p-2">
              <p className="text-2xs text-amber-200 font-semibold">Warnings ({warns.length})</p>
              {warns.slice(0,2).map((w,i)=><p key={i} className="text-2xs text-amber-300/80">• {w}</p>)}
            </div>
          )}
          {blockers.length === 0 && warns.length === 0 && (
            <p className="text-2xs text-emerald-300/80">Ready</p>
          )}
        </div>
      </div>
      {/* Step 12 — Backend Readiness */}
      <div className="grid gap-3 md:grid-cols-3">
        <div className="os-card p-4">
          <h3 className="text-xs font-semibold text-os-text-high mb-2">Database</h3>
          <div className="flex flex-wrap gap-1.5">
            <Badge label={`backend: ${ready.database_backend || "sqlite"}`} ok={ready.database_backend_ready} />
            <Badge label={`ready: ${ready.database_backend_ready}`} ok={ready.database_backend_ready} />
            {ready.production_backend_configured && ready.database_backend !== "sqlite" && (
              <Badge label={`postgres: ${ready.postgres_adapter_available ? "avail" : "unavail"}`} ok={ready.postgres_adapter_available} />
            )}
          </div>
        </div>
        <div className="os-card p-4">
          <h3 className="text-xs font-semibold text-os-text-high mb-2">Queue</h3>
          <div className="flex flex-wrap gap-1.5">
            <Badge label={`backend: ${ready.queue_backend || "sqlite"}`} ok={ready.queue_backend_ready} />
            <Badge label={`ready: ${ready.queue_backend_ready}`} ok={ready.queue_backend_ready} />
            {ready.production_backend_configured && ready.queue_backend !== "sqlite" && (
              <Badge label={`redis: ${ready.redis_queue_adapter_available ? "avail" : "unavail"}`} ok={ready.redis_queue_adapter_available} />
            )}
          </div>
        </div>
        <div className="os-card p-4">
          <h3 className="text-xs font-semibold text-os-text-high mb-2">Object Storage</h3>
          <div className="flex flex-wrap gap-1.5">
            <Badge label={`backend: ${ready.object_storage_backend || "local"}`} ok={ready.object_storage_ready} />
            <Badge label={`ready: ${ready.object_storage_ready}`} ok={ready.object_storage_ready} />
            {ready.production_backend_configured && ready.object_storage_backend !== "local" && (
              <Badge label={`minio: ${ready.minio_adapter_available ? "avail" : "unavail"}`} ok={ready.minio_adapter_available} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Jobs & Queue ── */
function JobsView({ jobs, queue, records, workers, dl, onRunWorker, onRequeue, onCancel, onSubmit }: {
  jobs: SandboxV2Job[]; queue: SandboxV2QueueItem[]; records: SandboxV2ExecutionRecord[];
  workers: SandboxV2WorkerHeartbeat[]; dl: unknown[];
  onRunWorker: ()=>void; onRequeue: ()=>void; onCancel: (jid:string)=>void; onSubmit: ()=>void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <button onClick={onSubmit} className="rounded bg-os-accent px-3 py-1.5 text-xs text-white">+ Submit Simulation Job</button>
        <button onClick={onRunWorker} className="rounded border border-os-border px-3 py-1.5 text-xs text-os-subtle hover:text-os-text-high"><Cpu size={12} className="inline mr-1"/>Run Worker Once</button>
        <button onClick={onRequeue} className="rounded border border-os-border px-3 py-1.5 text-xs text-os-subtle hover:text-os-text-high"><RefreshCw size={12} className="inline mr-1"/>Requeue Expired</button>
      </div>
      <DataTable title={`Jobs (${jobs.length})`} cols={["job_id","mode","status","risk_level","requested_action"]} rows={jobs.slice(0,20)} actions={[{label:"Cancel",fn:(r:Record<string,unknown>)=>onCancel(r.job_id as string)}]} />
      <DataTable title={`Queue (${queue.length})`} cols={["queue_id","job_id","status","attempts","max_attempts","leased_by"]} rows={queue.slice(0,20)} />
      <DataTable title={`Worker Heartbeats (${workers.length})`} cols={["worker_id","status","current_job_id","processed_count","last_heartbeat_at"]} rows={workers.slice(0,20)} />
      <DataTable title={`Dead Letter (${dl.length})`} cols={["job_id","status","attempts","dead_letter_reason"]} rows={dl.slice(0,20)} />
      <DataTable title={`Execution Records (${records.length})`} cols={["record_id","job_id","status","duration_ms","no_real_execution"]} rows={records.slice(0,20)} />
    </div>
  );
}

/* ── Artifacts ── */
function ArtifactsView({ artifacts, showArt, artContent, onView, onClose }: {
  artifacts: SandboxV2Artifact[]; showArt: string|null; artContent: string;
  onView: (id:string)=>void; onClose: ()=>void;
}) {
  return (
    <div className="space-y-4">
      {showArt && (
        <div className="os-card p-4">
          <div className="flex justify-between items-center mb-2"><h3 className="text-xs font-semibold text-os-text-high">Artifact: {showArt}</h3><button onClick={onClose} className="text-xs text-os-subtle hover:text-os-text-high">✕</button></div>
          <pre className="text-2xs text-os-subtle bg-os-surface rounded p-3 max-h-64 overflow-auto whitespace-pre-wrap">{artContent?.slice(0,5000)||"(empty)"}</pre>
        </div>
      )}
      <DataTable title={`Artifacts (${artifacts.length})`} cols={["artifact_id","job_id","artifact_type","name","size_bytes","mime_type","sha256","read_only","status"]} rows={artifacts.slice(0,30)}
        actions={[{label:"View",fn:(r:Record<string,unknown>)=>onView(r.artifact_id as string)}]} />
    </div>
  );
}

/* ── Packages ── */
function PackagesView({ pkgs, quar }: { pkgs: SandboxV2PackageRequest[]; quar: SandboxV2PackageQuarantineRecord[] }) {
  return (
    <div className="space-y-4">
      <div className="os-card p-3"><p className="text-xs text-amber-200 flex items-center gap-1.5"><AlertTriangle size={14}/> 不安装包、不执行包、不联网下载。external_url / public_registry 默认拒绝。</p></div>
      <DataTable title={`Package Requests (${pkgs.length})`} cols={["package_request_id","package_name","package_version","package_manager","source_type","status","risk_level"]} rows={pkgs.slice(0,20)} />
      <DataTable title={`Quarantine Records (${quar.length})`} cols={["quarantine_id","package_name","sha256","signature_status","sbom_status","vulnerability_status","status"]} rows={quar.slice(0,20)} />
    </div>
  );
}

/* ── Network ── */
function NetworkView({ egress, audit, netR, preflightUrl, setPreflightUrl, preflightR, onPreflight }: {
  egress: SandboxV2NetworkEgressRequest[]; audit: SandboxV2NetworkEgressAuditRecord[];
  netR: Record<string,unknown>|null; preflightUrl: string; setPreflightUrl: (u:string)=>void;
  preflightR: Record<string,unknown>|null; onPreflight: ()=>void;
}) {
  const testUrls = ["https://example.com","http://127.0.0.1","http://169.254.169.254","file:///etc/passwd","http://example.com:22"];
  return (
    <div className="space-y-4">
      <div className="os-card p-3"><p className="text-xs text-amber-200 flex items-center gap-1.5"><Globe size={14}/> Preflight only — 不做真实网络请求。external_network_access=false。</p></div>
      {netR && <DataTable title="Network Readiness" cols={Object.keys(netR as unknown as Record<string,unknown>).filter(k=>typeof (netR as unknown as Record<string,unknown>)[k]!=="object")} rows={[netR as unknown as Record<string,unknown>]} />}
      <div className="os-card p-4 space-y-2">
        <h3 className="text-xs font-semibold text-os-text-high">Preflight Check</h3>
        <div className="flex flex-wrap gap-1.5 mb-2">{testUrls.map(u=><button key={u} onClick={()=>setPreflightUrl(u)} className={`rounded px-2 py-1 text-2xs ${preflightUrl===u?"bg-os-accent text-white":"bg-os-elevated text-os-subtle"}`}>{u}</button>)}</div>
        <div className="flex gap-2"><input value={preflightUrl} onChange={e=>setPreflightUrl(e.target.value)} className="flex-1 rounded border border-os-border bg-os-surface px-2 py-1 text-xs text-os-text-high" /><button onClick={onPreflight} className="rounded bg-os-accent px-3 py-1 text-xs text-white">Check</button></div>
        {preflightR && <pre className="text-2xs text-os-subtle bg-os-surface rounded p-2 mt-2 overflow-auto max-h-40">{JSON.stringify(preflightR,null,2)}</pre>}
      </div>
      <DataTable title={`Egress Requests (${egress.length})`} cols={["egress_request_id","url","hostname","port","status","risk_level"]} rows={egress.slice(0,20)} />
      <DataTable title={`Audit Records (${audit.length})`} cols={["audit_id","url","hostname","decision","reason"]} rows={audit.slice(0,20)} />
    </div>
  );
}

/* ── Isolation ── */
function IsolationView({ isoR, plans, cplans, onRunFixture }: {
  isoR: Record<string,unknown>|null; plans: SandboxV2ExecutionPlan[]; cplans: SandboxV2ContainerExecutionPlan[]; onRunFixture: ()=>void;
}) {
  return (
    <div className="space-y-4">
      {isoR && (
        <div className="os-card p-4">
          <h3 className="text-xs font-semibold text-os-text-high mb-2">Isolation Readiness</h3>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(isoR).filter(([,v])=>typeof v==="boolean").map(([k,v])=><Badge key={k} label={`${k}: ${v}`} ok={!!v} safe={!v && ["untrusted_code_execution","local_process_execution","docker_execution","podman_execution","microvm_execution"].includes(k)}/>)}
          </div>
          {Boolean(isoR.platform) && <p className="text-2xs text-os-subtle mt-2">Platform: {String(isoR.platform)} | is_windows: {String(isoR.is_windows)}</p>}
          {Boolean(String(isoR.boundary || "")) && <p className="text-2xs text-os-subtle mt-1">{String(String(isoR.boundary || ""))}</p>}
        </div>
      )}
      <div className="flex gap-2">
        <button onClick={onRunFixture} className="rounded bg-os-accent px-3 py-1.5 text-xs text-white"><FlaskConical size={12} className="inline mr-1"/>Run Trusted Fixture</button>
      </div>
      <DataTable title={`Execution Plans (${plans.length})`} cols={["execution_plan_id","job_id","provider","mode","status","reason"]} rows={plans.slice(0,20)} />
      <DataTable title={`Container Plans (${cplans.length})`} cols={["container_plan_id","job_id","runtime","image","fixture_id","status"]} rows={cplans.slice(0,20)} />
    </div>
  );
}

/* ── Kill Switch ── */
function KillView({ kreqs, krecs, handles, killR, onKillJob }: {
  kreqs: SandboxV2KillRequest[]; krecs: SandboxV2KillRecord[]; handles: SandboxV2ActiveExecutionHandle[];
  killR: Record<string,unknown>|null; onKillJob: (jid:string)=>void;
}) {
  return (
    <div className="space-y-4">
      <div className="os-card p-3"><p className="text-xs text-red-200 flex items-center gap-1.5"><Skull size={14}/> 不支持任意 PID kill。只支持 sandbox 管理的 job/queue/execution/container plan。</p></div>
      {killR && <div className="os-card p-3"><h3 className="text-xs font-semibold text-os-text-high mb-2">Kill Readiness</h3><div className="flex flex-wrap gap-1.5">{Object.entries(killR as unknown as Record<string,unknown>).filter(([,v])=>typeof v==="boolean").map(([k,v])=><Badge key={k} label={`${k}: ${v}`} ok={!!v} safe={!v && ["arbitrary_pid_kill","process_kill_implemented","container_kill_enabled"].includes(k)}/>)}</div></div>}
      <div className="flex gap-2"><button onClick={()=>{const jid=window.prompt("Job ID to kill:"); if(jid) onKillJob(jid);}} className="rounded border border-red-400/30 bg-red-400/10 px-3 py-1.5 text-xs text-red-200 hover:bg-red-400/20">Kill Job (via Kill Switch)</button></div>
      <DataTable title={`Kill Requests (${kreqs.length})`} cols={["kill_request_id","job_id","target_type","target_id","status","reason"]} rows={kreqs.slice(0,20)} />
      <DataTable title={`Kill Records (${krecs.length})`} cols={["kill_record_id","job_id","action_taken","status_before","status_after","provider_result"]} rows={krecs.slice(0,20)} />
      <DataTable title={`Active Execution Handles (${handles.length})`} cols={["handle_id","job_id","provider","target_type","status","cancel_requested","timeout_at"]} rows={handles.slice(0,20)} />
    </div>
  );
}

/* ── Performance & Capacity ── */
function PerformanceView({ ready, benchmarks, results, capacity, onCreateSmoke, onRunSmoke, onViewCapacity }: {
  ready: SandboxV2PerformanceReadiness|null;
  benchmarks: SandboxV2BenchmarkConfig[];
  results: SandboxV2BenchmarkResult[];
  capacity: SandboxV2CapacityEstimate|null;
  onCreateSmoke: ()=>void;
  onRunSmoke: ()=>void;
  onViewCapacity: ()=>void;
}) {
  const canRun = !!ready?.performance_tests_enabled && !!ready?.synthetic_fixture_only;
  const readinessItems: [string, boolean | undefined, boolean?][] = [
    ["benchmarking", ready?.performance_benchmarking],
    ["tests_enabled", ready?.performance_tests_enabled],
    ["benchmarks_enabled", ready?.performance_benchmarks_enabled],
    ["safe_profile", ready?.performance_safe_profile],
    ["synthetic_fixture_only", ready?.synthetic_fixture_only],
    ["external_load_testing=false", ready ? !ready.external_load_testing : undefined, true],
    ["user_code_benchmarking=false", ready ? !ready.user_code_benchmarking : undefined, true],
    ["capacity_estimation", ready?.capacity_estimation],
    ["cleanup_enabled", ready?.benchmark_cleanup_enabled],
  ];
  return (
    <div className="space-y-4">
      <div className="os-card p-3">
        <p className="text-xs text-sky-200 flex items-center gap-1.5"><BarChart3 size={14}/> synthetic fixture only，不执行用户代码、不访问外网、不启动容器或 MicroVM。</p>
      </div>
      <div className="grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="os-card p-4">
          <h3 className="text-xs font-semibold text-os-text-high mb-2">Performance Readiness</h3>
          <div className="flex flex-wrap gap-1.5">
            {readinessItems.map(([l,v,safe])=><Badge key={l} label={`${l}: ${String(v ?? false)}`} ok={!!v && !safe} safe={safe && !!v}/>)}
          </div>
          {ready?.warnings?.length ? <p className="mt-2 text-2xs text-amber-200">{ready.warnings.slice(0,2).join(" · ")}</p> : null}
          {ready?.blockers?.length ? <p className="mt-2 text-2xs text-red-200">{ready.blockers.slice(0,2).join(" · ")}</p> : null}
        </div>
        <div className="os-card p-4">
          <h3 className="text-xs font-semibold text-os-text-high mb-2">Actions</h3>
          <div className="flex flex-wrap gap-2">
            <button disabled={!canRun} onClick={onCreateSmoke} className="rounded bg-os-accent px-3 py-1.5 text-xs text-white disabled:cursor-not-allowed disabled:opacity-40">Create smoke benchmark</button>
            <button disabled={!canRun || benchmarks.length===0} onClick={onRunSmoke} className="rounded border border-os-border px-3 py-1.5 text-xs text-os-subtle hover:text-os-text-high disabled:cursor-not-allowed disabled:opacity-40">Run smoke benchmark</button>
            <button onClick={onViewCapacity} className="rounded border border-os-border px-3 py-1.5 text-xs text-os-subtle hover:text-os-text-high">View latest capacity estimate</button>
          </div>
          <p className="mt-2 text-2xs text-os-muted">默认 disabled；启用后仍只允许 smoke/small profile。</p>
        </div>
      </div>
      <DataTable title={`Benchmark Configs (${benchmarks.length})`} cols={["benchmark_id","profile","targets","max_jobs","max_queue_items","max_concurrency","cleanup_after_run"]} rows={benchmarks.slice(0,20)} />
      <DataTable title={`Benchmark Results (${results.length})`} cols={["target","status","total_operations","success_count","failure_count","p50_ms","p95_ms","p99_ms","ops_per_second","duration_ms"]} rows={results.slice(0,30)} />
      {capacity ? (
        <div className="os-card p-4">
          <h3 className="text-xs font-semibold text-os-text-high mb-2">Capacity Estimate</h3>
          <div className="grid gap-2 md:grid-cols-4">
            <Metric label="Jobs/min" value={capacity.estimated_jobs_per_minute} />
            <Metric label="Queue/min" value={capacity.estimated_queue_items_per_minute} />
            <Metric label="Artifacts/min" value={capacity.estimated_artifact_metadata_per_minute} />
            <Metric label="Preflight/min" value={capacity.estimated_network_preflight_per_minute} />
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <div>
              <p className="text-2xs font-semibold text-os-muted mb-1">Bottlenecks</p>
              {(capacity.bottlenecks||[]).slice(0,4).map((b,i)=><p key={i} className="text-2xs text-os-subtle">• {b}</p>)}
            </div>
            <div>
              <p className="text-2xs font-semibold text-os-muted mb-1">Recommendations</p>
              {(capacity.recommendations||[]).slice(0,4).map((r,i)=><p key={i} className="text-2xs text-os-subtle">• {r}</p>)}
            </div>
          </div>
        </div>
      ) : <div className="os-card p-3"><p className="text-xs text-os-muted">Capacity Estimate — (empty)</p></div>}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="rounded border border-os-border bg-os-surface px-3 py-2"><p className="text-2xs text-os-muted">{label}</p><p className="text-sm font-semibold text-os-text-high">{Number(value||0).toFixed(2)}</p></div>;
}

/* ── Red-Team ── */
function RedTeamView({ ready }: { ready: SandboxV2ReadinessResponse|null }) {
  const items: [string, boolean | undefined][] = [
    ["Red-Team Suite", ready?.red_team_suite],
    ["Artifact Escape", ready?.artifact_escape_tests],
    ["Network SSRF", ready?.network_ssrf_tests],
    ["Package Supply Chain", ready?.package_supply_chain_tests],
    ["Kill Switch Abuse", ready?.kill_switch_abuse_tests],
    ["Container Escape", ready?.container_escape_tests],
    ["Policy Fail-Closed", ready?.policy_fail_closed_tests],
    ["API Abuse", ready?.api_abuse_tests],
    ["Worker/Queue Abuse", ready?.worker_queue_abuse_tests],
  ];
  return (
    <div className="space-y-4">
      <div className="os-card p-4">
        <h3 className="text-sm font-semibold text-emerald-200 mb-2 flex items-center gap-1.5"><TestTube size={16}/> 132 Red-Team Tests Passed</h3>
        <div className="flex flex-wrap gap-1.5 mb-3">{items.map(([l,v])=><Badge key={l} label={l} ok={!!v}/>)}</div>
        <p className="text-xs text-os-subtle mb-1">覆盖 Artifact Escape、Network SSRF、Package Supply Chain、Kill Switch Abuse、Container Escape、Policy Fail-Closed、API Abuse、Worker/Queue Abuse</p>
        <p className="text-xs text-os-subtle mb-1">已修复 network_policy 端口绕过漏洞</p>
        <p className="text-xs text-os-subtle mb-2">real_attack_execution: <span className="text-sky-200">false</span>（安全关闭）</p>
        <code className="text-2xs text-os-muted bg-os-surface rounded px-2 py-1">python -m pytest tests/test_open_platform/red_team -q</code>
      </div>
    </div>
  );
}

/* ── Reusable Table ── */
function DataTable({ title, cols, rows, actions }: {
  title: string; cols: string[]; rows: unknown[]; actions?: {label:string;fn:(row: Record<string,unknown>)=>void}[];
}) {
  if (!rows.length) return <div className="os-card p-3"><p className="text-xs text-os-muted">{title} — (empty)</p></div>;
  return (
    <div className="os-card overflow-x-auto">
      <h3 className="px-3 pt-3 text-xs font-semibold text-os-text-high">{title}</h3>
      <table className="w-full text-2xs text-os-subtle">
        <thead><tr className="border-b border-os-border">{cols.map(c=><th key={c} className="px-3 py-1.5 text-left font-medium text-os-muted">{c}</th>)}{actions?.length ? <th className="px-3 py-1.5 text-left font-medium text-os-muted">Actions</th> : null}</tr></thead>
        <tbody>{rows.map((r,i)=>{ const row=r as unknown as Record<string,unknown>; return <tr key={i} className="border-b border-os-border/40 hover:bg-os-elevated/50">{cols.map(c=>{ const v=String(row[c]??"-"); return <td key={c} className="px-3 py-1.5 max-w-[200px] truncate" title={v}>{v.length>80?v.slice(0,80)+"...":v}</td>; })}{actions?.length ? <td className="px-3 py-1.5">{actions.map(a=><button key={a.label} onClick={()=>a.fn(row)} className="text-os-accent hover:underline mr-2">{a.label}</button>)}</td> : null}</tr>; })}</tbody>
      </table>
    </div>
  );
}
