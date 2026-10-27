import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronDown, RefreshCw, Search, X } from "lucide-react";
import { api, Catalog, CatalogModel, Confidence } from "./api";
import { Portal } from "./ui";

type Kind = "video" | "image";

// Satu promise per jenis dibagi seluruh halaman; gagal -> dilepas agar bisa dicoba lagi.
const cache: Partial<Record<Kind, Promise<Catalog>>> = {};
function load(kind: Kind, refresh = false) {
  if (refresh || !cache[kind]) {
    cache[kind] = api.catalog(kind, refresh).catch((e) => { delete cache[kind]; throw e; });
  }
  return cache[kind]!;
}

export function useCatalog(kind: Kind) {
  const [data, setData] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const run = useCallback((refresh: boolean) => {
    setLoading(true); setError(null);
    load(kind, refresh).then(setData).catch((e: Error) => setError(e.message)).finally(() => setLoading(false));
  }, [kind]);
  useEffect(() => { run(false); }, [run]);
  return { data, error, loading, refresh: () => run(true) };
}

const usd = (n: number) => (n === 0 ? "$0 (gratis)" : n < 0.01 ? `$${n.toFixed(4)}` : n < 1 ? `$${n.toFixed(3)}` : `$${n.toFixed(2)}`);
const BADGE: Record<Confidence, string> = { exact: "pasti", formula: "rumus", history: "riwayat", bound: "batas atas", unknown: "tidak diketahui" };
const BILLABLE: Record<string, string> = { output_image: "output", input_image: "gambar input", input_text: "teks input" };

function unitText(usdValue: number, unit?: string) {
  if (unit === "token") return `${usd(usdValue * 1e6)} / 1M token`;
  if (unit === "image") return `${usd(usdValue)} / gambar`;
  if (unit === "megapixel") return `${usd(usdValue)} / megapiksel`;
  return `${usd(usdValue)} / ${unit ?? "satuan"}`;
}

export function exampleText(m: CatalogModel) {
  const e = m.price.example;
  if (e.confidence === "unknown") return "harga tidak diketahui";
  return `${e.low === e.high ? usd(e.high) : `${usd(e.low)}–${usd(e.high)}`} · ${e.label}`;
}

function Badge({ c }: { c: Confidence }) {
  return <span className="pill" title="Tingkat kepastian harga">{BADGE[c]}</span>;
}

function ModelCard({ m, kind, selected, onPick }: { m: CatalogModel; kind: Kind; selected: boolean; onPick?: () => void }) {
  const cap = m.capabilities;
  const chips = kind === "video"
    ? [cap.first_frame && "frame awal", cap.last_frame && "frame akhir", cap.audio === true && "suara", cap.audio === false && "tanpa suara",
       cap.durations?.length ? `${Math.min(...cap.durations)}–${Math.max(...cap.durations)} dtk` : null,
       cap.resolutions?.length ? cap.resolutions.join(" / ") : null]
    : [cap.max_references != null && `maks ${cap.max_references} referensi`, cap.quality?.length ? `kualitas: ${cap.quality.join("/")}` : null];
  return (
    <article className={`card catalog-card ${selected ? "picked" : ""} ${m.price.selectable ? "" : "off"}`}>
      <header className="catalog-head">
        <div>
          <strong>{m.name}</strong>
          <div className="mono muted">{m.id}</div>
        </div>
        <span className="pill">{m.price.category}</span>
      </header>
      {m.description && <p className="muted clamp">{m.description}</p>}
      <div className="chips">{chips.filter(Boolean).map((c) => <span key={String(c)} className="chip">{c}</span>)}</div>
      <table className="prices"><tbody>
        {m.price.rows.length === 0 && <tr><td colSpan={3} className="muted">harga tidak tersedia</td></tr>}
        {m.price.rows.map((r, i) => (
          <tr key={i}>
            <td>{kind === "video"
              ? `${r.label}${r.audio === true ? " · suara" : r.audio === false ? " · tanpa suara" : ""}`
              : `${r.provider} · ${BILLABLE[r.billable ?? ""] ?? r.billable}`}</td>
            <td className="mono">{kind === "video"
              ? (r.usd_per_second == null ? "?" : `${usd(r.usd_per_second)}/dtk`)
              : unitText(r.usd ?? 0, r.unit)}</td>
            <td>{r.confidence && <Badge c={r.confidence} />}</td>
          </tr>
        ))}
      </tbody></table>
      <div className="example"><span className="muted">Contoh {m.price.example.label}</span>
        <span className="mono">{m.price.example.confidence === "unknown" ? "?" : m.price.example.low === m.price.example.high ? usd(m.price.example.high) : `${usd(m.price.example.low)}–${usd(m.price.example.high)}`}</span>
        <Badge c={m.price.example.confidence} />
      </div>
      {m.price.notes.map((n) => <p key={n} className="muted">• {n}</p>)}
      {m.price.selectable
        ? onPick && <button className={`btn ${selected ? "" : "primary"}`} onClick={onPick}>{selected ? "Terpilih" : "Pilih model ini"}</button>
        : <p className="muted off-reason">{m.price.disabled_reason}</p>}
    </article>
  );
}

/** onPick kosong = mode lihat-lihat (dari command palette): tanpa tombol pilih. */
export function CatalogPanel({ kind, value = "", onPick, onClose }: { kind: Kind; value?: string; onPick?: (id: string) => void; onClose: () => void }) {
  const cat = useCatalog(kind);
  const [q, setQ] = useState("");
  const [provider, setProvider] = useState("");
  const [only, setOnly] = useState(false);
  const [sort, setSort] = useState<"price" | "name">("price");
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const models = cat.data?.models ?? [];
  const providers = useMemo(() => [...new Set(models.map((m) => m.provider))].sort(), [models]);
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const rank = (m: CatalogModel) => (m.price.example.confidence === "unknown" ? Infinity : m.price.example.high);
    return models
      .filter((m) => (!only || m.price.selectable) && (!provider || m.provider === provider)
        && (!needle || `${m.name} ${m.id} ${m.description}`.toLowerCase().includes(needle)))
      .sort((a, b) => Number(b.price.selectable) - Number(a.price.selectable)
        || (sort === "price" ? rank(a) - rank(b) : a.name.localeCompare(b.name)));
  }, [models, q, provider, only, sort]);

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label={`Katalog model ${kind === "video" ? "video" : "gambar"}`}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="catalog">
        <header className="catalog-bar">
          <h2>Model {kind === "video" ? "video" : "gambar"} <span className="muted">({shown.length}/{models.length})</span></h2>
          <span className="grow" />
          <button className="btn ghost sm" onClick={cat.refresh} disabled={cat.loading} title="Ambil ulang daftar dan harga">
            <RefreshCw size={14} className={cat.loading ? "spin" : ""} /> Perbarui harga
          </button>
          <button className="btn ghost sm" onClick={onClose} aria-label="Tutup"><X size={16} /></button>
        </header>
        <div className="catalog-filters">
          <label className="search"><Search size={14} />
            <input autoFocus placeholder="Cari nama, id, deskripsi…" value={q} onChange={(e) => setQ(e.target.value)} /></label>
          <select value={provider} onChange={(e) => setProvider(e.target.value)} aria-label="Provider">
            <option value="">Semua provider</option>{providers.map((p) => <option key={p}>{p}</option>)}
          </select>
          <select value={sort} onChange={(e) => setSort(e.target.value as "price" | "name")} aria-label="Urutkan">
            <option value="price">Termurah dulu</option><option value="name">Nama</option>
          </select>
          <label className="check"><input type="checkbox" checked={only} onChange={(e) => setOnly(e.target.checked)} /> Hanya yang bisa dipilih</label>
        </div>
        <p className="muted catalog-note">
          Harga daftar dari OpenRouter{cat.data && `, diambil ${new Date(cat.data.fetched_at).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })}`}.
          Angka yang mengikat tetap perkiraan biaya + dialog konfirmasi saat generate.
        </p>
        {cat.error && <p className="error">{cat.error}</p>}
        {cat.loading && !cat.data && <p className="muted">Memuat katalog…</p>}
        <div className="catalog-grid">
          {shown.map((m) => <ModelCard key={m.id} m={m} kind={kind} selected={m.id === value} onPick={onPick && (() => { onPick(m.id); onClose(); })} />)}
          {cat.data && shown.length === 0 && <p className="muted">Tidak ada model yang cocok.</p>}
        </div>
      </div>
    </div>
  );
}

/** Tombol pemilih model: menampilkan model terpilih + harga contoh, membuka katalog lengkap. */
export function ModelPicker({ kind, value, onChange, label = "Model" }: { kind: Kind; value: string; onChange: (id: string) => void; label?: string }) {
  const [open, setOpen] = useState(false);
  const cat = useCatalog(kind);
  const picked = cat.data?.models.find((m) => m.id === value);
  const gone = !!value && !!cat.data && !picked;   // model terpilih sudah tidak ada di katalog
  return (
    <div className="field">
      {label}
      <button type="button" className="btn picker" onClick={() => setOpen(true)} aria-haspopup="dialog">
        <span className="picker-main">
          <strong>{picked?.name ?? (value || "Pilih model…")}</strong>
          <span className="muted">{gone ? "tidak tersedia lagi" : picked ? exampleText(picked) : cat.error ? "katalog gagal dimuat" : "lihat semua model + harga"}</span>
        </span>
        <ChevronDown size={16} />
      </button>
      {open && <Portal><CatalogPanel kind={kind} value={value} onPick={onChange} onClose={() => setOpen(false)} /></Portal>}
    </div>
  );
}
