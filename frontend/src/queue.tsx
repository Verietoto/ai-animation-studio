import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, Clip, workspace, friendlyError } from "./api";
import { money } from "./estimate";

export const ACTIVE = ["submitted", "in_progress"];

const STATUS_TEXT: Record<Clip["status"], string> = {
  submitted: "dikirim", in_progress: "diproses", completed: "selesai", failed: "gagal", failed_download: "gagal unduh",
};

/** Notifikasi browser hanya bila tab tidak terlihat dan izin sudah diberikan; toast tetap jalur utama. */
function notify(title: string, body: string) {
  try {
    if (document.hidden && "Notification" in window && Notification.permission === "granted") new Notification(title, { body });
  } catch { /* notifikasi tidak tersedia */ }
}
export function askNotificationPermission() {
  try { if ("Notification" in window && Notification.permission === "default") void Notification.requestPermission(); } catch { /* abaikan */ }
}

/** Satu-satunya pemilik daftar klip + polling (4 dtk, hanya bila ada job aktif). Perubahan status memicu toast. */
export function useClips(onSettled: () => void) {
  const [clips, setClips] = useState<Clip[]>([]);   // klip workspace aktif (Library, Storyboard)
  const [jobs, setJobs] = useState<Clip[]>([]);     // job aktif + terbaru dari SEMUA workspace (dock, toast)
  const [error, setError] = useState<string | null>(null);
  const prev = useRef<Map<string, Clip["status"]> | null>(null);
  const settled = useRef(onSettled); settled.current = onSettled;

  const reload = useCallback(() => Promise.all([api.clips(), api.jobs()]).then(([list, jobList]) => {
    setError(null);
    const before = prev.current;
    if (before) {   // bandingkan dengan status sebelumnya (job bisa loncat submitted -> completed di antara dua polling)
      let changed = false;
      for (const c of jobList) {
        const was = before.get(c.id);
        if (was && ACTIVE.includes(was) && !ACTIVE.includes(c.status)) {
          changed = true;
          const where = c.workspace_id !== workspace.id ? `[${c.workspace_name}] ` : "";   // job dari workspace lain diberi label
          const name = `${where}${c.prompt.slice(0, 48)}`;
          if (c.status === "completed") { toast.success(`Video selesai: ${name}`); notify("Video selesai", name); }
          else { toast.error(`Video ${STATUS_TEXT[c.status]}: ${name}`, { description: friendlyError(c.error) ?? undefined }); notify("Video gagal", name); }
        }
      }
      if (changed) settled.current();
    }
    prev.current = new Map(jobList.map((c) => [c.id, c.status]));
    setClips(list); setJobs(jobList);
  }).catch((e: Error) => setError(e.message)), []);

  useEffect(() => { void reload(); }, [reload]);
  const anyActive = jobs.some((c) => ACTIVE.includes(c.status));
  useEffect(() => {
    if (!anyActive) return;
    const t = setInterval(() => void reload(), 4000);
    return () => clearInterval(t);
  }, [anyActive, reload]);
  return { clips, jobs, error, reload };
}

// ---- tugas sinkron (edit foto, character sheet): tampil di dock selama request berjalan ----
interface Task { id: number; label: string; startedAt: number }
type Track = <T>(label: string, fn: () => Promise<T>) => Promise<T>;
const TasksCtx = createContext<{ tasks: Task[]; track: Track }>({ tasks: [], track: (_l, fn) => fn() });
export const useTrack = () => useContext(TasksCtx).track;

export function TasksProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const seq = useRef(0);
  const track: Track = useCallback(async (label, fn) => {
    const id = ++seq.current;
    setTasks((t) => [...t, { id, label, startedAt: Date.now() }]);
    try { return await fn(); } finally { setTasks((t) => t.filter((x) => x.id !== id)); }
  }, []);
  return <TasksCtx.Provider value={{ tasks, track }}>{children}</TasksCtx.Provider>;
}

const elapsed = (from: number) => {
  const s = Math.max(0, Math.floor((Date.now() - from) / 1000));
  return s < 60 ? `${s}d` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}d`;
};

export function QueueDock({ jobs: clips, open, setOpen, onOpenClip }: {
  jobs: Clip[]; open: boolean; setOpen: (v: boolean) => void; onOpenClip: (job: Clip) => void;
}) {
  const { tasks } = useContext(TasksCtx);
  const [, tick] = useState(0);
  const active = clips.filter((c) => ACTIVE.includes(c.status));
  const busy = active.length + tasks.length;
  useEffect(() => {   // detik berjalan hanya dihitung ulang saat ada yang aktif
    if (!busy) return;
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [busy]);
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {   // tombol "Pengaturan" mobile perlu tahu tinggi dock
    const el = ref.current; if (!el) return;
    const ro = new ResizeObserver(() => document.documentElement.style.setProperty("--dock-h", `${el.offsetHeight}px`));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const recent = clips.filter((c) => !ACTIVE.includes(c.status)).slice(0, 10);
  const last = recent[0];

  return (
    <section ref={ref} className={`dock ${open ? "open" : ""}`} aria-label="Antrian job">
      <button className="dock-bar" onClick={() => setOpen(!open)} aria-expanded={open}>
        {busy ? <Loader2 size={15} className="spin" style={{ color: "var(--a2)" }} /> : <CheckCircle2 size={15} style={{ color: "var(--ok)" }} />}
        <strong>{busy ? `${busy} job berjalan` : "Antrian kosong"}</strong>
        {!busy && last && <span className="muted">terakhir: {STATUS_TEXT[last.status]} · {last.prompt.slice(0, 40)}</span>}
        <span className="grow" />
        <span className="kbd hide-sm">Q</span>
        {open ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
      </button>
      {open && (
        <ul className="dock-list">
          {tasks.map((t) => (
            <li key={`t${t.id}`} className="job">
              <span className="job-thumb"><Loader2 size={16} className="spin" /></span>
              <span className="job-main"><strong>{t.label}</strong><span className="muted">sedang diproses</span></span>
              <span className="mono muted">{elapsed(t.startedAt)}</span>
              <span className="bar" aria-hidden />
            </li>
          ))}
          {[...active, ...recent].map((c) => {
            const running = ACTIVE.includes(c.status);
            return (
              <li key={c.id} className="job" onClick={() => onOpenClip(c)} role="button" tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter") onOpenClip(c); }}>
                <span className="job-thumb">{c.source_image_id ? <img src={api.imageUrl(c.source_image_id)} alt="" onError={(e) => { e.currentTarget.style.display = "none"; }} /> : null}</span>
                <span className="job-main">
                  <strong className="clamp1">{c.prompt}</strong>
                  <span className="muted">
                    {c.workspace_id !== workspace.id && <span className="pill" style={{ marginRight: 6 }}>{c.workspace_name}</span>}
                    {c.model}{c.chain_depth > 0 ? ` · extend #${c.chain_depth}` : ""}
                  </span>
                </span>
                <span className={`pill ${c.status}`}>
                  {running ? <Loader2 size={11} className="spin" /> : c.status === "completed" ? null : <AlertTriangle size={11} />}
                  {STATUS_TEXT[c.status]}
                </span>
                <span className="mono muted">{running ? elapsed(Date.parse(c.created_at)) : c.cost != null ? money(c.cost) : c.estimated_cost != null ? `~${money(c.estimated_cost)}` : ""}</span>
                {running && <span className="bar" aria-hidden />}
              </li>
            );
          })}
          {busy === 0 && recent.length === 0 && <li className="muted" style={{ padding: 12 }}>Belum ada job.</li>}
        </ul>
      )}
    </section>
  );
}
