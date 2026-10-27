import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    parent_image_id TEXT,
    kind TEXT NOT NULL,            -- upload | edit | frame
    prompt TEXT,
    model TEXT,
    path TEXT NOT NULL,
    width INTEGER, height INTEGER,
    cost REAL,
    estimated_cost REAL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS refs (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    source_clip_id TEXT,           -- bila berasal dari klip library: URL publik dari OpenRouter
    duration REAL NOT NULL,
    width INTEGER NOT NULL, height INTEGER NOT NULL,
    has_audio INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    source_image_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS character_images (
    character_id TEXT NOT NULL,
    image_id TEXT NOT NULL,
    label TEXT NOT NULL,           -- source | front | side | three_quarter | full_body | custom
    PRIMARY KEY (character_id, image_id)
);
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);
CREATE TABLE IF NOT EXISTS films (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    clip_ids TEXT NOT NULL DEFAULT '[]',     -- JSON: urutan adegan (id klip; duplikat diperbolehkan)
    merged_path TEXT,
    rendered_ids TEXT,                       -- JSON: urutan saat render terakhir; beda dengan clip_ids = hasil basi
    render_status TEXT NOT NULL DEFAULT 'idle',   -- idle | rendering | done | failed
    render_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS film_characters (   -- pemeran episode (plan 15); adegan memilih dari daftar ini
    film_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (film_id, character_id)
);
CREATE TABLE IF NOT EXISTS film_locations (
    film_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (film_id, location_id)
);
CREATE TABLE IF NOT EXISTS text_jobs (   -- panggilan model teks (plan 14); biayanya ikut anggaran harian
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    model TEXT NOT NULL,
    cost REAL,
    estimated_cost REAL,
    scene_id TEXT,
    workspace_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS locations (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outfits (
    id TEXT PRIMARY KEY,
    character_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image_id TEXT,                 -- gambar karakter yang sudah memakai baju ini; kosong = tampilan teks saja
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scenes (
    id TEXT PRIMARY KEY,
    film_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    location_id TEXT,
    time_of_day TEXT NOT NULL DEFAULT '',
    camera TEXT NOT NULL DEFAULT '',
    dialogue TEXT NOT NULL DEFAULT '',
    extra_prompt TEXT NOT NULL DEFAULT '',
    keyframe_image_id TEXT,
    clip_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scene_cast (
    scene_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    outfit_id TEXT,
    action TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL,
    PRIMARY KEY (scene_id, character_id)
);
CREATE TABLE IF NOT EXISTS voice_versions (   -- suara karakter berversi (plan 18); aktif = characters.voice_id
    id TEXT PRIMARY KEY,
    character_id TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    path TEXT,                     -- sampel suara .m4a; kosong = hanya deskripsi
    duration REAL,
    source TEXT NOT NULL,          -- upload | text
    consent INTEGER NOT NULL DEFAULT 0,
    revision_note TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scene_beats (   -- ketukan adegan (plan 18): rentang detik, aksi, kamera, pemeran, dialog, gambar acuan
    id TEXT PRIMARY KEY,
    scene_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    start REAL NOT NULL, end REAL NOT NULL,
    action TEXT NOT NULL DEFAULT '',
    camera TEXT NOT NULL DEFAULT '',
    cast TEXT NOT NULL DEFAULT '[]',       -- JSON: [character_id]
    dialogue TEXT NOT NULL DEFAULT '[]',   -- JSON: [{character_id, text}]
    image_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scene_beats_scene ON scene_beats (scene_id, position);
CREATE TABLE IF NOT EXISTS beat_versions (   -- potret susunan beat sebelum tiap penggantian
    id TEXT PRIMARY KEY,
    scene_id TEXT NOT NULL,
    beats TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    parent_clip_id TEXT,
    source_image_id TEXT,
    prompt TEXT NOT NULL,
    model TEXT NOT NULL,
    params TEXT NOT NULL,          -- JSON
    status TEXT NOT NULL,          -- submitted | in_progress | completed | failed | failed_download
    remote_job_id TEXT,
    path TEXT,
    merged_path TEXT,
    cost REAL,
    estimated_cost REAL,
    error TEXT,
    chain_depth INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT UNIQUE,
    kind TEXT NOT NULL DEFAULT 'i2v',
    reference_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS comic_panels (   -- panel komik (plan 21): gambar AI + balon overlay
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    character_ids TEXT NOT NULL DEFAULT '[]',   -- JSON: [character_id] berurutan
    location_id TEXT,
    shot TEXT NOT NULL DEFAULT 'MS',
    angle TEXT NOT NULL DEFAULT 'eye',
    aspect_ratio TEXT NOT NULL DEFAULT '4:3',
    comic_style TEXT NOT NULL DEFAULT 'project',
    bubbles TEXT NOT NULL DEFAULT '[]',         -- JSON: [{id, kind, character_id, text, x, y, w, h, tail_x, tail_y}] relatif 0..1
    image_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comic_panels_ws ON comic_panels (workspace_id, created_at);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _Tx:
    """Operasi di dalam `Database.transaction()`: tanpa commit/kunci sendiri."""

    def __init__(self, conn: sqlite3.Connection):
        self._c = conn

    def execute(self, sql: str, args: tuple = ()) -> None:
        self._c.execute(sql, args)

    def one(self, sql: str, args: tuple = ()) -> dict[str, Any] | None:
        row = self._c.execute(sql, args).fetchone()
        return dict(row) if row else None

    def all(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self._c.execute(sql, args).fetchall()]

    def insert(self, table: str, values: dict[str, Any]) -> None:
        cols = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        self._c.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(values.values()))


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._migrate()

    def _migrate(self) -> None:
        """Migrasi bernomor lewat PRAGMA user_version (CREATE IF NOT EXISTS tidak mengubah tabel lama)."""
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 2:   # v2: kolom estimated_cost (plan 04)
            for table in ("images", "clips"):
                cols = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}
                if "estimated_cost" not in cols:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN estimated_cost REAL")
            self._conn.execute("PRAGMA user_version = 2")
        if version < 3:   # v3: tabel characters/character_images dibuat oleh SCHEMA (IF NOT EXISTS)
            self._conn.execute("PRAGMA user_version = 3")
        if version < 4:   # v4: klip motion (kind, reference_id); tabel refs dibuat oleh SCHEMA
            cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(clips)")}
            if "kind" not in cols:
                self._conn.execute("ALTER TABLE clips ADD COLUMN kind TEXT NOT NULL DEFAULT 'i2v'")
            if "reference_id" not in cols:
                self._conn.execute("ALTER TABLE clips ADD COLUMN reference_id TEXT")
            self._conn.execute("PRAGMA user_version = 4")
        if version < 5:   # v5: durasi klip (detik, dari ffprobe) untuk total durasi storyboard; tabel films dibuat oleh SCHEMA
            cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(clips)")}
            if "duration" not in cols:
                self._conn.execute("ALTER TABLE clips ADD COLUMN duration REAL")
            self._conn.execute("PRAGMA user_version = 5")
        if version < 6:   # v6: soft delete (deleted_at); baris tetap ada supaya catatan biaya/batas harian tidak hilang
            for table in ("images", "clips"):
                cols = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}
                if "deleted_at" not in cols:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN deleted_at TEXT")
            self._conn.execute("PRAGMA user_version = 6")
        if version < 7:   # v7: workspace (plan 07). Semua data lama masuk workspace "Utama" (id "main").
            stamp = now()
            self._conn.execute("INSERT OR IGNORE INTO workspaces (id, name, created_at, updated_at) VALUES ('main', 'Utama', ?, ?)",
                               (stamp, stamp))
            for table in ("images", "clips", "characters", "films", "refs"):
                cols = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}
                if "workspace_id" not in cols:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN workspace_id TEXT")
                self._conn.execute(f"UPDATE {table} SET workspace_id = 'main' WHERE workspace_id IS NULL")
            cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(images)")}
            if "origin_image_id" not in cols:   # asal salinan lintas workspace
                self._conn.execute("ALTER TABLE images ADD COLUMN origin_image_id TEXT")
            for table in ("images", "clips", "characters", "films"):   # daftar per workspace diurutkan created_at
                self._conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_ws ON {table} (workspace_id, created_at)")
            self._conn.execute("PRAGMA user_version = 7")
        if version < 8:   # v8: workspace terhapus menjadi tombstone (aset dan catatan biaya tetap menunjuknya)
            cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(workspaces)")}
            if "deleted_at" not in cols:
                self._conn.execute("ALTER TABLE workspaces ADD COLUMN deleted_at TEXT")
            self._conn.execute("PRAGMA user_version = 8")
        if version < 9:   # v9: episode + adegan (plan 08). Tabel baru dibuat oleh SCHEMA; film lama -> episode, tiap klipnya -> satu adegan
            cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(films)")}
            for name, ddl in (("number", "INTEGER"), ("synopsis", "TEXT NOT NULL DEFAULT ''"),
                              ("aspect_ratio", "TEXT NOT NULL DEFAULT '16:9'")):
                if name not in cols:
                    self._conn.execute(f"ALTER TABLE films ADD COLUMN {name} {ddl}")
            films = self._conn.execute("SELECT id, clip_ids FROM films WHERE number IS NULL ORDER BY created_at, rowid").fetchall()
            for n, film in enumerate(films, 1):
                self._conn.execute("UPDATE films SET number = ? WHERE id = ?", (n, film["id"]))
                for pos, clip_id in enumerate(json.loads(film["clip_ids"] or "[]")):
                    alive = self._conn.execute("SELECT 1 FROM clips WHERE id = ? AND deleted_at IS NULL", (clip_id,)).fetchone()
                    stamp = now()   # klip yang sudah terhapus tetap jadi adegan (tanpa video): urutan film lama tidak berubah
                    self._conn.execute(
                        "INSERT INTO scenes (id, film_id, position, clip_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (uuid.uuid4().hex, film["id"], pos, clip_id if alive else None, stamp, stamp))
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_scenes_film ON scenes (film_id, position)")
            self._conn.execute("PRAGMA user_version = 9")
        if version < 10:   # v10: durasi rencana per adegan + hasil generate menunjuk adegannya (daftar take)
            for table, col, ddl in (("scenes", "planned_seconds", "INTEGER"), ("images", "scene_id", "TEXT"), ("clips", "scene_id", "TEXT")):
                cols = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}
                if col not in cols:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
            self._conn.execute("PRAGMA user_version = 10")
        if version < 11:   # v11: blockout 3D per adegan (plan 14); tabel text_jobs dibuat oleh SCHEMA
            cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(scenes)")}
            for col in ("blockout", "blockout_image_id", "previs_ref_id"):
                if col not in cols:
                    self._conn.execute(f"ALTER TABLE scenes ADD COLUMN {col} TEXT")
            self._conn.execute("PRAGMA user_version = 11")
        if version < 12:   # v12: alur episode (plan 15): naskah, pemeran/latar episode. Isi awal dari adegan yang sudah ada (idempoten)
            for table, col, ddl in (("films", "script", "TEXT NOT NULL DEFAULT ''"), ("films", "script_split_hash", "TEXT"),
                                    ("films", "previs_skipped", "INTEGER NOT NULL DEFAULT 0"), ("scenes", "script_excerpt", "TEXT")):
                cols = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}
                if col not in cols:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
            for film in self._conn.execute("SELECT id FROM films").fetchall():
                chars = list(dict.fromkeys(r[0] for r in self._conn.execute(   # urutan kemunculan pertama
                    "SELECT sc.character_id FROM scene_cast sc JOIN scenes s ON s.id = sc.scene_id WHERE s.film_id = ? "
                    "ORDER BY s.position, sc.position", (film["id"],))))
                locs = list(dict.fromkeys(r[0] for r in self._conn.execute(
                    "SELECT location_id FROM scenes WHERE film_id = ? AND location_id IS NOT NULL ORDER BY position", (film["id"],))))
                for pos, cid in enumerate(chars):
                    self._conn.execute("INSERT OR IGNORE INTO film_characters VALUES (?, ?, ?)", (film["id"], cid, pos))
                for pos, lid in enumerate(locs):
                    self._conn.execute("INSERT OR IGNORE INTO film_locations VALUES (?, ?, ?)", (film["id"], lid, pos))
            self._conn.execute("PRAGMA user_version = 12")
        if version < 13:   # v13: set latar + penampilan karakter dibuat AI (plan 17)
            for table, col in (("locations", "set_layout"), ("characters", "look"), ("characters", "look_hash")):
                cols = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}
                if col not in cols:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
            self._conn.execute("PRAGMA user_version = 13")
        if version < 14:   # v14: pengaturan proyek (= workspace), kolom revisi/hash/beat untuk Storyboard v2 (plan 18)
            for table, col, ddl in (
                    ("workspaces", "video_model", "TEXT NOT NULL DEFAULT 'bytedance/seedance-2.0'"),
                    ("workspaces", "video_resolution", "TEXT NOT NULL DEFAULT '720p'"),
                    ("workspaces", "aspect_ratio", "TEXT NOT NULL DEFAULT '16:9'"),
                    ("workspaces", "generate_audio", "INTEGER NOT NULL DEFAULT 1"),
                    ("workspaces", "image_model", "TEXT"),
                    ("workspaces", "style", "TEXT NOT NULL DEFAULT ''"),
                    ("images", "beat_id", "TEXT"), ("images", "revision_note", "TEXT"), ("images", "input_hash", "TEXT"),
                    ("clips", "revision_note", "TEXT"), ("clips", "input_hash", "TEXT")):
                cols = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}
                if col not in cols:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
            for ws in self._conn.execute("SELECT id FROM workspaces").fetchall():   # rasio proyek = rasio episode terbanyak (seri: yang terbaru)
                top = self._conn.execute(
                    "SELECT aspect_ratio FROM films WHERE workspace_id = ? GROUP BY aspect_ratio "
                    "ORDER BY COUNT(*) DESC, MAX(created_at) DESC LIMIT 1", (ws["id"],)).fetchone()
                if top:
                    self._conn.execute("UPDATE workspaces SET aspect_ratio = ? WHERE id = ?", (top["aspect_ratio"], ws["id"]))
            self._conn.execute("PRAGMA user_version = 14")
        if version < 15:   # v15: versi suara aktif per karakter (plan 18); tabel voice_versions/scene_beats/beat_versions dibuat oleh SCHEMA
            cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(characters)")}
            if "voice_id" not in cols:
                self._conn.execute("ALTER TABLE characters ADD COLUMN voice_id TEXT")
            self._conn.execute("PRAGMA user_version = 15")
        if version < 16:   # v16: format prompt shot Seedance (plan 18 Revisi 4): ukuran + lensa per beat, genre proyek
            for table, col in (("scene_beats", "size"), ("scene_beats", "lens"), ("workspaces", "genre")):
                if col not in {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
            self._conn.execute("PRAGMA user_version = 16")
        if version < 17:   # v17: prompt adegan = sumber tunggal Storyboard v2 (plan 18 Revisi 8); NULL = render dari data
            if "prompt" not in {r["name"] for r in self._conn.execute("PRAGMA table_info(scenes)")}:
                self._conn.execute("ALTER TABLE scenes ADD COLUMN prompt TEXT")
            self._conn.execute("PRAGMA user_version = 17")
        if version < 18:   # v18: adegan ke-2 dst. bisa mulai dari frame akhir adegan sebelumnya (plan 18 Revisi 9)
            if "start_from_prev" not in {r["name"] for r in self._conn.execute("PRAGMA table_info(scenes)")}:
                self._conn.execute("ALTER TABLE scenes ADD COLUMN start_from_prev INTEGER NOT NULL DEFAULT 0")
            self._conn.execute("PRAGMA user_version = 18")
        if version < 19:   # v19: adegan sumber frame awal dipilih (plan 18 Revisi 11); menggantikan boolean start_from_prev
            if "start_from_scene_id" not in {r["name"] for r in self._conn.execute("PRAGMA table_info(scenes)")}:
                self._conn.execute("ALTER TABLE scenes ADD COLUMN start_from_scene_id TEXT")
            self._conn.execute(   # data lama: "adegan sebelumnya" menjadi id adegan tepat sebelumnya di episode yang sama
                "UPDATE scenes SET start_from_scene_id = (SELECT p.id FROM scenes p WHERE p.film_id = scenes.film_id AND p.position = scenes.position - 1) "
                "WHERE start_from_prev = 1")
            self._conn.execute("PRAGMA user_version = 19")
        if version < 20:   # v20: panel komik (plan 21); tabel comic_panels dibuat oleh SCHEMA, take = images.panel_id
            if "panel_id" not in {r["name"] for r in self._conn.execute("PRAGMA table_info(images)")}:
                self._conn.execute("ALTER TABLE images ADD COLUMN panel_id TEXT")
            self._conn.execute("PRAGMA user_version = 20")
        self._conn.commit()

    def execute(self, sql: str, args: tuple = ()) -> None:
        with self._lock:
            self._conn.execute(sql, args)
            self._conn.commit()

    def one(self, sql: str, args: tuple = ()) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(sql, args).fetchone()
        return dict(row) if row else None

    def all(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    def insert(self, table: str, values: dict[str, Any]) -> None:
        cols = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        self.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(values.values()))

    def update(self, table: str, id_: str, values: dict[str, Any]) -> None:
        sets = ", ".join(f"{k} = ?" for k in values)
        self.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*values.values(), id_))

    @contextmanager
    def transaction(self):
        """Beberapa penulisan sebagai satu unit: commit sekali di akhir, rollback bila ada galat.
        Memegang kunci database selama berlangsung, jadi di dalamnya pakai `tx`, bukan `self`."""
        with self._lock:
            tx = _Tx(self._conn)
            try:
                yield tx
            except BaseException:
                self._conn.rollback()
                raise
            self._conn.commit()

    def committed_today(self) -> float:
        """Biaya aktual hari ini; job yang belum punya biaya aktual dihitung dengan estimasinya."""
        day = datetime.now(timezone.utc).date().isoformat()
        clips = self.one(
            "SELECT COALESCE(SUM(COALESCE(cost, CASE WHEN status = 'failed' THEN 0 ELSE estimated_cost END, 0)), 0) AS s "
            "FROM clips WHERE created_at >= ?", (day,))["s"]
        images = self.one(
            "SELECT COALESCE(SUM(COALESCE(cost, estimated_cost, 0)), 0) AS s FROM images WHERE created_at >= ?",
            (day,))["s"]
        texts = self.one("SELECT COALESCE(SUM(COALESCE(cost, estimated_cost, 0)), 0) AS s FROM text_jobs WHERE created_at >= ?",
                         (day,))["s"]
        return clips + images + texts

    spent_today = committed_today
