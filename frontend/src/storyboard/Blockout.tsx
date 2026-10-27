// Editor blockout 3D + previs bergerak (plan 14; versi 2 di plan 17). Diuji manual oleh user; logika data ada di blockoutMath.ts.
// Susunan yang ditampilkan adalah hasil `POST /scenes/{id}/blockout/resolve` (pemecah tata letak di backend): koordinat objek
// dihitung server dari relasi (di atas, menempel dinding, dekat), jadi editor tidak menghitung tabrakan sendiri.
import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Bot, Film, Loader2, Pause, Play, Save, Trash2, Undo2, X } from "lucide-react";
import { toast } from "sonner";
import { api, BlockoutResolved, EstimateRequest, Scene } from "../api";
import { EstimateLine, useConfirmedRun, useEstimate } from "../estimate";
import { Portal } from "../ui";
import { TextModelPicker, useTextModel } from "../textmodel";
import {
  ActorKey, alignToCast, BODIES, bodyDef, CamKey, clampJoint, defaultLayout, DEFAULT_DURATION, Environment, fovFor, isShape, jointLabel, Layout, Look, MAX_DURATION,
  MAX_PROPS, normalizeLayout, posesOf, poseLabel, Prop, ratioOf, removeKeyAt, sampleActor, sampleCamera, upsertKey, Vec3, VOCAB, Wall, withPlacement,
} from "./blockoutMath";
import { ACTOR_COLORS, BlockoutWorld, configureRenderer, createWorld, WorldState } from "./blockoutScene";

type Sel = { kind: "camera" } | { kind: "actor"; id: string } | { kind: "prop"; index: number } | { kind: "env" };
type Mode = "at" | "on" | "against" | "near" | "pos";
const r2 = (n: number) => Math.round(n * 100) / 100;
const WALL_LABEL: Record<Wall, string> = { north: "Utara (belakang)", south: "Selatan (depan)", east: "Timur (kanan)", west: "Barat (kiri)" };
const modeOf = (p: Prop): Mode => (p.pos ? "pos" : p.on ? "on" : p.against ? "against" : p.near ? "near" : "at");
const EMPTY_STATE: WorldState = { props: [], environment: {}, bounds: [14, 12] };

function Num({ label, value, onChange, step = 0.1 }: { label: string; value: number; onChange: (v: number) => void; step?: number }) {
  return (
    <label className="field bo-num">{label}
      <input type="number" step={step} value={r2(value)}
        onChange={(e) => { const v = e.target.valueAsNumber; if (Number.isFinite(v)) onChange(v); }} /></label>
  );
}
const Vec = ({ label, v, onChange, step }: { label: string; v: Vec3; onChange: (v: Vec3) => void; step?: number }) => (
  <div className="bo-vec"><span className="muted">{label}</span>
    {(["x", "y", "z"] as const).map((n, i) => <Num key={n} label={n} value={v[i]} step={step} onChange={(x) => onChange(v.map((o, k) => (k === i ? x : o)) as Vec3)} />)}</div>
);
const propLabel = (p: Prop) => p.label || VOCAB.prefabs[p.type]?.label || p.type;

export default function Blockout({ scene, aspect, onClose, onSaved }: { scene: Scene; aspect: string; onClose: () => void; onSaved: () => void }) {
  const ratio = ratioOf(aspect);
  const cast = scene.cast;
  const names = useMemo(() => Object.fromEntries(cast.map((c) => [c.character_id, c.character_name])), [cast]);
  const initial = useMemo(() => scene.blockout ? alignToCast(normalizeLayout(scene.blockout), cast)
    : defaultLayout(cast, scene.planned_seconds ?? DEFAULT_DURATION, scene.camera), []);   // eslint-disable-line react-hooks/exhaustive-deps
  const [layout, setLayout] = useState<Layout>(initial);
  const [saved, setSaved] = useState(() => JSON.stringify(scene.blockout ? initial : null));
  const [prior, setPrior] = useState<Layout | null>(null);   // susunan sebelum draf AI, untuk "kembalikan"
  const [resolved, setResolved] = useState<BlockoutResolved | null>(null);
  const [resolveError, setResolveError] = useState<string | null>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [view, setView] = useState<"free" | "camera">("free");
  const [sel, setSel] = useState<Sel>({ kind: "camera" });
  const [joint, setJoint] = useState("r_shoulder");
  const [busy, setBusy] = useState<string | null>(null);
  const layoutKey = useMemo(() => JSON.stringify(layout), [layout]);
  const dirty = layoutKey !== saved;
  const autoFrame = useRef(!scene.blockout);   // susunan baru/AI: kamera boleh disesuaikan otomatis agar semua tokoh masuk bingkai

  // ---- susunan siap render dari server (pemecah tata letak), dengan jeda setelah tiap perubahan ----
  useEffect(() => {
    let alive = true;
    const h = setTimeout(() => {
      api.resolveBlockout(scene.id, layout).then((r) => {
        if (!alive) return;
        setResolved(r); setResolveError(null);
        if (autoFrame.current) {
          autoFrame.current = false;
          if (JSON.stringify(r.layout.camera) !== JSON.stringify(layout.camera)) setLayout((l) => ({ ...l, camera: r.layout.camera }));
        }
      }).catch((e: Error) => alive && setResolveError(e.message));
    }, 300);
    return () => { alive = false; clearTimeout(h); };
  }, [layoutKey]);   // eslint-disable-line react-hooks/exhaustive-deps
  const state: WorldState = resolved ? { props: resolved.props, environment: resolved.environment, bounds: resolved.bounds }
    : { ...EMPTY_STATE, environment: layout.environment };
  const looks: Record<string, Look> = resolved?.looks ?? {};

  // ---- three.js: dibuat sekali; loop membaca state lewat ref ----
  const box = useRef<HTMLDivElement>(null);
  const live = useRef({ layout, t, playing, view, recording: false, names, state, looks });
  live.current = { ...live.current, layout, t, playing, view, names, state, looks };
  const world = useRef<BlockoutWorld | null>(null);

  useEffect(() => {
    const el = box.current!;
    let gl: THREE.WebGLRenderer;
    try { gl = new THREE.WebGLRenderer({ antialias: true }); } catch { toast.error("WebGL tidak tersedia di browser ini"); return; }
    gl.setPixelRatio(Math.min(devicePixelRatio, 2));
    configureRenderer(gl);
    el.appendChild(gl.domElement);
    gl.domElement.style.cssText = "width:100%;height:100%;display:block";
    const w = createWorld(); world.current = w;
    const free = new THREE.PerspectiveCamera(50, ratio, 0.1, 500); free.position.set(5, 4, 8);
    const shot = new THREE.PerspectiveCamera(35, ratio, 0.1, 500);
    const helper = new THREE.CameraHelper(shot); w.scene.add(helper);
    const orbit = new OrbitControls(free, gl.domElement); orbit.target.set(0, 1, 0); orbit.update();
    const fit = () => { const { clientWidth: cw, clientHeight: ch } = el; if (cw && ch) { gl.setSize(cw, ch, false); free.aspect = shot.aspect = cw / ch; free.updateProjectionMatrix(); } };
    const ro = new ResizeObserver(fit); ro.observe(el); fit();
    let last = performance.now(), raf = 0;
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const s = live.current;
      if (s.recording) { last = now; return; }   // saat merekam, render dipegang perekam (satu set manekin dipakai bersama)
      if (s.playing) {
        const next = s.t + (now - last) / 1000;
        s.t = next >= s.layout.duration ? 0 : next;
        setT(s.t);
      }
      last = now;
      w.sync(s.state, s.layout, s.names, s.looks); w.poseAt(s.layout, s.t);
      const c = sampleCamera(s.layout, s.t);
      shot.position.set(...c.pos); shot.lookAt(new THREE.Vector3(...c.target)); shot.fov = fovFor(c.mm, shot.aspect); shot.updateProjectionMatrix(); shot.updateMatrixWorld();
      helper.visible = s.view === "free"; helper.update();
      gl.render(w.scene, s.view === "camera" ? shot : free);
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); orbit.dispose(); w.dispose(); gl.dispose(); gl.domElement.remove(); world.current = null; };
  }, [ratio]);

  // ---- edit: tiap perubahan menulis key di waktu sekarang (auto-key) ----
  const tk = r2(t);
  const apply = (next: Layout | null) => { if (next) setLayout(next); else toast.error("Maksimal 12 key per jalur; hapus salah satu dulu"); };
  const setCamera = (patch: Partial<Omit<CamKey, "t">>) => {
    const keys = upsertKey(layout.camera.keys, { t: tk, ...sampleCamera(layout, t), ...patch });
    apply(keys && { ...layout, camera: { keys } });
  };
  const actorBase = (id: string): { key: ActorKey; keys: ActorKey[] } => {
    const keys = layout.actors.find((a) => a.character_id === id)!.keys;
    const prev = [...keys].reverse().find((k) => k.t <= t + 0.04) ?? keys[0];
    const s = sampleActor(layout.actors.find((a) => a.character_id === id)!, t);
    return { key: { t: tk, pos: s.pos.map(r2) as Vec3, facing: r2(s.facing), pose: prev.pose, joints: Math.abs(prev.t - t) < 0.04 ? prev.joints : {} }, keys };
  };
  const setActor = (id: string, patch: Partial<Omit<ActorKey, "t">>) => {
    const { key, keys } = actorBase(id);
    const next = upsertKey(keys, { ...key, ...patch });
    apply(next && { ...layout, actors: layout.actors.map((a) => (a.character_id === id ? { ...a, keys: next } : a)) });
  };
  const setBody = (id: string, body: string) => {   // pose dan sendi milik jenis tubuhnya: key lama diubah ke pose berdiri
    setLayout({ ...layout, actors: layout.actors.map((a) => (a.character_id !== id ? a : { ...a, body,
      keys: a.keys.map((k) => ({ ...k, pose: posesOf(body).includes(k.pose) ? k.pose : "stand", joints: {} })) })) });
  };
  const setProp = (i: number, next: Prop) => setLayout({ ...layout, props: layout.props.map((p, n) => (n === i ? next : p)) });
  const patchProp = (i: number, patch: Partial<Prop>) => setProp(i, { ...layout.props[i], ...patch });
  const addProp = (type: string) => {
    if (!type) return;
    if (layout.props.length >= MAX_PROPS) return void toast.error(`Maksimal ${MAX_PROPS} properti`);
    let n = layout.props.length + 1;
    while (layout.props.some((p) => p.id === `${type}${n}`)) n++;
    const p: Prop = { id: `${type}${n}`, type, rot: [0, 0, 0], scale: 1, at: [0, 0], ...(isShape(type) ? { size: [1, 1, 1] as Vec3, color: "#8a8a8a" } : {}) };
    setLayout({ ...layout, props: [...layout.props, p] }); setSel({ kind: "prop", index: layout.props.length });
  };
  const changeType = (i: number, type: string) => {
    const old = layout.props[i];
    const { size: _s, color: _c, ...rest } = old;   // eslint-disable-line @typescript-eslint/no-unused-vars
    setProp(i, { ...rest, type, ...(isShape(type) ? { size: [1, 1, 1] as Vec3, color: "#8a8a8a" } : {}) });
  };
  const removeProp = (i: number) => {
    const gone = layout.props[i].id;   // properti yang menunjuk ke yang dihapus dilepas ke lantai
    setLayout({ ...layout, props: layout.props.filter((_, n) => n !== i).map((p) => (p.on === gone || p.near === gone ? withPlacement(p, "at", { at: [0, 0] }) : p)) });
    setSel({ kind: "camera" });
  };
  const setEnv = (patch: Environment) => {
    const env = { ...layout.environment, ...patch };
    for (const k of Object.keys(env) as (keyof Environment)[]) if (!env[k]) delete env[k];
    setLayout({ ...layout, environment: env });
  };
  const setDuration = (d: number) => {
    const dur = Math.max(1, Math.min(MAX_DURATION, d));
    const cut = <K extends { t: number }>(ks: K[]) => { const kept = ks.filter((k) => k.t <= dur); return kept.length ? kept : [ks[0]]; };
    setLayout({ ...layout, duration: dur, camera: { keys: cut(layout.camera.keys) }, actors: layout.actors.map((a) => ({ ...a, keys: cut(a.keys) })) });
    setT((x) => Math.min(x, dur));
  };

  // ---- AI penyusun (berbayar kecil, lewat konfirmasi biaya) ----
  const tm = useTextModel("scene");
  const estBody: EstimateRequest & { v?: string } = { kind: "scene_blockout", model: tm.model, scene_id: scene.id, v: scene.updated_at };
  const liveEst = useEstimate(estBody);
  const ai = useConfirmedRun(() => estBody, async (c) => {
    const res = await api.sceneBlockout(scene.id, { model: tm.model, ...c });
    setPrior(layout); autoFrame.current = true; setLayout(normalizeLayout(res.layout)); setT(0);
    toast.success(`AI selesai${res.cost != null ? ` ($${res.cost.toFixed(4)})` : ""}; periksa lalu simpan`);
    if (res.warnings.length) toast.warning(res.warnings.slice(0, 3).join(" · "));
  });

  async function save(): Promise<boolean> {
    try { await api.updateScene(scene.id, { blockout: layout }); setSaved(layoutKey); setPrior(null); onSaved(); return true; }
    catch (e) { toast.error((e as Error).message); return false; }
  }

  // ---- render previs: rekam canvas offscreen secara real-time, unggah, dan simpan frame diam ----
  async function renderPrevis() {
    const mime = ["video/webm;codecs=vp9", "video/webm", "video/mp4"].find((m) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(m));
    if (!mime) return void toast.error("Browser ini tidak mendukung perekaman video");
    if (!(await save())) return;
    let fresh: BlockoutResolved;
    try { fresh = await api.resolveBlockout(scene.id, layout); } catch (e) { return void toast.error((e as Error).message); }
    setPlaying(false); setBusy("Merekam previs… jangan pindah tab");
    live.current.recording = true;
    const w = world.current!;
    w.sync({ props: fresh.props, environment: fresh.environment, bounds: fresh.bounds }, layout, names, fresh.looks);
    w.setGrid(false);
    const W = ratio >= 1 ? 1280 : Math.round((1280 * ratio) / 2) * 2, H = ratio >= 1 ? Math.round(1280 / ratio / 2) * 2 : 1280;
    const canvas = document.createElement("canvas");
    const gl = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true }); gl.setSize(W, H, false);
    configureRenderer(gl);
    const cam = new THREE.PerspectiveCamera(35, W / H, 0.1, 500);
    const helpers = w.scene.children.filter((o) => o.type === "CameraHelper");
    helpers.forEach((h) => { h.visible = false; });
    const drawAt = (tt: number) => {
      w.poseAt(layout, tt);
      const c = sampleCamera(layout, tt);
      cam.position.set(...c.pos); cam.lookAt(new THREE.Vector3(...c.target)); cam.fov = fovFor(c.mm, W / H); cam.updateProjectionMatrix();
      gl.render(w.scene, cam);
    };
    const cleanup = () => { gl.dispose(); gl.forceContextLoss(); live.current.recording = false; w.setGrid(true); helpers.forEach((h) => { h.visible = true; }); setBusy(null); };
    try {
      drawAt(0);
      const still = await new Promise<Blob | null>((res) => canvas.toBlob(res, "image/png"));
      const rec = new MediaRecorder(canvas.captureStream(24), { mimeType: mime, videoBitsPerSecond: 5_000_000 });
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      const stopped = new Promise<void>((res) => { rec.onstop = () => res(); });
      let aborted = false;
      rec.start();
      await new Promise<void>((done) => {
        const t0 = performance.now();
        const step = () => {
          if (document.hidden) { aborted = true; return done(); }
          const el = (performance.now() - t0) / 1000;
          drawAt(Math.min(el, layout.duration));
          if (el < layout.duration) requestAnimationFrame(step); else done();
        };
        requestAnimationFrame(step);
      });
      rec.stop(); await stopped;
      if (aborted) return void toast.error("Perekaman dibatalkan karena tab disembunyikan; ulangi dan biarkan tab terbuka");
      setBusy("Mengunggah previs…");
      const video = new Blob(chunks, { type: mime.split(";")[0] });
      await api.scenePrevis(scene.id, video, mime.startsWith("video/mp4") ? "previs.mp4" : "previs.webm");
      if (still) { const img = await api.upload(new File([still], "blockout.png", { type: "image/png" })); await api.updateScene(scene.id, { blockout_image_id: img.id }); }
      toast.success("Previs tersimpan di adegan");
      onSaved();
    } catch (e) { toast.error((e as Error).message); } finally { cleanup(); }
  }

  const keysOf = (): { t: number }[] => sel.kind === "camera" ? layout.camera.keys : sel.kind === "actor" ? layout.actors.find((a) => a.character_id === sel.id)?.keys ?? [] : [];
  const dropKey = (kt: number) => {
    if (sel.kind === "camera") setLayout({ ...layout, camera: { keys: removeKeyAt(layout.camera.keys, kt) } });
    else if (sel.kind === "actor") setLayout({ ...layout, actors: layout.actors.map((a) => (a.character_id === sel.id ? { ...a, keys: removeKeyAt(a.keys, kt) } : a)) });
  };
  const close = () => { if (!busy && (!dirty || window.confirm("Ada perubahan yang belum disimpan. Tutup tanpa menyimpan?"))) onClose(); };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !busy) close(); };
    window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey);
  });

  // ---- panel kanan ----
  const cam = sampleCamera(layout, t);
  const actor = sel.kind === "actor" ? layout.actors.find((a) => a.character_id === sel.id) : undefined;
  const as = actor && sampleActor(actor, t);
  const prevKey = actor && ([...actor.keys].reverse().find((k) => k.t <= t + 0.04) ?? actor.keys[0]);
  const framed = resolved && JSON.stringify(resolved.layout.camera) !== JSON.stringify(layout.camera);
  let detail: ReactNode = null;
  if (sel.kind === "camera") {
    detail = <>
      <Vec label="Posisi (m)" v={cam.pos} onChange={(pos) => setCamera({ pos })} />
      <Vec label="Menatap ke (m)" v={cam.target} onChange={(target) => setCamera({ target })} />
      <label className="field">Lensa {r2(cam.mm)} mm <input type="range" min={14} max={120} value={cam.mm} onChange={(e) => setCamera({ mm: +e.target.value })} /></label>
      {framed && <button className="btn sm" onClick={() => setLayout({ ...layout, camera: resolved!.layout.camera })}>Sesuaikan kamera agar semua tokoh masuk bingkai</button>}
    </>;
  } else if (sel.kind === "env") {
    const e = layout.environment;
    detail = <>
      <label className="field">Waktu
        <select value={e.time ?? ""} onChange={(ev) => setEnv({ time: ev.target.value || undefined })}>
          <option value="">(ikut teks waktu adegan{resolved ? `: ${resolved.environment.time}` : ""})</option>
          {Object.keys(VOCAB.times).map((k) => <option key={k} value={k}>{k}</option>)}</select></label>
      <label className="field">Cuaca
        <select value={e.weather ?? ""} onChange={(ev) => setEnv({ weather: ev.target.value || undefined })}>
          <option value="">(cerah)</option>
          {Object.keys(VOCAB.weather).map((k) => <option key={k} value={k}>{k}</option>)}</select></label>
      <p className="muted">Mengatur langit, cahaya matahari, kabut, dan lampu menyala.</p>
    </>;
  } else if (actor && as && prevKey) {
    const def = bodyDef(actor.body);
    const jn = def.joints.includes(joint) ? joint : def.joints[0];
    const lim = def.limits[jn] ?? [[0, 0], [0, 0], [0, 0]];
    const jv = as.joints[jn] ?? [0, 0, 0];
    detail = <>
      <label className="field">Jenis tubuh
        <select value={actor.body} onChange={(e) => setBody(actor.character_id, e.target.value)}>
          {BODIES.map((b) => <option key={b} value={b}>{VOCAB.bodies[b].label}</option>)}</select></label>
      <Vec label="Posisi (m)" v={as.pos} onChange={(pos) => setActor(actor.character_id, { pos })} />
      <label className="field">Menghadap {Math.round(as.facing)}° (0 = ke penonton)
        <input type="range" min={-180} max={180} value={((as.facing + 540) % 360) - 180} onChange={(e) => setActor(actor.character_id, { facing: +e.target.value })} /></label>
      <label className="field">Pose
        <select value={prevKey.pose} onChange={(e) => setActor(actor.character_id, { pose: e.target.value, joints: {} })}>
          {posesOf(actor.body).map((p) => <option key={p} value={p}>{poseLabel(p)}</option>)}</select></label>
      <label className="field">Sendi
        <select value={jn} onChange={(e) => setJoint(e.target.value)}>{def.joints.map((j) => <option key={j} value={j}>{jointLabel(j)}</option>)}</select></label>
      {(["x", "y", "z"] as const).map((ax, i) => lim[i][0] === lim[i][1] ? null : (
        <label key={ax} className="field">{ax.toUpperCase()} {Math.round(jv[i])}°
          <input type="range" min={lim[i][0]} max={lim[i][1]} value={jv[i]}
            onChange={(e) => { const v = [...jv] as Vec3; v[i] = +e.target.value; setActor(actor.character_id, { joints: { ...prevKey.joints, [jn]: clampJoint(actor.body, jn, v) } }); }} /></label>))}
      <p className="muted">Berjalan/berlari menambah ayunan kaki otomatis. Mengubah apa pun di sini menulis key di waktu {tk} dtk.</p>
    </>;
  } else if (sel.kind === "prop" && layout.props[sel.index]) {
    const i = sel.index, p = layout.props[i], mode = modeOf(p);
    const targets = [...layout.props.filter((_, n) => n !== i).map((o) => ({ id: o.id, label: `${propLabel(o)} (${o.id})` })),
      ...(resolved?.props.filter((o) => o.layer === "set").map((o) => ({ id: o.id, label: `${propLabel(o)} · set latar (${o.id})` })) ?? [])];
    const res = resolved?.props.find((o) => o.id === p.id);
    const scale = Array.isArray(p.scale) ? p.scale[0] : p.scale;
    detail = <>
      <label className="field">Jenis
        <select value={p.type} onChange={(e) => changeType(i, e.target.value)}>
          <optgroup label="Objek">{Object.entries(VOCAB.prefabs).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</optgroup>
          <optgroup label="Bentuk dasar">{VOCAB.shapes.map((k) => <option key={k} value={k}>{k}</option>)}</optgroup></select></label>
      <label className="field">Label <input value={p.label ?? ""} maxLength={40} onChange={(e) => patchProp(i, { label: e.target.value || undefined })} placeholder={VOCAB.prefabs[p.type]?.label ?? p.type} /></label>
      <label className="field">Penempatan
        <select value={mode} onChange={(e) => {
          const m = e.target.value as Mode;
          setProp(i, withPlacement(p, m, m === "at" ? { at: res ? [res.pos[0], res.pos[2]] : [0, 0] } : m === "pos" ? { pos: res ? res.pos : [0, 0, 0] }
            : m === "against" ? { against: "north" } : { [m]: targets[0]?.id } as Partial<Prop>));
        }}>
          <option value="at">Di lantai (x, z)</option><option value="on">Di atas objek lain</option><option value="against">Menempel dinding</option>
          <option value="near">Dekat objek lain</option><option value="pos">Koordinat mutlak</option></select></label>
      {mode === "at" && <div className="bo-vec"><Num label="x" value={p.at?.[0] ?? 0} onChange={(x) => patchProp(i, { at: [x, p.at?.[1] ?? 0] })} /><Num label="z" value={p.at?.[1] ?? 0} onChange={(z) => patchProp(i, { at: [p.at?.[0] ?? 0, z] })} /></div>}
      {mode === "pos" && <Vec label="Posisi alas (m)" v={p.pos ?? [0, 0, 0]} onChange={(pos) => patchProp(i, { pos })} />}
      {(mode === "on" || mode === "near") && (
        <label className="field">Target
          <select value={(mode === "on" ? p.on : p.near) ?? ""} onChange={(e) => patchProp(i, { [mode]: e.target.value })}>
            {targets.length === 0 && <option value="">(belum ada objek lain)</option>}
            {targets.map((tg) => <option key={tg.id} value={tg.id}>{tg.label}</option>)}</select></label>)}
      {mode === "on" && <div className="bo-vec"><Num label="dx" value={p.dx ?? 0} onChange={(dx) => patchProp(i, { dx })} /><Num label="dz" value={p.dz ?? 0} onChange={(dz) => patchProp(i, { dz })} /></div>}
      {mode === "against" && <>
        <label className="field">Dinding <select value={p.against} onChange={(e) => patchProp(i, { against: e.target.value as Wall })}>
          {(Object.keys(WALL_LABEL) as Wall[]).map((w) => <option key={w} value={w}>{WALL_LABEL[w]}</option>)}</select></label>
        <Num label="Geser sepanjang dinding (m)" value={p.offset ?? 0} onChange={(offset) => patchProp(i, { offset })} /></>}
      {mode === "near" && <div className="bo-vec"><Num label="jarak" value={p.dist ?? 0.8} onChange={(dist) => patchProp(i, { dist })} /><Num label="sudut°" value={p.angle ?? 0} step={15} onChange={(angle) => patchProp(i, { angle })} /></div>}
      {mode !== "against" && <label className="field">Putar {Math.round(p.rot[1])}°<input type="range" min={-180} max={180} value={p.rot[1]} onChange={(e) => patchProp(i, { rot: [p.rot[0], +e.target.value, p.rot[2]] })} /></label>}
      <Num label="Skala" value={scale} step={0.1} onChange={(v) => patchProp(i, { scale: Math.max(0.1, Math.min(10, v)) })} />
      {isShape(p.type) && <Vec label="Ukuran (m)" v={p.size ?? [1, 1, 1]} step={0.1} onChange={(size) => patchProp(i, { size: size.map((x) => Math.max(0.02, x)) as Vec3 })} />}
      <label className="field">Warna <input type="color" value={p.color ?? "#8a8a8a"} onChange={(e) => patchProp(i, { color: e.target.value })} />
        {!isShape(p.type) && p.color && <button className="btn ghost sm" onClick={() => patchProp(i, { color: undefined })}>pakai warna bawaan</button>}</label>
      <label className="field">Menyala (emisi) {r2(p.material?.emissive ?? 0)}
        <input type="range" min={0} max={1} step={0.05} value={p.material?.emissive ?? 0} onChange={(e) => patchProp(i, { material: { ...p.material, emissive: +e.target.value } })} /></label>
      {res && <p className="muted">Hasil penempatan: x {r2(res.pos[0])}, y {r2(res.pos[1])}, z {r2(res.pos[2])} m · {res.dims.map(r2).join(" × ")} m</p>}
      <button className="btn danger sm" onClick={() => removeProp(i)}><Trash2 size={13} /> Hapus objek</button>
    </>;
  }

  return (
    <Portal>
      <div className="modal bo-modal" role="dialog" aria-modal="true" aria-label="Susun adegan 3D">
        <div className="bo">
          <div className="bo-main">
            <div className="bo-bar">
              <strong>Adegan {scene.number} · blockout 3D</strong>
              <div className="seg" role="tablist" aria-label="Sudut pandang">
                <button role="tab" aria-selected={view === "free"} className={view === "free" ? "on" : ""} onClick={() => setView("free")}>Kamera bebas</button>
                <button role="tab" aria-selected={view === "camera"} className={view === "camera" ? "on" : ""} onClick={() => setView("camera")}>Lihat dari kamera</button>
              </div>
              <button className="btn ghost sm" onClick={close} aria-label="Tutup" disabled={!!busy}><X size={15} /></button>
            </div>
            <div className="bo-view" ref={box} style={{ aspectRatio: String(ratio) }} />
            <div className="bo-time">
              <button className="btn sm" onClick={() => setPlaying((p) => !p)} aria-label={playing ? "Jeda" : "Putar"}>{playing ? <Pause size={14} /> : <Play size={14} />}</button>
              <input type="range" min={0} max={layout.duration} step={0.05} value={Math.min(t, layout.duration)} aria-label="Waktu"
                onChange={(e) => { setPlaying(false); setT(+e.target.value); }} />
              <span className="mono">{t.toFixed(1)} / </span>
              <input className="bo-dur" type="number" min={1} max={MAX_DURATION} step={1} value={layout.duration} aria-label="Durasi (detik)"
                onChange={(e) => { const v = e.target.valueAsNumber; if (Number.isFinite(v)) setDuration(v); }} /><span className="mono">dtk</span>
            </div>
            <div className="chips" aria-label="Key pada jalur terpilih">
              {keysOf().map((k) => (
                <span key={k.t} className="chip meta">
                  <button className="linklike" onClick={() => { setPlaying(false); setT(k.t); }}>{k.t.toFixed(1)}s</button>
                  <button className="linklike" aria-label={`Hapus key ${k.t}`} onClick={() => dropKey(k.t)}><X size={10} /></button>
                </span>))}
              {(sel.kind === "prop" || sel.kind === "env") && <span className="muted">{sel.kind === "prop" ? "Objek tidak punya key (statis)." : "Lingkungan berlaku untuk seluruh adegan."}</span>}
            </div>
            {(resolveError || (resolved && resolved.warnings.length > 0)) && (
              <details className="bo-warn" open={!!resolveError}>
                <summary className="warn">{resolveError ? "Susunan belum bisa dihitung" : `${resolved!.warnings.length} catatan penataan`}</summary>
                {resolveError ? <p className="error">{resolveError}</p> : <ul className="muted">{resolved!.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
              </details>
            )}
          </div>
          <div className="bo-side">
            <div className="section">
              <h3>Susun dengan AI</h3>
              <TextModelPicker task="scene" value={tm.model} onChange={tm.setModel} />
              <EstimateLine est={liveEst.est} error={liveEst.error} />
              {ai.error && <p className="error">{ai.error}</p>}
              <button className="btn primary block" disabled={!!busy || !!liveEst.error || !liveEst.est || !!liveEst.est.blocked} onClick={() => void ai.start()}>
                <Bot size={15} /> Susun dari naskah adegan
              </button>
              {prior && <button className="btn sm" onClick={() => { setLayout(prior); setPrior(null); }}><Undo2 size={13} /> Kembalikan sebelum draf AI</button>}
              <p className="muted">AI memakai latar, deskripsi dan aksi pemeran, kamera, dan durasi adegan. Hasilnya draf: periksa lalu simpan.</p>
            </div>
            <div className="section">
              <h3>Objek</h3>
              <div className="bo-list">
                <button className={sel.kind === "camera" ? "on" : ""} onClick={() => setSel({ kind: "camera" })}>Kamera</button>
                <button className={sel.kind === "env" ? "on" : ""} onClick={() => setSel({ kind: "env" })}>Lingkungan</button>
                {layout.actors.map((a, i) => (
                  <button key={a.character_id} className={sel.kind === "actor" && sel.id === a.character_id ? "on" : ""} onClick={() => setSel({ kind: "actor", id: a.character_id })}>
                    <span className="dot" style={{ background: ACTOR_COLORS[i % ACTOR_COLORS.length] }} /> {names[a.character_id] ?? "?"}</button>))}
                {layout.props.map((p, i) => (
                  <button key={p.id} className={sel.kind === "prop" && sel.index === i ? "on" : ""} onClick={() => setSel({ kind: "prop", index: i })}>{propLabel(p)}</button>))}
              </div>
              {resolved && resolved.props.some((o) => o.layer === "set") && (
                <p className="muted">Dari set latar: {resolved.props.filter((o) => o.layer === "set").map(propLabel).join(", ")}.</p>
              )}
              <label className="field">Tambah objek
                <select value="" onChange={(e) => addProp(e.target.value)} aria-label="Tambah objek">
                  <option value="">Pilih…</option>
                  <optgroup label="Objek">{Object.entries(VOCAB.prefabs).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</optgroup>
                  <optgroup label="Bentuk dasar">{VOCAB.shapes.map((k) => <option key={k} value={k}>{k}</option>)}</optgroup></select></label>
            </div>
            <div className="section">{detail}</div>
            <div className="bo-foot">
              {busy && <p className="muted"><Loader2 size={13} className="spin" /> {busy}</p>}
              <button className="btn block" disabled={!!busy || !dirty} onClick={() => void save().then((ok) => ok && toast.success("Susunan tersimpan"))}><Save size={15} /> {dirty ? "Simpan susunan" : "Tersimpan"}</button>
              <button className="btn primary block" disabled={!!busy || !!resolveError} onClick={() => void renderPrevis()}><Film size={15} /> Simpan &amp; render previs ({layout.duration} dtk)</button>
            </div>
          </div>
        </div>
        {ai.dialog}
      </div>
    </Portal>
  );
}
