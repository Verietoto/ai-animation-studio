// Langkah "Suara" Storyboard v2 (plan 18): suara tiap karakter, berversi. Unggah, rekam langsung, atau cukup deskripsi.
import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Loader2, Mic, Square, Trash2, Upload, UserRound } from "lucide-react";
import { toast } from "sonner";
import { api, EpisodeCharacter, VoiceVersion } from "../../api";

const MAX_RECORD = 15;   // detik; sama dengan batas server (backend/app/voices.py)

function Recorder({ onDone, disabled }: { onDone: (blob: Blob) => void; disabled?: boolean }) {
  const [on, setOn] = useState(false);
  const [sec, setSec] = useState(0);
  const rec = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const stop = useCallback(() => { window.clearInterval(timer.current); if (rec.current && rec.current.state !== "inactive") rec.current.stop(); }, []);
  useEffect(() => () => { window.clearInterval(timer.current); rec.current?.stream.getTracks().forEach((t) => t.stop()); }, []);

  async function start() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const r = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      r.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      r.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        setOn(false);
        if (chunks.length) onDone(new Blob(chunks, { type: r.mimeType || "audio/webm" }));
      };
      rec.current = r; r.start(); setOn(true); setSec(0);
      timer.current = window.setInterval(() => setSec((s) => { if (s + 1 >= MAX_RECORD) stop(); return s + 1; }), 1000);
    } catch { toast.error("Mikrofon tidak bisa dipakai. Izinkan akses mikrofon di browser, atau unggah berkas audio."); }
  }
  return on
    ? <button type="button" className="btn danger sm" onClick={stop}><Square size={13} /> Berhenti ({sec}/{MAX_RECORD} dtk)</button>
    : <button type="button" className="btn sm" disabled={disabled} onClick={() => void start()}><Mic size={13} /> Rekam suara</button>;
}

function VoiceCard({ character, locked, onChanged }: { character: EpisodeCharacter; locked: boolean; onChanged: () => void }) {
  const [list, setList] = useState<VoiceVersion[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [desc, setDesc] = useState("");
  const [note, setNote] = useState("");
  const [consent, setConsent] = useState(false);
  const [sample, setSample] = useState<{ blob: Blob; name: string; url: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => api.voices(character.id).then((r) => setList(r.versions)).catch((e: Error) => toast.error(e.message)), [character.id]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => () => { if (sample) URL.revokeObjectURL(sample.url); }, [sample]);

  const pick = (blob: Blob, name: string) => setSample((old) => { if (old) URL.revokeObjectURL(old.url); return { blob, name, url: URL.createObjectURL(blob) }; });
  const reset = () => { setAdding(false); setDesc(""); setNote(""); setConsent(false); setSample((old) => { if (old) URL.revokeObjectURL(old.url); return null; }); };
  const active = list?.find((v) => v.active) ?? null;
  const canSave = !busy && (sample ? consent : desc.trim().length > 0);

  async function save() {
    setBusy(true);
    try {
      await api.addVoice(character.id, { description: desc.trim(), consent, note: note.trim(), file: sample?.blob, filename: sample?.name });
      toast.success(`Suara ${character.name} disimpan`);
      reset(); await load(); onChanged();
    } catch (e) { toast.error((e as Error).message); }
    finally { setBusy(false); }
  }
  const act = async (fn: () => Promise<unknown>) => { try { await fn(); await load(); onChanged(); } catch (e) { toast.error((e as Error).message); } };

  return (
    <article className="jr-card v2-voice" aria-label={`Suara ${character.name}`}>
      <header className="v2-voice-head">
        <img src={api.imageUrl(character.image_id)} alt="" loading="lazy" />
        <div>
          <strong>{character.name}</strong>
          <span className="muted clamp1">{active ? (active.description || (active.has_audio ? "Sampel suara" : "")) : "Belum punya suara"}</span>
        </div>
        {active?.has_audio && <audio controls preload="none" src={api.voiceUrl(active.id)} aria-label={`Putar suara ${character.name}`} />}
      </header>

      {!adding && <button className="btn sm" disabled={locked} onClick={() => setAdding(true)}><Mic size={13} /> {active ? "Ganti suara" : "Tambah suara"}</button>}

      {adding && (
        <div className="v2-voice-form">
          <label className="field">Seperti apa suaranya?
            <textarea rows={2} maxLength={300} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Contoh: suara kucing jantan, berat, santai, sedikit serak" />
          </label>
          <div className="v2-voice-sample">
            <input ref={fileInput} type="file" accept="audio/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) pick(f, f.name); e.target.value = ""; }} />
            <button type="button" className="btn sm" onClick={() => fileInput.current?.click()}><Upload size={13} /> Unggah audio</button>
            <Recorder onDone={(b) => pick(b, "rekaman.webm")} />
            <span className="muted">2 sampai 15 detik. Tanpa sampel pun boleh, deskripsi saja.</span>
          </div>
          {sample && (
            <div className="v2-voice-preview">
              <audio controls src={sample.url} aria-label="Pratinjau sampel suara" />
              <button type="button" className="btn ghost sm" onClick={() => setSample((old) => { if (old) URL.revokeObjectURL(old.url); return null; })} aria-label="Buang sampel"><Trash2 size={13} /></button>
            </div>
          )}
          {sample && (
            <label className="check">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              Suara ini milik saya, atau dipakai dengan izin pemiliknya
            </label>
          )}
          <label className="field">Catatan (opsional)<input value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} placeholder="Contoh: rekaman kedua, lebih pelan" /></label>
          <div className="jr-inline">
            <button className="btn primary sm" disabled={!canSave} onClick={() => void save()}>{busy ? <Loader2 size={13} className="spin" /> : <Check size={13} />} Simpan suara</button>
            <button className="btn ghost sm" onClick={reset}>Batal</button>
          </div>
        </div>
      )}

      {list && list.length > 1 && (
        <details className="v2-versions">
          <summary>{list.length} versi suara</summary>
          <ul>
            {list.map((v) => (
              <li key={v.id} className={v.active ? "on" : ""}>
                <div className="v2-ver-main">
                  <span className="clamp1">{v.description || (v.has_audio ? "Sampel suara" : "Tanpa deskripsi")}</span>
                  <span className="muted">{v.has_audio ? `${v.duration?.toFixed(1)} dtk` : "teks saja"}{v.revision_note ? ` · ${v.revision_note}` : ""}</span>
                </div>
                {v.has_audio && <audio controls preload="none" src={api.voiceUrl(v.id)} />}
                {v.active ? <span className="chip">dipakai</span>
                  : <button className="btn sm" disabled={locked} onClick={() => void act(() => api.activateVoice(v.id))}>Pakai</button>}
                <button className="btn ghost sm danger" disabled={locked} aria-label="Hapus versi suara"
                  onClick={() => { if (window.confirm("Hapus versi suara ini?")) void act(() => api.deleteVoice(v.id)); }}><Trash2 size={13} /></button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}

export function StepVoices({ characters, locked, onChanged, goCast }: { characters: EpisodeCharacter[]; locked: boolean; onChanged: () => void; goCast: () => void }) {
  if (characters.length === 0) {
    return (
      <div className="empty">
        <UserRound size={32} />
        <strong>Belum ada karakter di episode ini</strong>
        <span className="muted">Pilih karakter dulu, lalu beri tiap karakter suara.</span>
        <button className="btn primary" onClick={goCast}>Pilih karakter</button>
      </div>
    );
  }
  return (
    <div className="v2-voices">
      <p className="muted">Suara dipakai saat karakter berbicara di video. Boleh dilewati: tanpa suara, model memilih suaranya sendiri dari deskripsi dialog.</p>
      <div className="jr-cols">
        {characters.map((c) => <VoiceCard key={c.id} character={c} locked={locked} onChanged={onChanged} />)}
      </div>
    </div>
  );
}
