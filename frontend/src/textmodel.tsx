// Pilihan model LLM untuk fitur AI teks (plan 17): daftar disaring server, bawaan per tugas diingat di browser.
import { useEffect, useMemo, useState } from "react";
import { api, TextModel, TextModels } from "./api";

export type TextTask = "scene" | "script" | "split";
const KEY = (task: TextTask) => `ai-studio:text-model:${task}`;
let cache: Promise<TextModels> | null = null;
const load = () => (cache ??= api.textModels().catch((e) => { cache = null; throw e; }));
const read = (task: TextTask) => { try { return localStorage.getItem(KEY(task)); } catch { return null; } };
const write = (task: TextTask, id: string) => { try { localStorage.setItem(KEY(task), id); } catch { /* penyimpanan tidak tersedia */ } };

/** `model` = pilihan yang berlaku; "teks" (placeholder lama) berarti "bawaan server" selama daftar belum termuat. */
export function useTextModel(task: TextTask) {
  const [data, setData] = useState<TextModels | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(() => read(task));
  useEffect(() => { let alive = true; load().then((d) => alive && setData(d)).catch((e: Error) => alive && setError(e.message)); return () => { alive = false; }; }, []);
  const valid = data?.models.some((m) => m.id === picked);
  const model = data ? (valid ? picked! : data.default) : "teks";
  const setModel = (id: string) => { setPicked(id); write(task, id); };
  return { model, setModel, data, error };
}

const fmt = (n: number) => (n >= 10 ? n.toFixed(0) : n >= 1 ? n.toFixed(2) : n.toFixed(3));
const label = (m: TextModel) =>
  `${m.recommended ? "★ " : ""}${m.name} · $${fmt(m.prompt_per_m)}/$${fmt(m.completion_per_m)} per 1 jt · ${Math.round((m.context ?? 0) / 1000)}k${m.vision ? " · gambar" : ""}`;

export function TextModelPicker({ task, value, onChange, hint }: {
  task: TextTask; value: string; onChange: (id: string) => void; hint?: string;
}) {
  const { data, error } = useTextModel(task);
  const [q, setQ] = useState("");
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data?.models ?? []).filter((m) => !needle || `${m.id} ${m.name}`.toLowerCase().includes(needle) || m.id === value);
  }, [data, q, value]);
  if (error) return <p className="muted">Daftar model tidak termuat ({error}); memakai model bawaan server.</p>;
  if (!data) return <p className="muted">Memuat daftar model…</p>;
  const groups = [["Direkomendasikan", shown.filter((m) => m.recommended)], ["Model lain", shown.filter((m) => !m.recommended && !m.expensive)],
    ["Mahal (> $20 per juta token keluaran)", shown.filter((m) => m.expensive)]] as const;
  const current = data.models.find((m) => m.id === value);
  return (
    <div className="field tm-picker">
      <span>Model AI teks</span>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari model…" aria-label="Cari model AI teks" />
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Model AI teks">
        {groups.map(([name, ms]) => ms.length > 0 && (
          <optgroup key={name} label={name}>{ms.map((m) => <option key={m.id} value={m.id}>{label(m)}</option>)}</optgroup>
        ))}
      </select>
      {current?.expensive && <p className="warn">Model mahal: biaya per panggilan bisa jauh lebih besar; periksa estimasi di bawah.</p>}
      {current && !current.structured && <p className="muted">Model ini tanpa keluaran terstruktur; jawabannya lebih sering rusak.</p>}
      {hint && <p className="muted">{hint}</p>}
    </div>
  );
}
