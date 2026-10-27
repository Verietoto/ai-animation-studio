import { useCallback, useEffect, useRef, useState } from "react";
import { Plus, X } from "lucide-react";
import { Character, CastIn, Scene } from "../api";

/** Kolom teks dengan simpan otomatis: jeda 600 ms setelah berhenti mengetik, saat fokus lepas, dan saat dilepas dari layar.
 *  Bila simpan gagal, teks tetap di kolom (tidak ditimpa nilai server) supaya tidak hilang. */
export function SaveText({ value, onSave, multiline, rows = 3, maxLength, placeholder, label, list, onEnter, className, autoFocus }: {
  value: string; onSave: (v: string) => Promise<unknown>; multiline?: boolean; rows?: number; maxLength?: number;
  placeholder?: string; label: string; list?: string; onEnter?: () => void; className?: string; autoFocus?: boolean;
}) {
  const [text, setText] = useState(value);
  const dirty = useRef(false);
  const latest = useRef(value);
  const timer = useRef<number | undefined>(undefined);
  const save = useRef(onSave);
  save.current = onSave;

  useEffect(() => { if (!dirty.current) { setText(value); latest.current = value; } }, [value]);
  const flush = useCallback(() => {
    window.clearTimeout(timer.current);
    if (!dirty.current) return;
    dirty.current = false;
    save.current(latest.current).catch(() => { dirty.current = true; });
  }, []);
  useEffect(() => flush, [flush]);   // dilepas dari layar (ganti halaman/adegan) = simpan dulu

  const change = (next: string) => {
    setText(next); latest.current = next; dirty.current = true;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(flush, 600);
  };
  const common = { value: text, maxLength, placeholder, "aria-label": label, className, autoFocus, onBlur: flush };
  return multiline
    ? <textarea {...common} rows={rows} onChange={(e) => change(e.target.value)} />
    : <input {...common} list={list} onChange={(e) => change(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && onEnter) { e.preventDefault(); flush(); onEnter(); } }} />;
}

const MAX_CAST = 3;

/** Pemeran adegan: karakter + tampilan + aksi. Keadaan lokal adalah sumber kebenaran selama diedit,
 *  jadi dua ketikan cepat tidak saling menimpa; komponen dibuat ulang (key) saat pindah adegan. */
export function CastEditor({ scene, characters, onSave, locked }: {
  scene: Scene; characters: Character[]; onSave: (cast: CastIn[]) => Promise<unknown>; locked?: boolean;
}) {
  const [rows, setRows] = useState<CastIn[]>(() => scene.cast.map((c) => ({ character_id: c.character_id, outfit_id: c.outfit_id, action: c.action })));
  const ref = useRef(rows);
  const commit = (next: CastIn[]) => { ref.current = next; setRows(next); return onSave(next); };
  const byId = (id: string) => characters.find((c) => c.id === id);
  const free = characters.filter((c) => !rows.some((r) => r.character_id === c.id));
  return (
    <div className="cast">
      {rows.map((r) => {
        const ch = byId(r.character_id);
        return (
          <div className="cast-row" key={r.character_id}>
            <div className="cast-head">
              <strong className="clamp1">{ch?.name ?? scene.cast.find((c) => c.character_id === r.character_id)?.character_name ?? "?"}</strong>
              <select value={r.outfit_id ?? ""} aria-label={`Tampilan ${ch?.name ?? ""}`} disabled={locked}
                onChange={(e) => void commit(ref.current.map((x) => x.character_id === r.character_id ? { ...x, outfit_id: e.target.value || null } : x)).catch(() => {})}>
                <option value="">(tampilan bawaan)</option>
                {(ch?.outfits ?? []).map((o) => <option key={o.id} value={o.id}>{o.name}{o.image_id ? "" : " (teks)"}</option>)}
              </select>
              <button className="btn ghost sm" aria-label={`Lepas ${ch?.name ?? "pemeran"}`} disabled={locked}
                onClick={() => void commit(ref.current.filter((x) => x.character_id !== r.character_id)).catch(() => {})}><X size={13} /></button>
            </div>
            <SaveText label={`Aksi ${ch?.name ?? ""}`} value={r.action} maxLength={200} placeholder="apa yang dilakukan, mis. berlari ke pematang"
              onSave={(text) => commit(ref.current.map((x) => x.character_id === r.character_id ? { ...x, action: text } : x))} />
          </div>
        );
      })}
      {rows.length < MAX_CAST && free.length > 0 && (
        <label className="cast-add">
          <Plus size={13} />
          <select value="" aria-label="Tambah pemeran" disabled={locked}
            onChange={(e) => { if (e.target.value) void commit([...ref.current, { character_id: e.target.value, outfit_id: null, action: "" }]).catch(() => {}); }}>
            <option value="">Tambah pemeran…</option>
            {free.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
      )}
      {characters.length === 0 && <p className="muted">Belum ada karakter. Buat di halaman Karakter.</p>}
      {rows.length >= MAX_CAST && <p className="muted">Maksimal {MAX_CAST} pemeran per adegan.</p>}
    </div>
  );
}
