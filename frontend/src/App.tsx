import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { BookOpen, Clapperboard, Film, Footprints, Library as LibraryIcon, Sparkles, UserRound, Wand2, Wallet } from "lucide-react";
import { Toaster, toast } from "sonner";
import { api, Img, Workspace, workspace } from "./api";
import { useWorkspaces, WorkspaceProvider, WorkspaceSwitcher } from "./workspaces";
import { useAsync } from "./components";
import { money } from "./estimate";
import { CatalogPanel } from "./catalog";
import { ItemRef, Lightbox } from "./lightbox";
import { CommandPalette, PaletteItem } from "./palette";
import { Portal } from "./ui";
import { askNotificationPermission, QueueDock, TasksProvider, useClips } from "./queue";
import Generate from "./pages/Generate";
import EditPage from "./pages/EditPage";
import Library from "./pages/Library";
import Characters from "./pages/Characters";
import Motion from "./pages/Motion";

const Storyboard = lazy(() => import("./pages/Storyboard"));   // dnd-kit hanya dimuat saat dibuka
const Comic = lazy(() => import("./pages/Comic"));   // plan 21

const PAGES = [
  { id: "create", title: "Gambar → Video", icon: Clapperboard },
  { id: "edit", title: "Edit Foto", icon: Wand2 },
  { id: "characters", title: "Karakter", icon: UserRound },
  { id: "library", title: "Library", icon: LibraryIcon },
  { id: "storyboard", title: "Storyboard", icon: Film },
  { id: "comic", title: "Komik", icon: BookOpen },
  { id: "motion", title: "Tiru Gerakan", icon: Footprints },
] as const;
type PageId = (typeof PAGES)[number]["id"];

const readHash = (): PageId => {
  const id = location.hash.replace(/^#\//, "");
  return PAGES.some((p) => p.id === id) ? (id as PageId) : "create";
};

/** Pemilik workspace aktif. AppInner dipasang ulang (key) tiap ganti workspace, jadi semua state/hook di bawahnya bersih
 *  dan respons lama dari workspace sebelumnya tidak bisa menimpa tampilan (plan 07 grill 7). */
export default function App() {
  const [wsId, setWsId] = useState(workspace.id);
  const [list, setList] = useState<Workspace[]>([]);
  const [pending, setPending] = useState<ItemRef | null>(null);   // item yang dibuka setelah pindah (dari dock)
  const refresh = useCallback(() => api.workspaces().then(setList).catch(() => {}), []);
  const switchTo = useCallback((id: string, open?: ItemRef) => {
    workspace.set(id);   // sebelum render: request pertama AppInner sudah membawa header yang benar
    setPending(open ?? null);
    setWsId(id);
    void refresh();
  }, [refresh]);
  useEffect(() => {
    workspace.onMissing = () => { toast("Workspace tidak ditemukan atau sudah diarsip; kembali ke Utama"); switchTo("main"); };
    void refresh();
  }, [switchTo, refresh]);
  return (
    <WorkspaceProvider current={wsId} list={list} switchTo={switchTo} refresh={refresh}>
      <AppInner key={wsId} pending={pending} />
      <Toaster theme="dark" position="bottom-right" offset={{ bottom: 64, right: 16 }} />
    </WorkspaceProvider>
  );
}

function AppInner({ pending }: { pending: ItemRef | null }) {
  const ws = useWorkspaces();
  const [page, setPage] = useState<PageId>(readHash);
  const [selected, setSelected] = useState<string | null>(null);
  const [dockOpen, setDockOpen] = useState(false);
  const [viewer, setViewer] = useState<ItemRef | null>(pending);
  const [focusFilm, setFocusFilm] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [browse, setBrowse] = useState<"video" | "image" | null>(null);
  const chars = useAsync(api.characters, []);
  const health = useAsync(api.health, []);
  const images = useAsync(api.images, []);
  const list: Img[] = images.data ?? [];
  const refreshHealth = useCallback(() => { api.health().then(health.setData).catch(() => {}); }, [health.setData]);
  const refreshImages = useCallback(() => api.images().then(images.setData), [images.setData]);
  // job selesai: biaya aktual masuk dan frame extend baru muncul di daftar gambar
  const clips = useClips(useCallback(() => { refreshHealth(); void refreshImages(); }, [refreshHealth, refreshImages]));

  const go = useCallback((id: PageId) => { location.hash = `/${id}`; }, []);
  const focusPrompt = () => document.querySelector<HTMLTextAreaElement>("textarea[data-prompt]")?.focus();
  const newest = () => {   // klip/gambar terbaru (daftar dari server sudah urut terbaru dulu)
    const c = clips.clips[0], i = list[0];
    if (c && (!i || c.created_at >= i.created_at)) return { type: "clip" as const, id: c.id };
    return i ? { type: "image" as const, id: i.id } : null;
  };
  const paletteItems: PaletteItem[] = [
    ...PAGES.map((p, n) => ({ id: `go-${p.id}`, group: "Pindah halaman", label: p.title, hint: String(n + 1), run: () => go(p.id) })),
    { id: "cat-video", group: "Model", label: "Bandingkan model video + harga", keywords: "katalog harga", run: () => setBrowse("video") },
    { id: "cat-image", group: "Model", label: "Bandingkan model gambar + harga", keywords: "katalog harga", run: () => setBrowse("image") },
    { id: "last", group: "Aksi", label: "Buka aset terakhir", run: () => { const n = newest(); if (n) setViewer(n); else toast("Belum ada aset"); } },
    { id: "film", group: "Aksi", label: "Buat film baru", run: () => { go("storyboard"); setTimeout(() => document.querySelector<HTMLInputElement>(".sb-new input")?.focus(), 600); } },
    { id: "prompt", group: "Aksi", label: "Fokus ke prompt", hint: "/", run: () => setTimeout(focusPrompt, 50) },
    { id: "dock", group: "Aksi", label: "Buka/tutup antrian job", hint: "Q", run: () => setDockOpen((o) => !o) },
    { id: "ws-new", group: "Workspace", label: "Workspace baru…", run: () => window.dispatchEvent(new Event("ws:new")) },
    ...ws.list.filter((w) => w.id !== ws.current).map((w) => ({
      id: `ws-${w.id}`, group: "Workspace", label: `Pindah ke workspace: ${w.name}`, keywords: "workspace proyek", run: () => ws.switchTo(w.id),
    })),
  ];

  useEffect(() => {   // shortcut global; ⌘↵ hanya menekan tombol generate (dialog biaya tetap muncul), tidak pernah melewatinya
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") { e.preventDefault(); setPaletteOpen((o) => !o); return; }
      const modalOpen = !!document.querySelector("[role=dialog]");
      if (mod && e.key === "Enter") {
        const b = document.querySelector<HTMLButtonElement>("[data-generate]");
        if (b && !b.disabled && !modalOpen) { e.preventDefault(); b.click(); }
        return;
      }
      const t = e.target as HTMLElement | null;
      if (mod || e.altKey || modalOpen || t?.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t?.tagName ?? "")) return;
      const n = Number(e.key);
      if (n >= 1 && n <= PAGES.length) go(PAGES[n - 1].id);
      else if (e.key === "/") { e.preventDefault(); focusPrompt(); }
      else if (e.key.toLowerCase() === "q") setDockOpen((o) => !o);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  useEffect(() => {
    const onHash = () => setPage(readHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(refreshHealth, [page, refreshHealth]); // biaya hari ini tetap segar
  useEffect(() => { api.characters().then(chars.setData).catch(() => {}); }, [page, chars.setData]); // karakter baru dari halaman Karakter
  // gambar terpilih yang tidak ada lagi di daftar (mis. DB baru) dianggap tidak ada
  const current = selected && list.some((i) => i.id === selected) ? selected : null;
  /** Tambah klip sebagai adegan baru di episode terakhir (dibuat bila belum ada); episode yang sedang dirender ditolak server dengan pesan jelas. */
  async function addToFilm(clipId: string) {
    try {
      const eps = await api.films();
      const film = eps[eps.length - 1] ?? await api.createFilm("Episode 1");
      await api.addScene(film.id, { clip_id: clipId });
      setFocusFilm(film.id);
      toast.success(`Ditambahkan ke "${film.title}"`, { action: { label: "Buka", onClick: () => { setViewer(null); go("storyboard"); } } });
    } catch (e) { toast.error((e as Error).message); }
  }
  const reloadAll = () => { void clips.reload(); void refreshImages(); refreshHealth(); };

  const addImage = (img: Img) => images.setData([img, ...list.filter((i) => i.id !== img.id)]);
  const h = health.data;

  return (
    <TasksProvider>
      <div className="shell">
        <nav className="sidebar" aria-label="Navigasi utama">
          <div className="logo" aria-hidden><Sparkles size={20} /></div>
          {PAGES.map(({ id, title, icon: Icon }) => (
            <button key={id} className={`nav-btn ${id === page ? "active" : ""}`} onClick={() => go(id)}
              aria-label={title} aria-current={id === page ? "page" : undefined}>
              <Icon size={20} /><span className="tip">{title}</span>
            </button>
          ))}
          <div className="spacer" />
        </nav>
        <div className="main">
          <header className="topbar">
            <WorkspaceSwitcher />
            <h1>{PAGES.find((p) => p.id === page)!.title}</h1>
            <span className="grow" />
            {h && (
              <span className={`chip ${h.spent_today >= h.daily_budget * 0.8 ? "warn" : ""}`} title="Biaya terpakai/terpesan hari ini, semua workspace">
                <Wallet size={14} /> <b>{money(h.spent_today)}</b> / {money(h.daily_budget)} <span className="hide-sm">hari ini · semua workspace</span>
              </span>
            )}
          </header>
          {h && !h.api_key && <p className="banner">OPENROUTER_API_KEY belum diatur di server.</p>}
          {h && !h.ffmpeg && <p className="banner">ffmpeg/ffprobe tidak ditemukan; extend dan gabung klip tidak akan jalan.</p>}
          <main className="page">
            {page === "create" && <Generate images={list} selected={current} setSelected={setSelected} addImage={addImage}
              onCreated={() => { void clips.reload(); refreshHealth(); setDockOpen(true); askNotificationPermission(); toast("Video dikirim ke antrian"); }} />}
            {page === "edit" && <EditPage images={list} selected={current} setSelected={setSelected}
              addImage={addImage} refresh={() => { void refreshImages(); refreshHealth(); }} toVideo={(id) => { setSelected(id); go("create"); }} />}
            {page === "characters" && <Characters images={list} selected={current} setSelected={setSelected}
              addImage={addImage} onOpen={setViewer} refreshImages={() => { void refreshImages(); refreshHealth(); }} />}
            {page === "library" && <Library images={list} clips={clips.clips} characters={chars.data ?? []}
              onOpen={setViewer} onCharacters={() => go("characters")}
              reload={() => { reloadAll(); void api.characters().then(chars.setData).catch(() => {}); }} />}
            {page === "storyboard" && <Suspense fallback={<p className="muted" style={{ padding: 18 }}>Memuat storyboard…</p>}>
              <Storyboard clips={clips.clips} images={list} characters={chars.data ?? []} addImage={addImage} focusFilm={focusFilm}
                reloadCharacters={() => { void api.characters().then(chars.setData).catch(() => {}); }}
                onGenerated={() => { void clips.reload(); void refreshImages(); refreshHealth(); askNotificationPermission(); }} /></Suspense>}
            {page === "comic" && <Suspense fallback={<p className="muted" style={{ padding: 18 }}>Memuat komik…</p>}>
              <Comic characters={chars.data ?? []} onGenerated={() => { void refreshImages(); refreshHealth(); }} /></Suspense>}
            {page === "motion" && <Motion clips={clips.clips} images={list} characters={chars.data ?? []} addImage={addImage}
              publicMedia={!!h?.public_media} maxReference={h?.max_reference_seconds ?? 10}
              onCreated={() => { void clips.reload(); void refreshImages(); refreshHealth(); setDockOpen(true); askNotificationPermission(); }} />}
          </main>
        </div>
        {viewer && <Lightbox item={viewer} images={list} clips={clips.clips} characters={chars.data ?? []}
          onOpen={setViewer} onClose={() => setViewer(null)} reload={reloadAll} onAddToFilm={addToFilm}
          onEdit={(id) => { setSelected(id); setViewer(null); go("edit"); }}
          onToVideo={(id) => { setSelected(id); setViewer(null); go("create"); }} />}
        <CommandPalette open={paletteOpen} setOpen={setPaletteOpen} items={paletteItems} />
        {browse && <Portal><CatalogPanel kind={browse} onClose={() => setBrowse(null)} /></Portal>}
        <QueueDock jobs={clips.jobs} open={dockOpen} setOpen={setDockOpen}
          onOpenClip={(job) => (job.workspace_id === ws.current ? setViewer({ type: "clip", id: job.id })
            : ws.switchTo(job.workspace_id!, { type: "clip", id: job.id }))} />
      </div>
    </TasksProvider>
  );
}
