import { useState } from "react";
import { History } from "lucide-react";
import { addPhrase, loadHistory, PRESETS } from "./prompts";

/** Chip preset yang menambah frasa ke prompt + riwayat 20 prompt terakhir. */
export function PromptHelper({ value, onChange, groups }: { value: string; onChange: (v: string) => void; groups: (keyof typeof PRESETS)[] }) {
  const [group, setGroup] = useState<string>(groups[0]);
  const [history, setHistory] = useState<string[] | null>(null);   // dimuat saat dibuka: bisa berubah antar tab
  return (
    <div className="helper">
      <div className="helper-top">
        <div className="seg" role="tablist" aria-label="Jenis preset">
          {groups.map((g) => <button key={g} role="tab" aria-selected={g === group} className={g === group ? "on" : ""} onClick={() => setGroup(g)}>{g}</button>)}
        </div>
        <button className="btn ghost sm" aria-expanded={history !== null} onClick={() => setHistory(history ? null : loadHistory())}>
          <History size={14} /> Riwayat
        </button>
      </div>
      <div className="chips">
        {PRESETS[group].map((p) => (
          <button key={p.label} className="chip preset" title={p.text} onClick={() => onChange(addPhrase(value, p.text))}>+ {p.label}</button>
        ))}
      </div>
      {history && (
        <ul className="history" aria-label="Riwayat prompt">
          {history.length === 0 && <li className="muted">Belum ada riwayat.</li>}
          {history.map((h) => <li key={h}><button className="btn ghost sm" onClick={() => { onChange(h); setHistory(null); }}>{h}</button></li>)}
        </ul>
      )}
    </div>
  );
}
