import { createContext, FormEvent, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Archive, ArchiveRestore, Boxes, ChevronDown, Loader2, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, Workspace } from "./api";
import type { ItemRef } from "./lightbox";
import { Portal } from "./ui";

interface Ctx {
  current: string; list: Workspace[];
  switchTo: (id: string, open?: ItemRef) => void;
  refresh: () => Promise<void>;
  /** Buka dialog "Salin ke workspace…" untuk gambar/karakter di workspace aktif. */
  askCopy: (imageIds: string[], characterIds: string[]) => void;
}
const WorkspaceCtx = createContext<Ctx>({ current: "main", list: [], switchTo: () => {}, refresh: async () => {}, askCopy: () => {} });
export const useWorkspaces = () => useContext(WorkspaceCtx);

const countText = (w: Workspace) =>
  `${w.counts.images} gambar · ${w.counts.clips} video · ${w.counts.characters} karakter · ${w.counts.films} film`;

function CopyDialog({ images, characters, onClose }: { images: string[]; characters: string[]; onClose: () => void }) {
  const { current, list, switchTo, refresh } = useWorkspaces();
  const targets = list.filter((w) => w.id !== current);
  const [target, setTarget] = useState(targets[0]?.id ?? "");
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = !!newName.trim() || !!target;

  async function confirm() {
    setBusy(true); setError(null);
    try {
      let tid = target, tname = targets.find((w) => w.id === target)?.name ?? "";
      if (newName.trim()) { const w = await api.createWorkspace(newName.trim()); tid = w.id; tname = w.name; }
      const r = await api.copyTo(tid, { image_ids: images, character_ids: characters });
      await refresh();
      toast.success(`Disalin ke "${tname}": ${r.images.length} gambar${r.characters.length ? `, ${r.characters.length} karakter` : ""}`,
        { action: { label: "Buka", onClick: () => switchTo(tid) } });
      onClose();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <Portal>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Salin ke workspace"
        onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}
        onKeyDown={(e) => { if (e.key === "Escape" && !busy) onClose(); }}>
        <div className="modal-box">
          <h3>Salin ke workspace</h3>
          <p className="muted">
            {images.length > 0 && `${images.length} gambar`}{images.length > 0 && characters.length > 0 && ", "}
            {characters.length > 0 && `${characters.length} karakter (beserta gambar sheet-nya)`}.
            Yang asli tetap di sini; salinan tidak menambah biaya.
          </p>
          {targets.length > 0 && (
            <label className="field" style={{ marginTop: 10 }}>Workspace tujuan
              <select value={target} onChange={(e) => setTarget(e.target.value)} disabled={!!newName.trim()}>
                {targets.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
            </label>
          )}
          <label className="field" style={{ marginTop: 10 }}>{targets.length > 0 ? "…atau buat workspace baru" : "Buat workspace tujuan"}
            <input value={newName} maxLength={60} onChange={(e) => setNewName(e.target.value)} placeholder="Nama workspace baru" autoFocus={targets.length === 0} />
          </label>
          {error && <p className="error" style={{ marginTop: 8 }}>{error}</p>}
          <div className="actions">
            <button className="btn" onClick={onClose} disabled={busy}>Batal</button>
            <button className="btn primary" onClick={confirm} disabled={busy || !ready}>
              {busy ? <><Loader2 size={15} className="spin" /> Menyalin…</> : "Salin"}
            </button>
          </div>
        </div>
      </div>
    </Portal>
  );
}

export function WorkspaceProvider({ current, list, switchTo, refresh, children }: Omit<Ctx, "askCopy"> & { children: ReactNode }) {
  const [copy, setCopy] = useState<{ images: string[]; characters: string[] } | null>(null);
  const askCopy = useCallback((images: string[], characters: string[]) => setCopy({ images, characters }), []);
  return (
    <WorkspaceCtx.Provider value={{ current, list, switchTo, refresh, askCopy }}>
      {children}
      {copy && <CopyDialog images={copy.images} characters={copy.characters} onClose={() => setCopy(null)} />}
    </WorkspaceCtx.Provider>
  );
}

/** Hapus permanen: ringkasan isi + konfirmasi dengan mengetik nama workspace (tak bisa dibatalkan). */
function DeleteDialog({ ws, onClose, onDone }: { ws: Workspace; onClose: () => void; onDone: () => void }) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const c = ws.counts;
  async function confirm() {
    setBusy(true); setError(null);
    try {
      await api.deleteWorkspace(ws.id);
      toast.success(`Workspace "${ws.name}" dihapus`);
      onDone(); onClose();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <Portal>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Hapus workspace permanen"
        onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}
        onKeyDown={(e) => { if (e.key === "Escape" && !busy) onClose(); }}>
        <div className="modal-box">
          <h3>Hapus "{ws.name}" permanen?</h3>
          <p className="muted">
            Dihapus: <strong>{c.images} gambar, {c.clips} video, {c.characters} karakter, {c.films} film</strong> beserta filenya.
            Tidak bisa dibatalkan. Catatan biaya tetap tersimpan, jadi "biaya hari ini" tidak berubah.
          </p>
          <label className="field" style={{ marginTop: 12 }}>Ketik <b>{ws.name}</b> untuk mengonfirmasi
            <input autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} aria-label="Nama workspace untuk konfirmasi" />
          </label>
          {error && <p className="error" style={{ marginTop: 8 }}>{error}</p>}
          <div className="actions">
            <button className="btn" onClick={onClose} disabled={busy}>Batal</button>
            <button className="btn danger-solid" onClick={confirm} disabled={busy || typed !== ws.name}>
              {busy ? <><Loader2 size={15} className="spin" /> Menghapus…</> : "Hapus permanen"}
            </button>
          </div>
        </div>
      </div>
    </Portal>
  );
}

export function WorkspaceSwitcher() {
  const { current, list, switchTo, refresh } = useWorkspaces();
  const [archived, setArchived] = useState<Workspace[]>([]);
  const [showArchive, setShowArchive] = useState(false);
  const [deleting, setDeleting] = useState<Workspace | null>(null);
  const loadArchive = useCallback(() => api.workspaces(true).then((l) => setArchived(l.filter((w) => w.archived))).catch(() => {}), []);
  const [open, setOpen] = useState(false);
  useEffect(() => { if (open) void loadArchive(); }, [open, loadArchive]);
  const [name, setName] = useState("");
  const [renaming, setRenaming] = useState<string | null>(null);
  const [rename, setRename] = useState("");
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const newInput = useRef<HTMLInputElement>(null);
  const cur = list.find((w) => w.id === current);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); setRenaming(null); } };
    window.addEventListener("mousedown", onDown); window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("mousedown", onDown); window.removeEventListener("keydown", onKey); };
  }, [open]);
  useEffect(() => {   // command palette: "Workspace baru…"
    const onNew = () => { setOpen(true); setTimeout(() => newInput.current?.focus(), 30); };
    window.addEventListener("ws:new", onNew);
    return () => window.removeEventListener("ws:new", onNew);
  }, []);

  async function guard(fn: () => Promise<void>) {
    setError(null);
    try { await fn(); } catch (e) { setError((e as Error).message); }
  }
  const create = (e: FormEvent) => {
    e.preventDefault();
    void guard(async () => {
      const w = await api.createWorkspace(name.trim());
      setName(""); setOpen(false); await refresh(); switchTo(w.id);
    });
  };

  return (
    <div className="ws" ref={box}>
      <button className="btn ws-btn" onClick={() => setOpen(!open)} aria-haspopup="menu" aria-expanded={open} title="Ganti workspace">
        <Boxes size={16} /> <span className="ws-name">{cur?.name ?? "Utama"}</span> <ChevronDown size={14} />
      </button>
      {open && (
        <div className="ws-menu" role="menu">
          {list.map((w) => (
            <div key={w.id} className={`ws-item ${w.id === current ? "on" : ""}`}>
              {renaming === w.id ? (
                <input autoFocus value={rename} maxLength={60} aria-label="Nama baru"
                  onChange={(e) => setRename(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void guard(async () => { await api.renameWorkspace(w.id, rename.trim()); setRenaming(null); await refresh(); });
                    if (e.key === "Escape") { e.stopPropagation(); setRenaming(null); }
                  }} />
              ) : (
                <button role="menuitem" className="ws-pick" onClick={() => { if (w.id !== current) switchTo(w.id); setOpen(false); }}>
                  <strong>{w.name}</strong><span className="muted">{countText(w)}</span>
                </button>
              )}
              <button className="btn ghost sm" aria-label={`Ganti nama ${w.name}`} onClick={() => { setRenaming(w.id); setRename(w.name); }}><Pencil size={13} /></button>
              {w.id !== "main" && w.id !== current && (
                <button className="btn ghost sm" aria-label={`Arsipkan ${w.name}`} title="Arsipkan (sembunyikan; data tetap ada)"
                  onClick={() => void guard(async () => { await api.archiveWorkspace(w.id); await refresh(); await loadArchive(); })}><Archive size={13} /></button>
              )}
            </div>
          ))}
          <form className="ws-new" onSubmit={create}>
            <input ref={newInput} value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="Workspace baru…" aria-label="Nama workspace baru" />
            <button className="btn primary sm" disabled={!name.trim()}>Buat</button>
          </form>
          {error && <p className="error">{error}</p>}
          {archived.length > 0 && (
            <div className="ws-archive">
              <button className="btn ghost sm" aria-expanded={showArchive} onClick={() => setShowArchive(!showArchive)}>
                <ChevronDown size={13} style={{ transform: showArchive ? "none" : "rotate(-90deg)" }} /> Arsip ({archived.length})
              </button>
              {showArchive && archived.map((w) => (
                <div key={w.id} className="ws-item archived">
                  <span className="ws-pick" style={{ cursor: "default" }}><strong>{w.name}</strong><span className="muted">{countText(w)}</span></span>
                  <button className="btn sm" onClick={() => void guard(async () => { await api.restoreWorkspace(w.id); await refresh(); await loadArchive(); })}>
                    <ArchiveRestore size={13} /> Pulihkan</button>
                  <button className="btn sm danger ws-del" onClick={() => { setDeleting(w); setOpen(false); }}>
                    <Trash2 size={13} /> Hapus…</button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {deleting && <DeleteDialog ws={deleting} onClose={() => setDeleting(null)} onDone={() => { void refresh(); void loadArchive(); }} />}
    </div>
  );
}
