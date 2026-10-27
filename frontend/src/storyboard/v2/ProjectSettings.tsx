// Pengaturan proyek Storyboard v2 (plan 18): model video, resolusi, rasio, audio, gaya, model gambar. Berlaku untuk SEMUA episode di workspace.
import { useCallback, useEffect, useState } from "react";
import { Loader2, Lock } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, ImageModel, ProjectSettings, ProjectSettingsPatch, VideoModel, workspace } from "../../api";
import { SaveText } from "../fields";

const RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "9:21"];
const RESOLUTIONS = ["480p", "720p", "1080p", "4K"];

/** Kotak kecil berbanding lurus dengan rasio, supaya pilihan terlihat bentuknya. */
function RatioGlyph({ ratio }: { ratio: string }) {
  const [w, h] = ratio.split(":").map(Number);
  const k = 22 / Math.max(w, h);
  return <span className="v2-glyph" style={{ width: Math.round(w * k), height: Math.round(h * k) }} aria-hidden />;
}

export function useProjectSettings() {
  const [s, setS] = useState<ProjectSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(() => api.projectSettings(workspace.id).then((x) => { setS(x); setError(null); }).catch((e: Error) => setError(e.message)), []);
  useEffect(() => { void reload(); }, [reload]);
  return { s, error, reload, setS };
}

export function ProjectSettingsPanel({ s, setS, onChanged }: { s: ProjectSettings; setS: (s: ProjectSettings) => void; onChanged: () => void }) {
  const [videoModels, setVideoModels] = useState<VideoModel[]>([]);
  const [imageModels, setImageModels] = useState<ImageModel[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void api.videoModels().then(setVideoModels).catch(() => {});
    void api.imageModels().then(setImageModels).catch(() => {});
  }, []);

  const choices = s.allowed_video_models.map((id) => ({ id, name: videoModels.find((m) => m.id === id)?.name }));   // dikunci ke Seedance 2.0 oleh server
  const model = videoModels.find((m) => m.id === s.video_model);
  const resolutions = model?.supported_resolutions?.length ? model.supported_resolutions : RESOLUTIONS;
  const ratios = model?.supported_aspect_ratios?.length ? RATIOS.filter((r) => model.supported_aspect_ratios!.includes(r) || r === s.aspect_ratio) : RATIOS;

  async function save(patch: ProjectSettingsPatch): Promise<void> {
    setBusy(true);
    try {
      const next = await api.updateProjectSettings(workspace.id, patch);
      setS(next);
      if (next.synced_films) toast.success(`Rasio ${next.aspect_ratio} diterapkan ke ${next.synced_films} episode`);
      onChanged();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && !patch.confirm_sync && "films_with_assets" in e.body) {
        setBusy(false);
        if (window.confirm(`${e.message}\n\nLanjutkan dan samakan rasio semua episode?`)) return save({ ...patch, confirm_sync: true });
        return;
      }
      toast.error((e as Error).message);
      throw e;
    } finally { setBusy(false); }
  }
  const quiet = (patch: ProjectSettingsPatch) => { void save(patch).catch(() => {}); };

  return (
    <section className="jr-card v2-settings" aria-label="Pengaturan proyek">
      <h3>Pengaturan proyek {busy && <Loader2 size={13} className="spin" />}</h3>
      <p className="muted">Berlaku untuk semua episode, supaya hasilnya seragam. Perubahan tersimpan otomatis dan hanya memengaruhi hasil berikutnya.</p>

      <label className="field">Model video (Seedance 2.0)
        <select value={s.video_model} onChange={(e) => quiet({ video_model: e.target.value })} disabled={busy}>
          {!choices.some((m) => m.id === s.video_model) && <option value={s.video_model}>{s.video_model}</option>}
          {choices.map((m) => <option key={m.id} value={m.id}>{m.name ?? m.id}</option>)}
        </select>
      </label>

      <div className="field" role="group" aria-label="Resolusi video">Resolusi
        <div className="seg">
          {resolutions.map((r) => (
            <button key={r} type="button" aria-pressed={s.video_resolution === r} className={s.video_resolution === r ? "on" : ""} disabled={busy}
              onClick={() => s.video_resolution !== r && quiet({ video_resolution: r })}>{r}</button>
          ))}
        </div>
      </div>

      <div className="field" role="group" aria-label="Rasio video">
        <span>Rasio {s.ratio_locked && <span className="chip meta" title={`Terkunci: ${s.v2_assets.beat_images} gambar beat, ${s.v2_assets.clips} klip`}><Lock size={11} /> terkunci</span>}</span>
        <div className="v2-ratios">
          {ratios.map((r) => (
            <button key={r} type="button" className={`v2-ratio ${s.aspect_ratio === r ? "on" : ""}`} aria-pressed={s.aspect_ratio === r}
              disabled={busy || (s.ratio_locked && s.aspect_ratio !== r)} onClick={() => s.aspect_ratio !== r && quiet({ aspect_ratio: r })}>
              <RatioGlyph ratio={r} /><span>{r}</span>
            </button>
          ))}
        </div>
        {s.ratio_locked
          ? <span className="muted">Rasio dikunci karena proyek sudah punya {s.v2_assets.beat_images} gambar beat dan {s.v2_assets.clips} klip Storyboard v2.</span>
          : s.mismatched_films > 0 && <span className="muted warn">{s.mismatched_films} episode memakai rasio lain; memilih rasio menyamakan semuanya.</span>}
      </div>

      <label className="check">
        <input type="checkbox" checked={s.generate_audio} disabled={busy} onChange={(e) => quiet({ generate_audio: e.target.checked })} />
        Buat suara, dialog, dan efek bunyi bersama videonya
      </label>

      <label className="field">Genre
        <SaveText label="Genre" maxLength={80} value={s.genre ?? ""} placeholder="Contoh: noir heist, komedi keluarga, petualangan fantasi"
          onSave={(v) => save({ genre: v })} />
        <span className="muted">Masuk ke baris FORMAT prompt Seedance, dan jadi konteks saat AI membuat shot.</span>
      </label>

      <label className="field">Gaya visual proyek
        <SaveText label="Gaya visual proyek" multiline rows={2} maxLength={500} value={s.style}
          placeholder="Contoh: kartun 2D warna cerah, garis tebal, cahaya sore hangat"
          onSave={(v) => save({ style: v })} />
        <span className="muted">Ditambahkan ke setiap prompt gambar dan video supaya semua episode terlihat sama.</span>
      </label>

      <label className="field">Model gambar untuk beat
        <select value={s.image_model ?? ""} disabled={busy} onChange={(e) => quiet({ image_model: e.target.value || null })}>
          <option value="">Pilih saat membuat gambar</option>
          {imageModels.map((m) => <option key={m.id} value={m.id}>{m.name ?? m.id}</option>)}
        </select>
      </label>
    </section>
  );
}

/** Ringkasan satu baris yang selalu terlihat di atas alur v2. */
export function ProjectSummary({ s, onOpen }: { s: ProjectSettings; onOpen: () => void }) {
  const short = s.video_model.split("/").pop() ?? s.video_model;
  return (
    <button className="v2-summary" onClick={onOpen} title="Buka pengaturan proyek">
      <strong>{short}</strong><span>{s.video_resolution}</span><span>{s.aspect_ratio}</span><span>{s.generate_audio ? "dengan suara" : "tanpa suara"}</span>
      {s.ratio_locked && <Lock size={12} aria-label="Rasio terkunci" />}
    </button>
  );
}
