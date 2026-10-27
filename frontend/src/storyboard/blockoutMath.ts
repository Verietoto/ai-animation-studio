// Logika data blockout 3D (plan 14, versi 2 di plan 17): tipe, interpolasi, siklus gerak, susunan awal. Tanpa React dan tanpa three.js,
// jadi bisa dibaca/diuji sendiri. Semua tabel (bentuk, objek siap pakai, jenis tubuh, sendi, batas, pose, waktu, lensa) diambil dari
// `shared/blockout_vocabulary.json`, berkas yang sama dengan yang dibaca backend (`app/vocab.py`), jadi tidak bisa menyimpang.
import vocabJson from "../../../shared/blockout_vocabulary.json";

export type Vec3 = [number, number, number];
export type Wall = "north" | "south" | "east" | "west";
export type BodyName = string;   // "humanoid" | "quadruped" (kunci di kosakata)

interface GaitTerm { joint: string; axis: number; amp: number; fn: "sin" | "cos_pos" | "cos_neg" }
export interface BodyDef {
  label: string; joints: string[]; limits: Record<string, number[][]>;
  poses: Record<string, { hipY: number; rootRot: Vec3; joints: Record<string, Vec3> }>;
  gait: { hz: number; amp: Record<string, number>; terms: GaitTerm[] };
  wiggle: { pose: string; joint: string; axis: number; amp: number; freq: number }[];
}
export interface PrefabDef { label: string; size: Vec3; top: boolean; elevation?: number; light?: boolean; walkable?: boolean }
export interface TimeDef { sky_top: string; sky_bottom: string; ground: string; sun_color: string; sun_intensity: number; sun_dir: Vec3; ambient: number; fog: string; fog_density: number }
export interface Vocab {
  lens: { sensor_short_mm: number }; shapes: string[]; prefabs: Record<string, PrefabDef>; times: Record<string, TimeDef>;
  weather: Record<string, { fog_mul: number; dim: number }>; hair: string[]; accessories: string[]; ears: string[]; tails: string[];
  bodies: Record<string, BodyDef>;
}
export const VOCAB = vocabJson as unknown as Vocab;
export const BODIES = Object.keys(VOCAB.bodies);
export const bodyDef = (name: string): BodyDef => VOCAB.bodies[name] ?? VOCAB.bodies.humanoid;
export const posesOf = (name: string) => Object.keys(bodyDef(name).poses);
export const isShape = (type: string) => VOCAB.shapes.includes(type);

export const POSE_LABEL: Record<string, string> = {
  stand: "Berdiri", sit: "Duduk", walk: "Berjalan", run: "Berlari", point: "Menunjuk", wave: "Melambai", lie: "Berbaring", jump: "Melompat",
};
const JOINT_LABEL: Record<string, string> = {
  spine: "Perut", chest: "Dada", neck: "Leher", head: "Kepala", tail: "Ekor",
  l_shoulder: "Bahu kiri", l_elbow: "Siku kiri", l_wrist: "Pergelangan kiri", r_shoulder: "Bahu kanan", r_elbow: "Siku kanan", r_wrist: "Pergelangan kanan",
  l_hip: "Pinggul kiri", l_knee: "Lutut kiri", l_ankle: "Kaki kiri", r_hip: "Pinggul kanan", r_knee: "Lutut kanan", r_ankle: "Kaki kanan",
  fl_leg: "Kaki depan kiri", fl_knee: "Siku depan kiri", fr_leg: "Kaki depan kanan", fr_knee: "Siku depan kanan",
  bl_leg: "Kaki belakang kiri", bl_knee: "Lutut belakang kiri", br_leg: "Kaki belakang kanan", br_knee: "Lutut belakang kanan",
};
export const jointLabel = (j: string) => JOINT_LABEL[j] ?? j;
export const poseLabel = (p: string) => POSE_LABEL[p] ?? p;

export type Joints = Record<string, Vec3>;
export interface CamKey { t: number; pos: Vec3; target: Vec3; mm: number }
export interface ActorKey { t: number; pos: Vec3; facing: number; pose: string; joints: Joints }
export interface Actor { character_id: string; body: BodyName; keys: ActorKey[] }
export interface Prop {
  id: string; type: string; label?: string; color?: string; material?: { roughness?: number; emissive?: number };
  rot: Vec3; scale: number | Vec3; size?: Vec3;
  pos?: Vec3; at?: [number, number]; on?: string; against?: Wall; near?: string;
  dx?: number; dz?: number; offset?: number; dist?: number; angle?: number;
}
export interface ResolvedProp extends Prop { pos: Vec3; dims: Vec3; layer: "set" | "scene" }
export interface Environment { time?: string; weather?: string }
export interface Layout { version: 2; duration: number; environment: Environment; camera: { keys: CamKey[] }; actors: Actor[]; props: Prop[] }
/** Penampilan tokoh (plan 17): disimpan per karakter, dipakai pembangun manekin. Semua field opsional. */
export interface Look {
  body?: BodyName; height?: number; build?: number; skin?: string; hair?: { style: string; color: string }; top?: string; bottom?: string;
  accessories?: string[]; size?: number; fur?: string; fur2?: string; ears?: string; tail?: string;
}

export const MAX_KEYS = 12, MAX_PROPS = 120, MAX_DURATION = 15, DEFAULT_DURATION = 5;
const KEY_EPS = 0.04;   // dua key dalam rentang ini dianggap key yang sama

export function clampJoint(body: BodyName, name: string, v: Vec3): Vec3 {
  const lim = bodyDef(body).limits[name];
  return lim ? (v.map((x, i) => Math.min(lim[i][1], Math.max(lim[i][0], x))) as Vec3) : v;
}

const lerp = (a: number, b: number, u: number) => a + (b - a) * u;
const lerpV = (a: Vec3, b: Vec3, u: number): Vec3 => [lerp(a[0], b[0], u), lerp(a[1], b[1], u), lerp(a[2], b[2], u)];
/** Sudut terpendek (derajat): 350 -> 10 lewat 360, bukan memutar balik lewat 180. */
const lerpAngle = (a: number, b: number, u: number) => a + ((((b - a) % 360) + 540) % 360 - 180) * u;

/** Pasangan key yang mengapit t beserta fraksi u (0..1); sebelum key pertama / sesudah terakhir = key itu sendiri. */
function bracket<K extends { t: number }>(keys: K[], t: number): [K, K, number] {
  if (t <= keys[0].t) return [keys[0], keys[0], 0];
  const last = keys[keys.length - 1];
  if (t >= last.t) return [last, last, 0];
  const i = keys.findIndex((k) => k.t > t);
  const [a, b] = [keys[i - 1], keys[i]];
  return [a, b, (t - a.t) / (b.t - a.t)];
}

export interface ActorSample { pos: Vec3; facing: number; hipY: number; rootRot: Vec3; joints: Joints }

function poseJoints(def: BodyDef, key: ActorKey): Joints {
  const pose = def.poses[key.pose] ?? def.poses.stand;
  const out: Joints = {};
  for (const j of def.joints) {
    const raw = key.joints[j] ?? pose.joints[j] ?? [0, 0, 0];
    const lim = def.limits[j];
    out[j] = lim ? (raw.map((x, i) => Math.min(lim[i][1], Math.max(lim[i][0], x))) as Vec3) : raw;
  }
  return out;
}

const GAIT_FN = { sin: (_c: number, s: number) => s, cos_pos: (c: number) => Math.max(0, c), cos_neg: (c: number) => Math.max(0, -c) };

export function sampleActor(actor: Actor, t: number): ActorSample {
  const def = bodyDef(actor.body);
  const [a, b, u] = bracket(actor.keys, t);
  const [ja, jb] = [poseJoints(def, a), poseJoints(def, b)];
  const joints: Joints = {};
  for (const j of def.joints) joints[j] = lerpV(ja[j], jb[j], u);
  // siklus jalan/lari prosedural dan gerak berulang (grill 14: AI tidak perlu menulis tiap langkah); data dari kosakata
  const amp = lerp(def.gait.amp[a.pose] ?? 0, def.gait.amp[b.pose] ?? 0, u);
  const bump = (j: string, axis: number, d: number) => {
    const v = [...joints[j]] as Vec3; v[axis] += d; joints[j] = clampJoint(actor.body, j, v);
  };
  if (amp > 0) {
    const ph = t * def.gait.hz * 2 * Math.PI, s = Math.sin(ph), c = Math.cos(ph);
    for (const term of def.gait.terms) bump(term.joint, term.axis, term.amp * amp * GAIT_FN[term.fn](c, s));
  }
  for (const w of def.wiggle) {
    const weight = lerp(a.pose === w.pose ? 1 : 0, b.pose === w.pose ? 1 : 0, u);
    if (weight > 0) bump(w.joint, w.axis, w.amp * weight * Math.sin(t * w.freq));
  }
  const pa = def.poses[a.pose] ?? def.poses.stand, pb = def.poses[b.pose] ?? def.poses.stand;
  return { pos: lerpV(a.pos, b.pos, u), facing: lerpAngle(a.facing, b.facing, u), hipY: lerp(pa.hipY, pb.hipY, u), rootRot: lerpV(pa.rootRot, pb.rootRot, u), joints };
}

export function sampleCamera(layout: Layout, t: number): Omit<CamKey, "t"> {
  const [a, b, u] = bracket(layout.camera.keys, t);
  return { pos: lerpV(a.pos, b.pos, u), target: lerpV(a.target, b.target, u), mm: lerp(a.mm, b.mm, u) };
}

/** Lensa (mm, sensor sisi pendek) -> FOV vertikal derajat untuk rasio lebar/tinggi tertentu. HARUS sama dengan `fov_for` di backend/app/vocab.py. */
export function fovFor(mm: number, aspect: number): number {
  const short = 2 * Math.atan(VOCAB.lens.sensor_short_mm / 2 / mm);   // sudut sisi pendek
  return (aspect >= 1 ? short : 2 * Math.atan(Math.tan(short / 2) / aspect)) * 180 / Math.PI;
}

export const ratioOf = (r: string): number => { const [w, h] = r.split(":").map(Number); return w > 0 && h > 0 ? w / h : 16 / 9; };

/** Tambah/ganti key di waktu t (key dalam ±0.04 dtk dianggap sama). Mengembalikan null bila melewati batas key. */
export function upsertKey<K extends { t: number }>(keys: K[], key: K): K[] | null {
  const i = keys.findIndex((k) => Math.abs(k.t - key.t) < KEY_EPS);
  if (i >= 0) return keys.map((k, n) => (n === i ? { ...key, t: k.t } : k));
  if (keys.length >= MAX_KEYS) return null;
  return [...keys, key].sort((x, y) => x.t - y.t);
}
export const removeKeyAt = <K extends { t: number }>(keys: K[], t: number): K[] =>
  keys.length <= 1 ? keys : keys.filter((k) => Math.abs(k.t - t) >= KEY_EPS);

const round = (n: number, d = 3) => Math.round(n * 10 ** d) / 10 ** d;

/** Susunan awal deterministik dari pemeran + teks kamera: dipakai bila adegan belum punya blockout. `bodies`: jenis tubuh per karakter. */
export function defaultLayout(cast: { character_id: string }[], duration: number, cameraText: string, bodies: Record<string, BodyName> = {}): Layout {
  const text = cameraText.toLowerCase();
  const has = (...w: string[]) => w.some((x) => text.includes(x));
  let dist = 5, mm = 35, camY = 1.5;
  if (has("close", "dekat")) { dist = 2.6; mm = 70; camY = 1.55; }
  else if (has("wide", "establishing", "lebar", "jauh")) { dist = 9; mm = 24; }
  if (has("dari atas", "high angle", "top", "overhead")) camY = 5;
  else if (has("dari bawah", "low angle", "rendah")) camY = 0.4;
  const gap = 1.2, x0 = -((cast.length - 1) * gap) / 2;
  return {
    version: 2, duration: Math.max(1, Math.min(MAX_DURATION, duration)), environment: {},
    camera: { keys: [{ t: 0, pos: [0, camY, dist], target: [0, 1.2, 0], mm }] },
    actors: cast.map((c, i) => ({ character_id: c.character_id, body: bodies[c.character_id] ?? "humanoid",
      keys: [{ t: 0, pos: [round(x0 + i * gap), 0, 0], facing: 0, pose: "stand", joints: {} }] })),
    props: [],
  };
}

/** Terima susunan v1 atau v2 dari server dan kembalikan v2 yang lengkap (id properti, jenis tubuh, ukuran bentuk, penempatan). */
export function normalizeLayout(raw: unknown): Layout {
  const r = raw as Record<string, any>;   // eslint-disable-line @typescript-eslint/no-explicit-any
  const props: Prop[] = ((r.props ?? []) as Record<string, any>[]).map((p, i) => {   // eslint-disable-line @typescript-eslint/no-explicit-any
    const out: Prop = { id: p.id ?? `p${i + 1}`, type: p.type, rot: p.rot ?? [0, 0, 0], scale: p.scale ?? 1 };
    for (const k of ["label", "color", "material", "pos", "at", "on", "against", "near", "dx", "dz", "offset", "dist", "angle"] as const) {
      if (p[k] !== undefined) (out as any)[k] = p[k];   // eslint-disable-line @typescript-eslint/no-explicit-any
    }
    if (isShape(p.type)) {
      const size: Vec3 = p.size ?? [1, 1, 1];
      out.size = size; out.color = out.color ?? "#8a8a8a";
      if (r.version !== 2 && out.pos) {   // v1: pos = titik tengah bentuk; v2: pos = titik tengah ALAS (sama dengan backend/app/blockout.py)
        const sc = Array.isArray(out.scale) ? out.scale[1] : out.scale;
        out.pos = [out.pos[0], Math.round((out.pos[1] - (size[1] * sc) / 2) * 1000) / 1000, out.pos[2]];
      }
    }
    if (!out.pos && !out.at && !out.on && !out.against && !out.near) out.at = [0, 0];
    return out;
  });
  return {
    version: 2, duration: r.duration, environment: r.environment ?? {}, camera: r.camera,
    actors: ((r.actors ?? []) as Actor[]).map((a) => ({ ...a, body: a.body ?? "humanoid" })), props,
  };
}

/** Muat susunan tersimpan dengan menyelaraskannya ke pemeran sekarang: aktor basi dibuang, pemeran baru diberi aktor. */
export function alignToCast(layout: Layout, cast: { character_id: string }[], bodies: Record<string, BodyName> = {}): Layout {
  const keep = layout.actors.filter((a) => cast.some((c) => c.character_id === a.character_id));
  const fresh = defaultLayout(cast.filter((c) => !keep.some((a) => a.character_id === c.character_id)), layout.duration, "", bodies).actors;
  return { ...layout, actors: [...keep, ...fresh] };
}

/** Ganti penempatan properti: hanya satu cara penempatan yang tersisa (sesuai aturan server). */
export function withPlacement(p: Prop, mode: "pos" | "at" | "on" | "against" | "near", v: Partial<Prop>): Prop {
  const { pos: _a, at: _b, on: _c, against: _d, near: _e, dx: _f, dz: _g, offset: _h, dist: _i, angle: _j, ...rest } = p;   // eslint-disable-line @typescript-eslint/no-unused-vars
  return { ...rest, [mode]: v[mode], ...(mode === "on" ? { dx: v.dx ?? 0, dz: v.dz ?? 0 } : {}), ...(mode === "against" ? { offset: v.offset ?? 0 } : {}),
    ...(mode === "near" ? { dist: v.dist, angle: v.angle } : {}) } as Prop;
}
