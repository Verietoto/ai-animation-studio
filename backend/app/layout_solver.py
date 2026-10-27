"""Pemecah tata letak deterministik untuk blockout 3D (plan 17): murni Python, tanpa DB/HTTP.

AI menulis RELASI (di lantai, di atas objek lain, menempel dinding, dekat objek); modul ini menghitung koordinat sebenarnya supaya tidak
ada benda melayang, saling tembus, atau di luar area, dan memastikan semua aktor masuk bingkai kamera pada t=0. Urutan kerja:
1) objek lantai (`pos`/`against`/`at`/`near`), 2) dorong objek padat yang bertabrakan (aktor ikut jadi penghalang), 3) objek `on`
mengikuti induknya, 4) lansiran sisa tabrakan. Hasil sama untuk masukan sama (tanpa acak).
"""
import math

from . import vocab

DEFAULT_BOUNDS = (14.0, 12.0)   # lebar (sumbu x) dan dalam (sumbu z), meter
MARGIN = 0.02                   # jarak minimum antar benda padat (2 cm)
ITERATIONS = 80
ACTOR_HALF = 0.4                # jejak aktor sebagai penghalang (kotak 0,8 m)
NOT_SOLID = {"wall", "road", "plane", "window", "door", "sign"}
WALL_ROT = {"north": 0.0, "south": 180.0, "east": 270.0, "west": 90.0}   # depan benda menghadap ke tengah area


def dims_of(p: dict) -> list[float]:
    """Ukuran akhir (lebar, tinggi, dalam) dalam meter: ukuran dasar objek/bentuk x skala."""
    pre = vocab.prefabs().get(p["type"])
    base = list(pre["size"]) if pre else list(p.get("size", [1, 1, 1]))
    if p["type"] == "plane":
        base[2] = 0.02
    s = p.get("scale", 1)
    sx, sy, sz = (s, s, s) if isinstance(s, (int, float)) else s
    return [base[0] * sx, base[1] * sy, base[2] * sz]


def half_extent(dims: list[float], rot_y: float) -> tuple[float, float]:
    a = math.radians(rot_y)
    c, s = abs(math.cos(a)), abs(math.sin(a))
    return (dims[0] * c + dims[2] * s) / 2, (dims[0] * s + dims[2] * c) / 2


class _Obj:
    def __init__(self, p: dict, layer: str):
        self.p, self.layer, self.id = p, layer, p["id"]
        self.dims = dims_of(p)
        self.rot_y = float(p.get("rot", [0, 0, 0])[1])
        pre = vocab.prefabs().get(p["type"], {})
        self.elev = float(pre.get("elevation", 0.0))
        self.top = bool(pre.get("top", p["type"] in ("box", "cylinder")))
        self.solid = p["type"] not in NOT_SOLID and self.elev == 0.0 and not pre.get("walkable")
        self.x = self.y = self.z = 0.0
        self.fixed, self.lock, self.placed = False, None, False

    def half(self) -> tuple[float, float]:
        return half_extent(self.dims, self.rot_y)


def solve(set_objects: list[dict], scene_props: list[dict], actor_xz: list[tuple[float, float]] | None = None,
          bounds: tuple[float, float] | None = None) -> tuple[list[dict], list[str]]:
    """Gabungkan objek set (layer `set`) dan properti adegan (layer `scene`), lalu hitung posisi/rotasi/ukuran absolut.

    Mengembalikan (daftar properti dengan `pos`, `rot`, `dims`, `layer`, peringatan). Id harus unik di dua lapisan (pemanggil menjamin)."""
    warnings: list[str] = []
    w, d = bounds or DEFAULT_BOUNDS
    objs = [_Obj(p, "set") for p in set_objects] + [_Obj(p, "scene") for p in scene_props]
    by_id = {o.id: o for o in objs}

    def wall_pos(o: _Obj, wall: str) -> None:
        o.rot_y = WALL_ROT[wall]
        hx, hz = o.half()
        off = float(o.p.get("offset", 0.0))
        if wall in ("north", "south"):
            o.x, o.z, o.lock = off, (-d / 2 + hz if wall == "north" else d / 2 - hz), "x"
        else:
            o.x, o.z, o.lock = (w / 2 - hx if wall == "east" else -w / 2 + hx), off, "z"
        o.y, o.placed = o.elev, True

    # 1) objek lantai
    for o in objs:
        p = o.p
        if "pos" in p:
            o.x, o.y, o.z = p["pos"]
            o.fixed = o.placed = True
        elif "against" in p:
            wall_pos(o, p["against"])
        elif "at" in p:
            o.x, o.z, o.y, o.placed = p["at"][0], p["at"][1], o.elev, True
    near_count: dict[str, int] = {}
    pending = [o for o in objs if "near" in o.p]
    for _ in range(len(pending) + 1):
        left = []
        for o in pending:
            t = by_id.get(o.p["near"])
            if t is None or not t.placed:
                left.append(o)
                continue
            k = near_count.get(t.id, 0)
            near_count[t.id] = k + 1
            ang = math.radians(float(o.p.get("angle", 40.0 * k)))
            dist = float(o.p.get("dist", max(t.half()) + max(o.half()) + 0.25))
            o.x, o.z, o.y, o.placed = t.x + dist * math.sin(ang), t.z + dist * math.cos(ang), o.elev, True
        pending = left
        if not pending:
            break
    for o in pending:
        warnings.append(f"{o.id}: target 'near' tidak bisa ditempatkan, ditaruh di tengah")
        o.x = o.z = 0.0
        o.y, o.placed = o.elev, True

    # 2) tabrakan benda padat di lantai (objek `on` ikut induknya nanti)
    floor = [o for o in objs if o.solid and "on" not in o.p]
    obstacles = []
    for n, (ax, az) in enumerate(actor_xz or []):
        a = _Obj({"id": f"actor{n}", "type": "box", "size": [2 * ACTOR_HALF, 1.7, 2 * ACTOR_HALF], "rot": [0, 0, 0]}, "actor")
        a.x, a.z, a.fixed, a.placed = ax, az, True, True
        obstacles.append(a)
    group = floor + obstacles

    def movable(o: _Obj, axis: str) -> bool:
        return not o.fixed and (o.lock is None or o.lock == axis)

    def clamp(o: _Obj) -> None:
        if o.fixed or o.p["type"] == "road":
            return
        hx, hz = o.half()
        if o.lock != "z":
            o.x = max(-w / 2 + hx, min(w / 2 - hx, o.x))
        if o.lock != "x":
            o.z = max(-d / 2 + hz, min(d / 2 - hz, o.z))

    def overlap(a: _Obj, b: _Obj):
        ahx, ahz = a.half()
        bhx, bhz = b.half()
        dx, dz = a.x - b.x, a.z - b.z
        ox, oz = ahx + bhx + MARGIN - abs(dx), ahz + bhz + MARGIN - abs(dz)
        return (ox, oz, dx, dz) if ox > 0 and oz > 0 else None

    for _ in range(ITERATIONS):
        moved = False
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a.fixed and b.fixed:
                    continue
                ov = overlap(a, b)
                if ov is None:
                    continue
                ox, oz, dx, dz = ov
                for axis, amount, delta in sorted((("x", ox, dx), ("z", oz, dz)), key=lambda t: t[1]):
                    ca, cb = movable(a, axis), movable(b, axis)
                    if not (ca or cb):
                        continue
                    sign = 1.0 if delta >= 0 else -1.0
                    share = amount / 2 if (ca and cb) else amount
                    for o, s in ((a, sign), (b, -sign)):
                        if movable(o, axis):
                            if axis == "x":
                                o.x += s * share
                            else:
                                o.z += s * share
                    moved = True
                    break
        for o in floor:
            clamp(o)
        if not moved:
            break
    for i in range(len(group)):
        for j in range(i + 1, len(group)):
            a, b = group[i], group[j]
            if a.fixed and b.fixed:
                continue
            ov = overlap(a, b)
            if ov and min(ov[0], ov[1]) > MARGIN + 0.02:
                warnings.append(f"{a.id} dan {b.id} masih bertumpuk")

    # 3) objek `on` mengikuti induknya (bertingkat)
    todo = [o for o in objs if "on" in o.p]
    for _ in range(len(todo) + 1):
        left = []
        for o in todo:
            par = by_id.get(o.p["on"])
            if par is None or not par.placed:
                left.append(o)
                continue
            hx, hz = par.half()
            if not par.top:
                o.x, o.z, o.y = par.x + hx + max(o.half()) + 0.1, par.z, o.elev
                warnings.append(f"{o.id}: {par.id} tidak punya permukaan datar, diletakkan di sampingnya")
            else:
                ohx, ohz = o.half()
                lim_x, lim_z = max(hx - ohx, 0.0), max(hz - ohz, 0.0)
                o.x = par.x + max(-lim_x, min(lim_x, float(o.p.get("dx", 0.0))))
                o.z = par.z + max(-lim_z, min(lim_z, float(o.p.get("dz", 0.0))))
                o.y = par.y + par.dims[1]
            o.placed = True
        todo = left
        if not todo:
            break
    for o in todo:
        warnings.append(f"{o.id}: induk 'on' tidak bisa ditempatkan, ditaruh di lantai")
        o.x = o.z = 0.0
        o.y, o.placed = o.elev, True

    out = []
    for o in objs:
        rot = list(o.p.get("rot", [0, 0, 0]))
        rot[1] = round(o.rot_y, 3)
        out.append({**o.p, "pos": [round(o.x, 3), round(o.y, 3), round(o.z, 3)], "rot": rot,
                    "dims": [round(v, 3) for v in o.dims], "layer": o.layer})
    return out, warnings


def frame_actors(camera_keys: list[dict], actor_points: list[tuple[float, float]], aspect: float) -> tuple[list[dict], list[str]]:
    """Pastikan setiap aktor (titik setinggi dada) terlihat pada key kamera pertama: mundurkan kamera, lalu lebarkan lensa."""
    keys = [dict(k) for k in camera_keys]
    if not keys or not actor_points:
        return keys, []
    first = keys[0]

    def visible(pos, target, mm) -> bool:
        f = [target[i] - pos[i] for i in range(3)]
        n = math.sqrt(sum(v * v for v in f)) or 1.0
        f = [v / n for v in f]
        rn = math.sqrt(f[2] ** 2 + f[0] ** 2)
        if rn < 1e-6:
            return False
        r = [f[2] / rn, 0.0, -f[0] / rn]   # kanan = cross(f, up) dengan up = (0,1,0)
        u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]]
        vfov = math.radians(vocab.fov_for(mm, aspect))
        hfov = 2 * math.atan(math.tan(vfov / 2) * aspect)
        for ax, az in actor_points:
            v = [ax - pos[0], 1.0 - pos[1], az - pos[2]]
            depth = sum(v[i] * f[i] for i in range(3))
            if depth <= 0.2:
                return False
            if abs(sum(v[i] * r[i] for i in range(3)) / (depth * math.tan(hfov / 2))) > 0.95:
                return False
            if abs(sum(v[i] * u[i] for i in range(3)) / (depth * math.tan(vfov / 2))) > 0.95:
                return False
        return True

    pos, target, mm = list(first["pos"]), list(first["target"]), float(first["mm"])
    if visible(pos, target, mm):
        return keys, []
    warnings = []
    for _ in range(4):                    # mundurkan kamera 25% per langkah
        pos = [target[i] + (pos[i] - target[i]) * 1.25 for i in range(3)]
        if visible(pos, target, mm):
            break
    else:
        for _ in range(3):                # lalu lebarkan lensa
            mm = max(14.0, mm * 0.8)
            if visible(pos, target, mm):
                break
    if not visible(pos, target, mm):      # terakhir: arahkan tatapan ke pusat aktor
        cx = sum(p[0] for p in actor_points) / len(actor_points)
        cz = sum(p[1] for p in actor_points) / len(actor_points)
        target = [cx, 1.0, cz]
        if not visible(pos, target, mm):
            warnings.append("tidak semua tokoh masuk bingkai kamera pada awal adegan; periksa kamera")
    first["pos"], first["target"], first["mm"] = [round(v, 3) for v in pos], [round(v, 3) for v in target], round(mm, 1)
    warnings.append("kamera pertama disesuaikan agar semua tokoh masuk bingkai")
    return keys, warnings
