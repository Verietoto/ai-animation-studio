// Pembangun scene three.js untuk blockout (plan 14; versi 2 di plan 17). Dimuat dinamis lewat Blockout.tsx, jadi three.js tidak masuk bundel utama.
// Konvensi sumbu sama dengan prompt AI: Y atas, lantai y=0, facing 0 = menghadap +Z, 90 = menghadap +X; sisi "l_" ada di +X.
// Objek diletakkan oleh pemecah tata letak di backend (`pos` = titik tengah ALAS, `dims` = ukuran akhir); modul ini hanya merender.
import * as THREE from "three";
import { Actor, ActorSample, bodyDef, Environment, isShape, Layout, Look, ResolvedProp, sampleActor, Vec3, VOCAB } from "./blockoutMath";

const DEG = Math.PI / 180;
export const ACTOR_COLORS = ["#4f9cff", "#ff8a4f", "#6fd08c", "#d58cff"];

// ---------- helper geometri ----------
interface MatOpts { rough?: number; emissive?: number; opacity?: number }
const matCache = new Map<string, THREE.MeshStandardMaterial>();
function std(color: string, o: MatOpts = {}): THREE.MeshStandardMaterial {
  const key = `${color}|${o.rough ?? 0.85}|${o.emissive ?? 0}|${o.opacity ?? 1}`;
  let m = matCache.get(key);
  if (!m) {
    m = new THREE.MeshStandardMaterial({ color, roughness: o.rough ?? 0.85, metalness: 0.02, transparent: (o.opacity ?? 1) < 1, opacity: o.opacity ?? 1,
      emissive: new THREE.Color((o.emissive ?? 0) > 0 ? color : "#000000"), emissiveIntensity: o.emissive ?? 0 });
    matCache.set(key, m);
  }
  return m;
}
function add(parent: THREE.Object3D, g: THREE.BufferGeometry, color: string, x = 0, y = 0, z = 0, o: MatOpts = {}): THREE.Mesh {
  const m = new THREE.Mesh(g, std(color, o));
  m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true;
  parent.add(m);
  return m;
}
const box = (p: THREE.Object3D, w: number, h: number, d: number, x: number, y: number, z: number, c: string, o?: MatOpts) => add(p, new THREE.BoxGeometry(w, h, d), c, x, y, z, o);
const cyl = (p: THREE.Object3D, rt: number, rb: number, h: number, x: number, y: number, z: number, c: string, o?: MatOpts, seg = 16) => add(p, new THREE.CylinderGeometry(rt, rb, h, seg), c, x, y, z, o);
const sph = (p: THREE.Object3D, r: number, x: number, y: number, z: number, c: string, sx = 1, sy = 1, sz = 1, o?: MatOpts) => {
  const m = add(p, new THREE.SphereGeometry(r, 16, 12), c, x, y, z, o); m.scale.set(sx, sy, sz); return m;
};
const joint = (parent: THREE.Object3D, x: number, y: number, z = 0) => { const o = new THREE.Object3D(); o.position.set(x, y, z); parent.add(o); return o; };

// ---------- objek siap pakai (alas di y=0, berpusat di x/z; ukuran dasar dari kosakata) ----------
type Builder = (g: THREE.Group, s: Vec3, main: string | undefined, o: MatOpts) => void;
const WOOD = "#8b5e3c", DARK = "#4a3426", FABRIC = "#b5524a";
const BUILDERS: Record<string, Builder> = {
  table: (g, [w, h, d], c) => { box(g, w, 0.04, d, 0, h - 0.02, 0, c ?? WOOD); for (const sx of [-1, 1]) for (const sz of [-1, 1]) box(g, 0.06, h - 0.04, 0.06, sx * (w / 2 - 0.05), (h - 0.04) / 2, sz * (d / 2 - 0.05), DARK); },
  chair: (g, [w, h, d], c) => { box(g, w, 0.05, d, 0, 0.45, 0, c ?? WOOD); box(g, w, h - 0.5, 0.05, 0, 0.5 + (h - 0.5) / 2, -d / 2 + 0.025, c ?? WOOD);
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) box(g, 0.04, 0.45, 0.04, sx * (w / 2 - 0.04), 0.225, sz * (d / 2 - 0.04), DARK); },
  stool: (g, [w, h], c) => { cyl(g, w / 2, w / 2, 0.05, 0, h - 0.025, 0, c ?? WOOD); for (let i = 0; i < 3; i++) { const a = (i / 3) * Math.PI * 2; cyl(g, 0.025, 0.025, h - 0.05, Math.cos(a) * w * 0.3, (h - 0.05) / 2, Math.sin(a) * w * 0.3, DARK, undefined, 8); } },
  bench: (g, [w, h, d], c) => { box(g, w, 0.05, d, 0, h - 0.025, 0, c ?? WOOD); for (const sx of [-1, 1]) box(g, 0.06, h - 0.05, d * 0.9, sx * (w / 2 - 0.1), (h - 0.05) / 2, 0, DARK); },
  counter: (g, [w, h, d], c) => { box(g, w, h - 0.05, d, 0, (h - 0.05) / 2, 0, c ?? "#7a5a3c"); box(g, w + 0.06, 0.05, d + 0.06, 0, h - 0.025, 0, "#cbbba0"); },
  shelf: (g, [w, h, d], c) => { for (const sx of [-1, 1]) box(g, 0.03, h, d, sx * (w / 2 - 0.015), h / 2, 0, c ?? WOOD); box(g, w, h, 0.02, 0, h / 2, -d / 2 + 0.01, DARK);
    for (let i = 0; i <= 4; i++) box(g, w, 0.03, d, 0, 0.015 + (i * (h - 0.03)) / 4, 0, c ?? WOOD); },
  bed: (g, [w, h, d], c) => { box(g, w, 0.25, d, 0, 0.125, 0, c ?? WOOD); box(g, w - 0.1, h - 0.3, d - 0.1, 0, 0.25 + (h - 0.3) / 2, 0, "#e9e4da"); box(g, 0.5, 0.12, 0.35, 0, h + 0.03, -d / 2 + 0.3, "#ffffff"); box(g, w, 0.55, 0.06, 0, 0.3, -d / 2 + 0.03, c ?? WOOD); },
  sofa: (g, [w, h, d], c) => { box(g, w, 0.4, d, 0, 0.2, 0, c ?? FABRIC); box(g, w, h - 0.4, 0.2, 0, 0.4 + (h - 0.4) / 2, -d / 2 + 0.1, c ?? FABRIC); for (const sx of [-1, 1]) box(g, 0.18, 0.28, d, sx * (w / 2 - 0.09), 0.54, 0, c ?? FABRIC); },
  door: (g, [w, h, d], c) => { box(g, w, h, d, 0, h / 2, 0, c ?? "#7a4b2a"); sph(g, 0.04, w / 2 - 0.1, 1.0, d / 2 + 0.03, "#d9b34a"); },
  window: (g, [w, h, d], c) => { for (const sy of [-1, 1]) box(g, w, 0.06, d, 0, h / 2 + sy * (h / 2 - 0.03), 0, c ?? "#e8e1d4"); for (const sx of [-1, 1]) box(g, 0.06, h, d, sx * (w / 2 - 0.03), h / 2, 0, c ?? "#e8e1d4");
    box(g, w - 0.1, h - 0.1, 0.01, 0, h / 2, 0, "#9fd3ff", { rough: 0.1, opacity: 0.45 }); },
  wall: (g, [w, h, d], c) => { box(g, w, h, d, 0, h / 2, 0, c ?? "#cfc6b8"); },
  lamp: (g, [, h], c, o) => { cyl(g, 0.12, 0.14, 0.03, 0, 0.015, 0, DARK); cyl(g, 0.02, 0.02, h - 0.35, 0, (h - 0.35) / 2 + 0.03, 0, DARK, undefined, 8); cyl(g, 0.1, 0.2, 0.3, 0, h - 0.15, 0, c ?? "#ffe6a8", { emissive: o.emissive ?? 0.9, rough: 0.5 });
    g.userData.light = { y: h - 0.2, color: c ?? "#ffe6a8", intensity: 1.2 }; },
  street_lamp: (g, [, h], c, o) => { cyl(g, 0.05, 0.07, h, 0, h / 2, 0, "#3a3f47"); box(g, 0.5, 0.06, 0.06, 0.2, h - 0.05, 0, "#3a3f47"); box(g, 0.3, 0.1, 0.18, 0.4, h - 0.12, 0, c ?? "#ffe6a8", { emissive: o.emissive ?? 1, rough: 0.4 });
    g.userData.light = { y: h - 0.2, color: c ?? "#ffe6a8", intensity: 2.2, dx: 0.4 }; },
  tree: (g, [w, h], c) => { cyl(g, 0.12, 0.18, h * 0.45, 0, h * 0.225, 0, "#6b4a2b"); sph(g, w * 0.5, 0, h * 0.58, 0, c ?? "#3f7d3c", 1, 0.9, 1); sph(g, w * 0.38, w * 0.15, h * 0.78, w * 0.05, c ?? "#488a43"); sph(g, w * 0.3, -w * 0.1, h * 0.92, 0, c ?? "#52994a"); },
  bush: (g, [w, h], c) => { sph(g, w * 0.5, 0, h * 0.45, 0, c ?? "#3f7d3c", 1, h / w, 1); sph(g, w * 0.35, w * 0.3, h * 0.35, w * 0.1, c ?? "#488a43", 1, 0.9, 1); sph(g, w * 0.3, -w * 0.3, h * 0.35, -w * 0.05, c ?? "#52994a", 1, 0.9, 1); },
  rock: (g, [w, h, d], c) => { const m = add(g, new THREE.IcosahedronGeometry(0.5, 0), c ?? "#8a8d92", 0, h / 2, 0); m.scale.set(w, h, d); },
  fence: (g, [w, h, d], c) => { const n = Math.max(2, Math.round(w / 0.5) + 1); for (let i = 0; i < n; i++) box(g, 0.08, h, 0.08, -w / 2 + (i * w) / (n - 1), h / 2, 0, c ?? WOOD); for (const y of [0.35, 0.75]) box(g, w, 0.06, d, 0, h * y, 0, c ?? WOOD); },
  house: (g, [w, h, d], c) => { const wall = h * 0.62; box(g, w, wall, d, 0, wall / 2, 0, c ?? "#e8dcc4"); const roof = add(g, new THREE.ConeGeometry(0.5, h - wall, 4), "#8a3b2e", 0, wall + (h - wall) / 2, 0); roof.rotation.y = Math.PI / 4; roof.scale.set(w * 1.45, 1, d * 1.45);
    box(g, 0.9, 1.9, 0.06, 0, 0.95, d / 2 + 0.02, "#6b4426"); for (const sx of [-1, 1]) box(g, 0.8, 0.8, 0.05, sx * (w / 2 - 0.9), 1.5, d / 2 + 0.02, "#9fd3ff", { rough: 0.2 }); },
  road: (g, [w, h, d], c) => { box(g, w, h, d, 0, h / 2, 0, c ?? "#2c2f36"); for (let i = -3; i <= 3; i++) box(g, 0.6, 0.005, 0.1, (i * w) / 7, h + 0.003, 0, "#e5e2d0"); },
  crate: (g, [w, h, d], c) => { box(g, w, h, d, 0, h / 2, 0, c ?? "#a67c52"); for (const sx of [-1, 1]) for (const sz of [-1, 1]) box(g, 0.05, h + 0.01, 0.05, sx * (w / 2 - 0.02), h / 2, sz * (d / 2 - 0.02), DARK); },
  barrel: (g, [w, h], c) => { cyl(g, w / 2, w / 2, h, 0, h / 2, 0, c ?? "#7a5230"); for (const y of [0.2, 0.7]) cyl(g, w / 2 + 0.01, w / 2 + 0.01, 0.04, 0, h * y, 0, "#3a3f47"); },
  cup: (g, [w, h], c) => { cyl(g, w / 2, w * 0.4, h, 0, h / 2, 0, c ?? "#f2efe8"); const t = add(g, new THREE.TorusGeometry(h * 0.28, h * 0.06, 6, 12), c ?? "#f2efe8", w / 2, h * 0.5, 0); t.scale.set(0.8, 1, 1); },
  plant: (g, [w, h], c) => { cyl(g, w * 0.45, w * 0.35, h * 0.35, 0, h * 0.175, 0, "#b4572f"); sph(g, w * 0.55, 0, h * 0.6, 0, c ?? "#3f7d3c", 1, 0.9, 1); sph(g, w * 0.38, 0, h * 0.85, 0, c ?? "#52994a"); },
  car: (g, [w, h, d], c) => { box(g, w, h * 0.35, d, 0, 0.3 + h * 0.175, 0, c ?? "#c0392b"); box(g, w * 0.5, h * 0.35, d * 0.9, -w * 0.05, 0.3 + h * 0.35 + h * 0.175, 0, "#9fd3ff", { rough: 0.2 });
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) { const wh = cyl(g, 0.3, 0.3, 0.22, sx * (w / 2 - 0.7), 0.3, sz * (d / 2 - 0.08), "#1b1d22"); wh.rotation.x = Math.PI / 2; } },
  motorbike: (g, [w, , d], c) => { for (const sx of [-1, 1]) { const wh = cyl(g, 0.3, 0.3, 0.1, sx * (w / 2 - 0.3), 0.3, 0, "#1b1d22"); wh.rotation.x = Math.PI / 2; }
    box(g, w * 0.5, 0.25, d * 0.5, 0, 0.55, 0, c ?? "#2d6cdf"); box(g, w * 0.3, 0.1, d * 0.55, -w * 0.1, 0.78, 0, "#222"); box(g, 0.06, 0.06, d, w / 2 - 0.35, 0.95, 0, "#444"); },
  cart: (g, [w, , d], c) => { box(g, w, 0.5, d, 0, 0.75, 0, c ?? "#c8a24c"); box(g, w, 0.4, 0.04, 0, 1.2, -d / 2 + 0.02, c ?? "#c8a24c"); for (const sz of [-1, 1]) { const wh = cyl(g, 0.32, 0.32, 0.06, 0, 0.32, sz * (d / 2 + 0.03), "#3a3f47"); wh.rotation.x = Math.PI / 2; }
    box(g, 0.8, 0.04, 0.04, -w / 2 - 0.35, 0.9, 0, DARK); },
  sign: (g, [w, h, d], c) => { box(g, w, h, d, 0, h / 2, 0, c ?? "#3b7a57"); },
};

export function buildProp(rp: ResolvedProp): THREE.Group {
  const g = new THREE.Group();
  const o: MatOpts = { rough: rp.material?.roughness, emissive: rp.material?.emissive };
  const pre = VOCAB.prefabs[rp.type];
  const holder = new THREE.Group();
  if (pre) {
    const base = pre.size;
    (BUILDERS[rp.type] ?? BUILDERS.crate)(holder, base, rp.color, o);
    holder.scale.set(rp.dims[0] / base[0], rp.dims[1] / base[1], rp.dims[2] / base[2]);
  } else if (isShape(rp.type)) {
    const geo = { box: () => new THREE.BoxGeometry(1, 1, 1), cylinder: () => new THREE.CylinderGeometry(0.5, 0.5, 1, 24), sphere: () => new THREE.SphereGeometry(0.5, 20, 14),
      cone: () => new THREE.ConeGeometry(0.5, 1, 24), capsule: () => new THREE.CapsuleGeometry(0.25, 0.5, 6, 14), torus: () => new THREE.TorusGeometry(0.35, 0.12, 10, 24),
      plane: () => new THREE.PlaneGeometry(1, 1) }[rp.type as "box"]();
    const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: rp.color ?? "#8a8a8a", roughness: o.rough ?? 0.9, side: THREE.DoubleSide,
      emissive: new THREE.Color((o.emissive ?? 0) > 0 ? (rp.color ?? "#8a8a8a") : "#000000"), emissiveIntensity: o.emissive ?? 0 }));
    m.castShadow = rp.type !== "plane"; m.receiveShadow = true;
    m.scale.set(rp.dims[0], rp.dims[1], rp.dims[2]); m.position.y = rp.dims[1] / 2;   // alas di y=0 (v2): pos adalah titik tengah ALAS
    holder.add(m);
  }
  g.add(holder);
  const L = holder.userData.light as { y: number; color: string; intensity: number; dx?: number } | undefined;
  if (L) g.userData.light = { ...L, y: L.y * (rp.dims[1] / (pre?.size[1] ?? 1)) };
  g.position.set(rp.pos[0], rp.pos[1], rp.pos[2]);
  g.rotation.order = "YXZ";
  g.rotation.set(rp.rot[0] * DEG, rp.rot[1] * DEG, rp.rot[2] * DEG);
  return g;
}

// ---------- manekin ----------
export interface Mannequin { root: THREE.Group; pelvis: THREE.Object3D; joints: Record<string, THREE.Object3D> }

function nameTag(text: string, y: number): THREE.Sprite {
  const c = document.createElement("canvas"); c.width = 256; c.height = 64;
  const g = c.getContext("2d")!;
  g.fillStyle = "rgba(0,0,0,.55)"; g.fillRect(0, 0, 256, 64);
  g.fillStyle = "#fff"; g.font = "bold 30px sans-serif"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(text.slice(0, 14), 128, 34);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), depthTest: false }));
  sprite.scale.set(0.6, 0.15, 1); sprite.position.set(0, y, 0); sprite.renderOrder = 10;
  return sprite;
}

function buildHumanoid(look: Look, color: string): Mannequin {
  const skin = look.skin ?? color, top = look.top ?? color, bottom = look.bottom ?? color, wd = look.build ?? 1;
  const anchor = new THREE.Group(), root = new THREE.Group();
  root.scale.setScalar(look.height ?? 1);          // skala seragam: sendi tidak terdistorsi
  anchor.add(root);
  const pelvis = joint(root, 0, 0.95);
  box(pelvis, 0.3 * wd, 0.18, 0.18 * wd, 0, 0, 0, bottom);
  const J: Record<string, THREE.Object3D> = {};
  J.spine = joint(pelvis, 0, 0.09); add(J.spine, new THREE.CylinderGeometry(0.1 * wd, 0.12 * wd, 0.18), top, 0, 0.09, 0);
  J.chest = joint(J.spine, 0, 0.18); box(J.chest, 0.34 * wd, 0.3, 0.2 * wd, 0, 0.15, 0, top);
  J.neck = joint(J.chest, 0, 0.3); cyl(J.neck, 0.04, 0.045, 0.08, 0, 0.04, 0, skin, undefined, 10);
  J.head = joint(J.neck, 0, 0.08); sph(J.head, 0.11, 0, 0.11, 0, skin);
  box(J.head, 0.04, 0.03, 0.05, 0, 0.1, 0.11, skin);                       // hidung: arah hadap
  for (const sx of [-1, 1]) sph(J.head, 0.016, sx * 0.04, 0.13, 0.098, "#1b1b1b");   // mata
  const style = look.hair?.style ?? "short", hair = look.hair?.color ?? "#2a1d14";
  if (style !== "bald") {
    const cap = add(J.head, new THREE.SphereGeometry(0.118, 16, 10, 0, Math.PI * 2, 0, Math.PI * 0.55), hair, 0, 0.12, -0.005);
    cap.rotation.x = -0.12;
    if (style === "long") box(J.head, 0.22, 0.34, 0.07, 0, 0.0, -0.085, hair);
    if (style === "braids") for (const sx of [-1, 1]) add(J.head, new THREE.CapsuleGeometry(0.03, 0.3, 4, 8), hair, sx * 0.1, -0.02, -0.04);
    if (style === "bun") sph(J.head, 0.06, 0, 0.25, -0.03, hair);
  }
  for (const a of look.accessories ?? []) {
    if (a === "glasses") { for (const sx of [-1, 1]) add(J.head, new THREE.TorusGeometry(0.03, 0.006, 6, 14), "#1b1b1b", sx * 0.04, 0.13, 0.105); box(J.head, 0.03, 0.006, 0.006, 0, 0.13, 0.108, "#1b1b1b"); }
    if (a === "hat") { cyl(J.head, 0.2, 0.2, 0.015, 0, 0.215, 0, "#b8863b"); cyl(J.head, 0.1, 0.12, 0.1, 0, 0.27, 0, "#b8863b"); }
  }
  for (const [side, sx] of [["l", 0.2], ["r", -0.2]] as const) {
    const sh = (J[`${side}_shoulder`] = joint(J.chest, sx * wd, 0.26));
    add(sh, new THREE.CapsuleGeometry(0.045, 0.22, 4, 8), top, 0, -0.15, 0);
    const el = (J[`${side}_elbow`] = joint(sh, 0, -0.3));
    add(el, new THREE.CapsuleGeometry(0.04, 0.2, 4, 8), skin, 0, -0.135, 0);
    const wr = (J[`${side}_wrist`] = joint(el, 0, -0.27));
    sph(wr, 0.05, 0, -0.04, 0, skin);
    const hp = (J[`${side}_hip`] = joint(pelvis, (sx / 2) * wd, -0.09));
    add(hp, new THREE.CapsuleGeometry(0.065, 0.32, 4, 8), bottom, 0, -0.21, 0);
    const kn = (J[`${side}_knee`] = joint(hp, 0, -0.42));
    add(kn, new THREE.CapsuleGeometry(0.052, 0.32, 4, 8), bottom, 0, -0.21, 0);
    const an = (J[`${side}_ankle`] = joint(kn, 0, -0.42));
    box(an, 0.1, 0.06, 0.24, 0, -0.03, 0.06, "#2a2a2a");
  }
  return { root: anchor, pelvis, joints: J };
}

function buildQuadruped(look: Look, color: string): Mannequin {
  const fur = look.fur ?? color, fur2 = look.fur2 ?? fur, b = look.build ?? 1;
  const anchor = new THREE.Group(), root = new THREE.Group();
  root.scale.setScalar(look.size ?? 0.3);          // satuan lokal = tinggi bahu
  anchor.add(root);
  const pelvis = joint(root, 0, 1.0);
  const J: Record<string, THREE.Object3D> = {};
  sph(pelvis, 0.27 * b, 0, 0, 0, fur);                                              // pinggul
  const trunk = add(pelvis, new THREE.CapsuleGeometry(0.25 * b, 0.5, 6, 12), fur, 0, 0.01, 0.22); trunk.rotation.x = Math.PI / 2;
  J.spine = joint(pelvis, 0, 0.02, 0.2);
  J.chest = joint(J.spine, 0, 0, 0.2); sph(J.chest, 0.25 * b, 0, 0, 0.05, fur);
  J.neck = joint(J.chest, 0, 0.12, 0.2); add(J.neck, new THREE.CapsuleGeometry(0.1, 0.12, 4, 8), fur, 0, 0.04, 0.05);
  J.head = joint(J.neck, 0, 0.12, 0.1); sph(J.head, 0.2, 0, 0.04, 0.1, fur);
  sph(J.head, 0.09, 0, -0.02, 0.27, fur2, 1, 0.8, 1); sph(J.head, 0.025, 0, 0.0, 0.35, "#2a1d1d");   // moncong + hidung
  for (const sx of [-1, 1]) {
    sph(J.head, 0.025, sx * 0.08, 0.1, 0.24, "#1b1b1b");                              // mata
    const ears = look.ears ?? "pointed";
    if (ears === "pointed") { const e = add(J.head, new THREE.ConeGeometry(0.075, 0.17, 4), fur, sx * 0.12, 0.25, 0.02); e.rotation.z = -sx * 0.18; }
    else if (ears === "round") sph(J.head, 0.07, sx * 0.13, 0.22, 0.02, fur, 1, 1, 0.5);
    else add(J.head, new THREE.CapsuleGeometry(0.05, 0.14, 4, 8), fur2, sx * 0.17, 0.12, 0.02);
  }
  const tailLen = ({ short: 0.22, medium: 0.45, long: 0.75 } as Record<string, number>)[look.tail ?? "medium"] ?? 0.45;
  J.tail = joint(pelvis, 0, 0.08, -0.28);
  const tail = add(J.tail, new THREE.CapsuleGeometry(0.045, tailLen, 4, 8), fur2, 0, 0, -tailLen / 2); tail.rotation.x = Math.PI / 2;
  const legs: [string, THREE.Object3D, number, number, number][] = [
    ["fl", J.chest, 0.17, -0.1, 0.05], ["fr", J.chest, -0.17, -0.1, 0.05], ["bl", pelvis, 0.17, -0.05, -0.02], ["br", pelvis, -0.17, -0.05, -0.02]];
  for (const [id, parent, x, y, z] of legs) {
    const hip = (J[`${id}_leg`] = joint(parent, x * b, y, z));
    add(hip, new THREE.CapsuleGeometry(0.07, 0.3, 4, 8), fur, 0, -0.21, 0);
    const kn = (J[`${id}_knee`] = joint(hip, 0, -0.43));
    add(kn, new THREE.CapsuleGeometry(0.06, 0.28, 4, 8), fur, 0, -0.2, 0);
    sph(kn, 0.08, 0, -0.42, 0.03, fur2, 1, 0.7, 1.3);                                // telapak
  }
  return { root: anchor, pelvis, joints: J };
}

export function buildMannequin(body: string, look: Look, color: string, label: string): Mannequin {
  const m = body === "quadruped" ? buildQuadruped(look, color) : buildHumanoid(look, color);
  const top = body === "quadruped" ? (look.size ?? 0.3) * 1.9 + 0.25 : (look.height ?? 1) * 1.95 + 0.1;
  m.root.add(nameTag(label, top));
  return m;
}

export function applyActor(m: Mannequin, s: ActorSample, body: string): void {
  m.root.position.set(...s.pos);
  m.root.rotation.set(0, s.facing * DEG, 0);
  m.pelvis.position.y = s.hipY;
  m.pelvis.rotation.set(s.rootRot[0] * DEG, s.rootRot[1] * DEG, s.rootRot[2] * DEG);
  for (const j of bodyDef(body).joints) {
    const r = s.joints[j];
    if (r && m.joints[j]) m.joints[j].rotation.set(r[0] * DEG, r[1] * DEG, r[2] * DEG);
  }
}

// ---------- lingkungan ----------
function gradientTexture(top: string, bottom: string): THREE.CanvasTexture {
  const c = document.createElement("canvas"); c.width = 2; c.height = 256;
  const g = c.getContext("2d")!;
  const grad = g.createLinearGradient(0, 0, 0, 256);
  grad.addColorStop(0, top); grad.addColorStop(1, bottom);
  g.fillStyle = grad; g.fillRect(0, 0, 2, 256);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** Pengaturan renderer yang sama untuk editor dan perekam previs: bayangan lembut + tone mapping film. */
export function configureRenderer(gl: THREE.WebGLRenderer): void {
  gl.shadowMap.enabled = true;
  gl.shadowMap.type = THREE.PCFSoftShadowMap;
  gl.toneMapping = THREE.ACESFilmicToneMapping;
  gl.toneMappingExposure = 1.0;
}

export interface WorldState { props: ResolvedProp[]; environment: Environment; bounds: [number, number] }
export interface BlockoutWorld {
  scene: THREE.Scene;
  actors: Map<string, Mannequin>;
  /** Bangun ulang bagian yang berubah (properti, lingkungan, aktor). */
  sync(state: WorldState, layout: Layout, names: Record<string, string>, looks: Record<string, Look>): void;
  /** Pasang semua pose/posisi pada waktu t. */
  poseAt(layout: Layout, t: number): void;
  setGrid(visible: boolean): void;
  dispose(): void;
}

const MAX_POINT_LIGHTS = 6;

export function createWorld(): BlockoutWorld {
  const scene = new THREE.Scene();
  const hemi = new THREE.HemisphereLight("#ffffff", "#3a3f4a", 1.0); scene.add(hemi);
  const sun = new THREE.DirectionalLight("#ffffff", 2); sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024); sun.shadow.bias = -0.0005;
  Object.assign(sun.shadow.camera, { left: -14, right: 14, top: 14, bottom: -14, near: 0.5, far: 60 });
  scene.add(sun, sun.target);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(120, 120), new THREE.MeshStandardMaterial({ color: "#5c7a45", roughness: 1 }));
  ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; scene.add(ground);
  const grid = new THREE.GridHelper(40, 40, "#5b6475", "#3b4250");
  (grid.material as THREE.Material).opacity = 0.35; (grid.material as THREE.Material).transparent = true;
  scene.add(grid);
  const propGroup = new THREE.Group(); scene.add(propGroup);
  const lights: THREE.PointLight[] = [];
  const actors = new Map<string, Mannequin>();
  const sig = { props: "", env: "", actors: "" };

  function applyEnv(env: Environment): void {
    const t = VOCAB.times[env.time ?? "siang"] ?? VOCAB.times.siang, wth = VOCAB.weather[env.weather ?? "cerah"] ?? VOCAB.weather.cerah;
    if (scene.background instanceof THREE.Texture) scene.background.dispose();
    scene.background = gradientTexture(t.sky_top, t.sky_bottom);
    scene.fog = new THREE.FogExp2(t.fog, t.fog_density * wth.fog_mul);
    hemi.color.set(t.sky_bottom); hemi.groundColor.set(t.ground); hemi.intensity = t.ambient * wth.dim;
    sun.color.set(t.sun_color); sun.intensity = t.sun_intensity * wth.dim; sun.position.set(...(t.sun_dir.map((v) => v * 3) as Vec3));
    (ground.material as THREE.MeshStandardMaterial).color.set(t.ground);
    for (const l of lights) l.intensity = (l.userData.base as number) * (env.time === "malam" || env.time === "senja" ? 1 : 0.15);
  }

  return {
    scene, actors,
    sync(state, layout, names, looks) {
      const ps = JSON.stringify(state.props);
      if (ps !== sig.props) {
        sig.props = ps;
        propGroup.clear();
        lights.splice(0).forEach((l) => scene.remove(l));
        for (const p of state.props) {
          const g = buildProp(p);
          propGroup.add(g);
          const L = g.userData.light as { y: number; color: string; intensity: number; dx?: number } | undefined;
          if (L && lights.length < MAX_POINT_LIGHTS) {
            const pl = new THREE.PointLight(L.color, L.intensity, 8, 1.6);
            pl.position.set(p.pos[0] + (L.dx ?? 0), p.pos[1] + L.y, p.pos[2]); pl.userData.base = L.intensity;
            scene.add(pl); lights.push(pl);
          }
        }
        sig.env = "";   // intensitas lampu bergantung waktu: terapkan ulang
      }
      const es = JSON.stringify([state.environment, state.bounds]);
      if (es !== sig.env) {
        sig.env = es; applyEnv(state.environment);
        ground.scale.setScalar(Math.max(1, Math.max(...state.bounds) / 40));
      }
      const as = JSON.stringify([layout.actors.map((a: Actor) => [a.character_id, a.body]), names, looks]);
      if (as !== sig.actors) {
        sig.actors = as;
        for (const m of actors.values()) scene.remove(m.root);
        actors.clear();
        layout.actors.forEach((a, i) => {
          const m = buildMannequin(a.body, looks[a.character_id] ?? {}, ACTOR_COLORS[i % ACTOR_COLORS.length], names[a.character_id] ?? "?");
          scene.add(m.root); actors.set(a.character_id, m);
        });
      }
    },
    poseAt(layout, t) {
      for (const a of layout.actors) { const m = actors.get(a.character_id); if (m) applyActor(m, sampleActor(a, t), a.body); }
    },
    setGrid(v) { grid.visible = v; },
    dispose() {
      scene.traverse((o) => {
        const mesh = o as THREE.Mesh;
        mesh.geometry?.dispose();
        const mat = mesh.material;
        if (mat && !Array.isArray(mat)) mat.dispose();
      });
      if (scene.background instanceof THREE.Texture) scene.background.dispose();
      matCache.clear();
    },
  };
}
