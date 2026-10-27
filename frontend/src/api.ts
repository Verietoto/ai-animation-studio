import type { Environment, Layout, Look, ResolvedProp } from "./storyboard/blockoutMath";
export interface Health { ffmpeg: boolean; api_key: boolean; spent_today: number; daily_budget: number; max_per_job: number; public_media?: boolean; max_reference_seconds?: number }
export interface VideoModel {
  id: string; name?: string;
  supported_durations?: number[]; supported_resolutions?: string[]; supported_aspect_ratios?: string[];
  supported_frame_images?: string[] | null; generate_audio?: boolean | null;
  allowed_passthrough_parameters?: string[] | null;
}
export interface ParamDesc { type: "enum" | "range" | "boolean"; values?: string[]; min?: number; max?: number }
export interface ImageModel { id: string; name?: string; supported_parameters?: Record<string, ParamDesc> }
export interface Img {
  id: string; parent_image_id: string | null; kind: "upload" | "edit" | "frame" | "sheet" | "keyframe" | "location" | "anchor" | "portrait";
  prompt: string | null; model: string | null; width: number; height: number; cost: number | null; estimated_cost?: number | null;
  created_at: string;
  origin_image_id?: string | null; origin_workspace?: string | null;   // salinan lintas workspace (plan 07)
}
export interface Workspace {
  id: string; name: string; archived: boolean; created_at: string;
  counts: { images: number; clips: number; characters: number; films: number };
}
export interface CopyResult {
  workspace_id: string; images: { from: string; to: string }[]; characters: { from: string; to: string; name: string }[];
}
export interface Clip {
  id: string; parent_clip_id: string | null; source_image_id: string | null; prompt: string; model: string;
  status: "submitted" | "in_progress" | "completed" | "failed" | "failed_download";
  cost: number | null; estimated_cost?: number | null; error: string | null; chain_depth: number; has_file: boolean; has_merged: boolean;
  kind: string; created_at: string; updated_at: string; params: string; duration?: number | null;
  last_image_id?: string | null;   // frame akhir (plan 09)
  negative_prompt?: string | null;   // plan 13
  workspace_id?: string; workspace_name?: string;   // workspace_name hanya ada di /api/jobs
}

/** Video referensi untuk tiru gerakan (plan 03/09). */
export interface Reference {
  id: string; duration: number; width: number; height: number; has_audio: boolean; source_clip_id: string | null;
  created_at: string; trimmed?: boolean;
}
export type MotionMode = "flux_edit" | "anchor_edit" | "reference";

export interface Estimate {
  low: number; high: number; confidence: "exact" | "formula" | "history" | "bound" | "unknown"; basis: string[];
  committed_today: number; daily_budget: number; remaining: number; max_per_job: number; blocked?: string | null;
  inputs?: number;   // jumlah gambar input (image_edit berbasis id)
}
export interface Confirm { confirmed_cost?: number | null; accept_unknown_cost?: boolean }

export class ApiError extends Error {
  constructor(message: string, public status: number, public body: Record<string, unknown>) { super(message); }
  /** Server menolak karena estimasi belum dikonfirmasi / berubah: berisi estimasi terbaru. */
  get estimate(): Estimate | null {
    const e = this.body.estimate as Partial<Estimate> | undefined;
    return e ? ({ ...this.body, ...e } as Estimate) : null;
  }
}

// ---- workspace aktif (plan 07): satu variabel modul, dikirim sebagai header oleh satu-satunya fetch di bawah ----
const WS_KEY = "ai-studio:workspace";
const readWs = () => { try { return localStorage.getItem(WS_KEY) || "main"; } catch { return "main"; } };
let activeWs = readWs();
export const workspace = {
  get id() { return activeWs; },
  set(id: string) { activeWs = id; try { localStorage.setItem(WS_KEY, id); } catch { /* storage diblokir: tetap jalan */ } },
  /** Diisi App: dipanggil saat server bilang workspace aktif hilang/diarsip (mis. diarsip di tab lain). */
  onMissing: (() => {}) as () => void,
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const sent = activeWs;
  // JANGAN menambah fetch lain di aplikasi: header workspace hanya dipasang di sini (diperiksa di docs/implementation/07)
  const res = await fetch(`/api${path}`, { ...init, headers: { ...(init?.headers as Record<string, string> | undefined), "X-Workspace-Id": sent } });
  const echoed = res.headers.get("X-Workspace-Id");
  if (res.ok && echoed && echoed !== sent) throw new Error(`Workspace tidak cocok (dikirim ${sent}, dibalas ${echoed})`);
  if (!res.ok) {
    let body: Record<string, unknown> = {};
    try { body = await res.json(); } catch { /* body bukan JSON */ }
    if (body.code === "workspace_missing" && sent === activeWs) workspace.onMissing();
    const detail = body.detail ?? `${res.status}`;
    throw new ApiError(friendlyError(typeof detail === "string" ? detail : JSON.stringify(detail)), res.status, body);
  }
  return res.json() as Promise<T>;
}

/** Penolakan filter konten provider -> saran yang bisa ditindaklanjuti (plan 09). Dipakai untuk error request dan clip.error. */
export function friendlyError(msg: string): string;
export function friendlyError(msg: string | null | undefined): string | null;
export function friendlyError(msg: string | null | undefined): string | null {
  if (!msg || msg.includes("foto-realistik")) return msg ?? null;   // pesan server yang sudah menjelaskan
  if (/cannot use media as a reference/i.test(msg))
    return "Ditolak FLUX Video Edit: model ini hanya membaca teks dan menganggap prompt merujuk ke gambar/foto. Tulis deskripsi karakter dengan kata-kata (rambut, pakaian, warna) tanpa menyebut \"foto\" atau \"gambar\". "
      + `(Pesan asli: ${msg.slice(0, 160)})`;
  if (/moderation|SensitiveContent|content policy|safety system/i.test(msg))
    return `Ditolak filter konten model. Coba model lain, lunakkan kata di prompt, atau ganti gambar/video referensi. (Pesan asli: ${msg.slice(0, 200)})`;
  return msg;
}

const json = (body: unknown): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export interface EstimateRequest {
  kind: "video" | "image_edit" | "character_sheet" | "scene_keyframe" | "scene_video" | "scene_blockout" | "scene_beats" | "scene_revise" | "script_revise" | "scene_prompt_revise" | "scene_previs_video" | "episode_script" | "episode_split" | "character_portrait" | "location_image" | "storyboard_video" | "motion" | "motion_anchor"; model: string; use_previs?: boolean;
  mode?: MotionMode; reference_id?: string;
  scene_id?: string; location_id?: string; film_id?: string; description?: string; duration?: number; resolution?: string; aspect_ratio?: string;
  generate_audio?: boolean; reference_count?: number; quality?: string;
  // image_edit berbasis id (plan 06): server menghitung daftar gambar input yang sama dengan saat generate
  source_image_id?: string; character_id?: string; pose_image_id?: string; pose_mode?: "sketch" | "original";
  expression_image_id?: string; reference_image_ids?: string[]; pose_text?: string; expression_text?: string;
}
export interface EditRoles {
  character_id?: string; pose_image_id?: string; pose_mode?: "sketch" | "original"; expression_image_id?: string;
  pose_text?: string; expression_text?: string;
}

export interface Outfit { id: string; character_id: string; name: string; description: string; image_id: string | null; created_at: string }
export interface Character {
  id: string; name: string; description: string; source_image_id: string; created_at?: string;
  images: { image_id: string; label: string }[]; outfits: Outfit[];
}
export interface Location { id: string; name: string; description: string; image_id: string | null; used: number }
export interface CastMember {
  character_id: string; character_name: string; outfit_id: string | null; outfit_name: string | null; image_id: string | null; action: string;
}
export type SceneStatus = "naskah" | "keyframe" | "video_diproses" | "siap" | "gagal";
export interface Scene {
  id: string; film_id: string; position: number; number: number; location: { id: string; name: string; image_id: string | null } | null;
  time_of_day: string; camera: string; dialogue: string; extra_prompt: string;
  keyframe_image_id: string | null; clip_id: string | null; cast: CastMember[]; status: SceneStatus; clip_status: string | null; updated_at: string;
  planned_seconds: number | null; keyframe_takes: string[]; video_takes: { id: string; status: string }[];
  blockout: Layout | null; blockout_image_id: string | null; previs_ref_id: string | null;   // plan 14
  script_excerpt: string;   // potongan naskah asal adegan (plan 15)
  start_from_prev: boolean;   // plan 18 Revisi 9: mulai dari frame akhir video adegan sebelumnya
}

// ---- alur episode (plan 15) ----
export interface BlockoutResolved {
  layout: Layout; props: ResolvedProp[]; environment: Environment; bounds: [number, number]; looks: Record<string, Look>; warnings: string[];
}
export interface TextModel {
  id: string; name: string; prompt_per_m: number; completion_per_m: number; context: number | null;
  structured: boolean; reasoning: boolean; vision: boolean; expensive: boolean; recommended: boolean; note: string | null;
}
export interface TextModels { default: string; models: TextModel[] }
export interface EpisodeCharacter { id: string; name: string; description: string; image_id: string; has_sheet: boolean }
export interface EpisodeLocation { id: string; name: string; description: string; image_id: string | null }
export interface JourneyProgress {
  scenes: number; blockout: number; previs: number; keyframe: number; video: number; no_location: number; planned: number;
  video_ready: number; rendered: boolean; render_status: string;
}
export interface JourneyState {
  film_id: string; script: string; script_changed: boolean; previs_skipped: boolean;
  characters: EpisodeCharacter[]; locations: EpisodeLocation[];
  mentions: { unknown: { kind: "character" | "location"; name: string }[]; ambiguous: { kind: "character" | "location"; name: string }[] };
  format: { detected: boolean; scenes: number; shots: number; errors: string[]; warnings: string[] };   // naskah berformat shot Seedance (plan 18 Rev. 5)
  progress: JourneyProgress;
}
// ---- Storyboard v2 (plan 18) ----
export interface ProjectSettings {
  allowed_video_models: string[];   // Storyboard v2 dikunci ke keluarga Seedance 2.0 (server yang menentukan)
  video_model: string; video_resolution: string; aspect_ratio: string; generate_audio: boolean; image_model: string | null; style: string; genre: string;
  ratio_locked: boolean; v2_assets: { beat_images: number; clips: number }; mismatched_films: number; synced_films?: number;
}
export type ProjectSettingsPatch = Partial<Omit<ProjectSettings, "allowed_video_models" | "ratio_locked" | "v2_assets" | "mismatched_films" | "synced_films">> & { confirm_sync?: boolean };
export interface VoiceVersion {
  id: string; character_id: string; description: string; has_audio: boolean; duration: number | null; source: "upload" | "text";
  consent: boolean; revision_note: string | null; created_at: string; active: boolean;
}
export interface BeatDialogue { character_id: string; text: string }
export interface Beat {
  id: string; start: number; end: number; action: string; camera: string; size: string | null; lens: string | null; cast: string[]; dialogue: BeatDialogue[]; image_id: string | null; broken: boolean;
}
export interface BeatsResponse { beats: Beat[]; planned_seconds: number | null; warnings: string[]; warnings_save?: string[] }
export type RevisedBeat = Beat & { from: number | null; changed: boolean };
export interface BeatRevision {
  beats: RevisedBeat[]; warnings: string[]; total_seconds: number; previous_seconds: number; mood: string; time_of_day: string;
  mood_changed: boolean; time_changed: boolean; cost: number | null; estimated_cost: number; attempts: number;
}
export interface ScenePromptState {
  prompt: string; derived: boolean; errors: string[]; warnings: string[];
  assets: { characters: { id: string; name: string; image_id: string | null }[]; location: { id: string; name: string; image_id: string | null } | null };
  will_link?: { characters: { id: string; name: string }[]; location: { id: string; name: string; image_id: string | null } | null } | null;
}
export interface PromptRevision { prompt: string; previous: string; changed: number[]; warnings: string[]; cost: number | null; estimated_cost: number; attempts: number }
export interface BeatVersion { id: string; note: string | null; created_at: string; count: number; seconds: number }
export interface BeatPayload { id?: string; start: number; end: number; action: string; camera: string; size: string | null; lens: string | null; cast: string[]; dialogue: BeatDialogue[] }
export interface StoryboardRef { kind: "image" | "audio" | "video" | "frame"; n: number; label: string; image_id?: string; voice_id?: string; clip_id?: string }
export interface StoryboardPreview {
  model: string; duration: number; resolution: string; aspect_ratio: string; generate_audio: boolean; prompt: string; warnings: string[];
  scene_prompt: string; refs: StoryboardRef[]; public_media: boolean; previs_available: boolean; audio_refs: number;
  start_from_prev: boolean; start_frame: { scene_number: number; clip_id: string } | null;
  can_start_from_prev: { ok: boolean; reason: string | null; scene_number: number | null; clip_id: string | null };
}

export interface ScriptRevision {
  script: string; warnings: string[]; cost: number | null; estimated_cost: number; attempts: number; format_before: boolean;
  scenes: { n: number; changed: boolean; text: string; previous: string | null }[]; previous_scenes: number; removed: number;
}
export interface SplitScene {
  location_id: string | null; time_of_day: string; camera: string; dialogue: string; extra_prompt: string; excerpt: string;
  planned_seconds: number; cast: { character_id: string; outfit_id: string | null; action: string }[];
  beats?: { start: number; end: number; size: string | null; lens: string | null; camera: string; action: string }[];   // dari naskah berformat
}
export interface CastIn { character_id: string; outfit_id: string | null; action: string }
/** Hanya field yang dikirim yang diubah di server. */
export type SceneUpdate = Partial<Pick<Scene, "time_of_day" | "camera" | "dialogue" | "extra_prompt">> &
  { start_from_prev?: boolean; location_id?: string | null; keyframe_image_id?: string | null; clip_id?: string | null; cast?: CastIn[]; planned_seconds?: number | null;
    blockout?: Layout | null; blockout_image_id?: string | null };

export type Confidence = Estimate["confidence"];
export interface PriceExample { label: string; low: number; high: number; confidence: Confidence }
export interface CatalogModel {
  id: string; name: string; provider: string; description: string;
  capabilities: Record<string, unknown> & { durations?: number[]; resolutions?: string[]; aspect_ratios?: string[]; audio?: boolean | null;
    first_frame?: boolean; last_frame?: boolean; max_references?: number | null; quality?: string[] };
  price: {
    category: string; selectable: boolean; disabled_reason: string | null; notes: string[]; example: PriceExample;
    rows: { label?: string; audio?: boolean | null; usd_per_second?: number | null; confidence?: Confidence;
            provider?: string; billable?: string; unit?: string; usd?: number; variant?: string | null }[];
  };
}
export interface Catalog { fetched_at: string; models: CatalogModel[] }

export interface Film {
  id: string; title: string; number: number; synopsis: string; aspect_ratio: string; planned_seconds: number; scene_count: number; ready_count: number; clip_ids: string[]; render_status: "idle" | "rendering" | "done" | "failed"; render_error: string | null;
  has_file: boolean; stale: boolean; created_at: string; updated_at: string;
}
export interface FilmDetail extends Film {
  scenes: Scene[];
  durations: Record<string, number>; warnings: { scene: number; kind: "aspect" | "unplayable"; message: string }[];
}

const put = <T>(path: string, body: unknown) =>
  call<T>(path, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  workspaces: (withArchived = false) => call<Workspace[]>(`/workspaces${withArchived ? "?archived=true" : ""}`),
  restoreWorkspace: (id: string) => call<Workspace>(`/workspaces/${id}/restore`, { method: "POST" }),
  deleteWorkspace: (id: string) => call<{ deleted: Workspace["counts"] }>(`/workspaces/${id}`, { method: "DELETE" }),
  createWorkspace: (name: string) => call<Workspace>("/workspaces", json({ name })),
  renameWorkspace: (id: string, name: string) => put<Workspace>(`/workspaces/${id}`, { name }),
  archiveWorkspace: (id: string) => call<Workspace>(`/workspaces/${id}/archive`, { method: "POST" }),
  copyTo: (targetId: string, body: { image_ids: string[]; character_ids: string[] }) =>
    call<CopyResult>(`/workspaces/${targetId}/copy`, json(body)),
  jobs: () => call<Clip[]>("/jobs"),
  deleteImage: (id: string) => call<{ ok: boolean }>(`/images/${id}`, { method: "DELETE" }),
  deleteClip: (id: string) => call<{ ok: boolean }>(`/clips/${id}`, { method: "DELETE" }),
  deleteCharacter: (id: string) => call<{ ok: boolean }>(`/characters/${id}`, { method: "DELETE" }),
  bulkDelete: (ids: { image_ids: string[]; clip_ids: string[]; character_ids: string[] }) =>
    call<{ deleted: { images: number; clips: number; characters: number }; skipped: number; failed: { type: string; id: string; reason: string }[] }>(
      "/bulk-delete", json(ids)),
  films: () => call<Film[]>("/films"),
  film: (id: string) => call<FilmDetail>(`/films/${id}`),
  createFilm: (title: string, number?: number) => call<Film>("/films", json({ title, number })),
  updateFilm: (id: string, body: { title?: string; number?: number; synopsis?: string; aspect_ratio?: string; script?: string; previs_skipped?: boolean }) => put<Film>(`/films/${id}`, body),
  journey: (id: string) => call<JourneyState>(`/films/${id}/journey`),
  setEpisodeCast: (id: string, body: { character_ids: string[]; location_ids: string[]; release?: boolean }) => put<JourneyState>(`/films/${id}/cast`, body),
  textModels: () => call<TextModels>("/models/text"),
  reviseScript: (id: string, body: Confirm & { model?: string; instruction: string }) => call<ScriptRevision>(`/films/${id}/script/revise`, json(body)),
  scriptDraft: (id: string, body: Confirm & { model?: string }) => call<{ script: string; warnings: string[]; cost: number | null }>(`/films/${id}/script/draft`, json(body)),
  splitScript: (id: string, body: Confirm & { model?: string }) => call<{ scenes: SplitScene[]; warnings: string[]; cost: number | null }>(`/films/${id}/split`, json(body)),
  splitFormat: (id: string) => call<{ scenes: SplitScene[]; warnings: string[]; cost: number; source: "format" }>(`/films/${id}/split/format`, json({})),
  applySplit: (id: string, body: { scenes: SplitScene[]; mode: "append" | "replace" }) => call<{ scenes: Scene[]; warnings: string[] }>(`/films/${id}/split/apply`, json(body)),
  scenePrevisVideo: (id: string, body: { model: string; duration?: number; resolution?: string; aspect_ratio?: string; generate_audio?: boolean; idempotency_key?: string } & Confirm) =>
    call<Scene>(`/scenes/${id}/previs-video`, json(body)),
  addScene: (filmId: string, body: { after_scene_id?: string; inherit?: boolean; clip_id?: string } = {}) => call<Scene>(`/films/${filmId}/scenes`, json(body)),
  reorderScenes: (filmId: string, scene_ids: string[]) => put<Scene[]>(`/films/${filmId}/scene-order`, { scene_ids }),
  updateScene: (id: string, body: SceneUpdate) => put<Scene>(`/scenes/${id}`, body),
  sceneBlockout: (id: string, body: Confirm & { model?: string }) => call<{ layout: Layout; warnings: string[]; cost: number | null; estimated_cost: number }>(`/scenes/${id}/blockout`, json(body)),
  resolveBlockout: (id: string, layout: Layout | null) => call<BlockoutResolved>(`/scenes/${id}/blockout/resolve`, json({ layout })),
  scenePrevis: (id: string, video: Blob, filename: string) => { const f = new FormData(); f.append("file", video, filename); return call<Scene>(`/scenes/${id}/previs`, { method: "POST", body: f }); },
  sceneKeyframe: (id: string, body: { model: string } & Confirm) => call<Scene>(`/scenes/${id}/keyframe`, json(body)),
  sceneVideo: (id: string, body: { model: string; duration?: number; resolution?: string; aspect_ratio?: string; generate_audio?: boolean; idempotency_key?: string } & Confirm) =>
    call<Scene>(`/scenes/${id}/video`, json(body)),
  locationImage: (id: string, body: { model: string } & Confirm) => call<Location>(`/locations/${id}/image`, json(body)),
  deleteScene: (id: string) => call<{ ok: boolean }>(`/scenes/${id}`, { method: "DELETE" }),
  bulkDeleteScenes: (filmId: string, sceneIds: string[]) =>
    call<{ deleted: number; remaining: number; film_id: string }>(`/films/${filmId}/scenes/bulk-delete`, json({ scene_ids: sceneIds })),
  duplicateScene: (id: string) => call<Scene>(`/scenes/${id}/duplicate`, { method: "POST" }),
  locations: () => call<Location[]>("/locations"),
  createLocation: (body: { name: string; description?: string; image_id?: string | null }) => call<Location>("/locations", json(body)),
  updateLocation: (id: string, body: { name?: string; description?: string; image_id?: string | null }) => put<Location>(`/locations/${id}`, body),
  deleteLocation: (id: string) => call<{ ok: boolean }>(`/locations/${id}`, { method: "DELETE" }),
  createOutfit: (characterId: string, body: { name: string; description?: string; image_id?: string | null }) =>
    call<Outfit>(`/characters/${characterId}/outfits`, json(body)),
  deleteOutfit: (id: string) => call<{ ok: boolean }>(`/outfits/${id}`, { method: "DELETE" }),
  addCharacterImage: (characterId: string, image_id: string, label = "custom") =>
    call<Character>(`/characters/${characterId}/images`, json({ image_id, label })),
  deleteFilm: (id: string) => call<{ ok: boolean }>(`/films/${id}`, { method: "DELETE" }),
  renderFilm: (id: string) => call<Film>(`/films/${id}/render`, { method: "POST" }),
  filmUrl: (id: string, v?: string) => `/api/films/${id}/file${v ? `?v=${encodeURIComponent(v)}` : ""}`,
  catalog: (kind: "video" | "image", refresh = false) => call<Catalog>(`/catalog/${kind}${refresh ? "?refresh=1" : ""}`),
  characters: () => call<Character[]>("/characters"),
  characterPortrait: (body: { description: string; model: string } & Confirm) => call<Img>("/characters/portrait", json(body)),
  createCharacter: (body: { name: string; description: string; source_image_id: string }) => call<Character>("/characters", json(body)),
  makeSheet: (id: string, body: { model: string; aspect_ratio?: string } & Confirm) => call<Character>(`/characters/${id}/sheet`, json(body)),
  estimate: (body: EstimateRequest) => call<Estimate>("/estimate", json(body)),
  health: () => call<Health>("/health"),
  videoModels: () => call<VideoModel[]>("/models/video"),
  imageModels: () => call<ImageModel[]>("/models/image"),
  images: () => call<Img[]>("/images"),
  upload: (file: File) => { const f = new FormData(); f.append("file", file); return call<Img>("/images", { method: "POST", body: f }); },
  sketchUrl: (id: string) => `/api/images/${id}/sketch`,
  editImage: (id: string, body: { prompt: string; model: string; reference_image_ids: string[]; resolution?: string; aspect_ratio?: string; quality?: string } & EditRoles & Confirm) =>
    call<Img[]>(`/images/${id}/edit`, json(body)),
  clips: () => call<Clip[]>("/clips"),
  createClip: (body: Record<string, unknown>) => call<Clip>("/clips", json(body)),
  extend: (id: string, body: Record<string, unknown>) => call<Clip>(`/clips/${id}/extend`, json(body)),
  merge: (id: string) => call<Clip>(`/clips/${id}/merge`, { method: "POST" }),
  retryDownload: (id: string) => call<Clip>(`/clips/${id}/retry-download`, { method: "POST" }),
  references: () => call<Reference[]>("/references"),
  referenceFromClip: (clipId: string) => call<Reference>(`/references/from-clip/${clipId}`, { method: "POST" }),
  uploadReference: (file: File) => { const f = new FormData(); f.append("file", file); return call<Reference>("/references", { method: "POST", body: f }); },
  trimReference: (id: string, start: number, end: number) => call<Reference>(`/references/${id}/trim`, json({ start, end })),
  referenceUrl: (id: string) => `/api/references/${id}/file`,
  makeAnchor: (body: { reference_id: string; character_id: string; model: string } & Confirm) => call<Img>("/motion/anchor", json(body)),
  motion: (body: { mode: MotionMode; model: string; reference_id: string; prompt: string; character_id?: string; image_ids?: string[];
    anchor_image_id?: string; subject_text?: string; duration?: number; resolution?: string; aspect_ratio?: string; generate_audio?: boolean; idempotency_key?: string } & Confirm) =>
    call<Clip>("/motion", json(body)),
  projectSettings: (wsId: string) => call<ProjectSettings>(`/workspaces/${wsId}/settings`),
  updateProjectSettings: (wsId: string, body: ProjectSettingsPatch) => put<ProjectSettings>(`/workspaces/${wsId}/settings`, body),
  voices: (characterId: string) => call<{ active: string | null; versions: VoiceVersion[] }>(`/characters/${characterId}/voices`),
  addVoice: (characterId: string, v: { description: string; consent: boolean; note?: string; file?: Blob; filename?: string }) => {
    const f = new FormData();
    f.append("description", v.description); f.append("consent", String(v.consent)); f.append("note", v.note ?? "");
    if (v.file) f.append("file", v.file, v.filename ?? "suara.m4a");
    return call<VoiceVersion>(`/characters/${characterId}/voices`, { method: "POST", body: f });
  },
  activateVoice: (id: string) => call<VoiceVersion>(`/voices/${id}/activate`, { method: "POST" }),
  deleteVoice: (id: string) => call<{ ok: boolean }>(`/voices/${id}`, { method: "DELETE" }),
  voiceUrl: (id: string) => `/api/voices/${id}/file`,
  beats: (sceneId: string) => call<BeatsResponse>(`/scenes/${sceneId}/beats`),
  aiBeats: (id: string, body: Confirm & { model?: string }) => call<{ beats: Beat[]; warnings: string[]; cost: number | null; estimated_cost: number; attempts: number }>(`/scenes/${id}/beats/ai`, json(body)),
  reviseScene: (id: string, body: Confirm & { model?: string; instruction: string }) => call<BeatRevision>(`/scenes/${id}/revise`, json(body)),
  scenePrompt: (id: string) => call<ScenePromptState>(`/scenes/${id}/prompt`),
  checkScenePrompt: (id: string, prompt: string) => call<{ errors: string[]; warnings: string[]; will_link: ScenePromptState["will_link"] & { characters: { id: string; name: string; image_id?: string | null }[] } | null }>(`/scenes/${id}/prompt/check`, json({ prompt })),
  revisePrompt: (id: string, body: Confirm & { model?: string; instruction: string }) => call<PromptRevision>(`/scenes/${id}/prompt/revise`, json(body)),
  saveScenePrompt: (id: string, prompt: string) => put<ScenePromptState>(`/scenes/${id}/prompt`, { prompt }),
  saveBeats: (sceneId: string, beats: BeatPayload[], note = "") => put<BeatsResponse>(`/scenes/${sceneId}/beats`, { beats, note }),
  beatVersions: (sceneId: string) => call<BeatVersion[]>(`/scenes/${sceneId}/beats/versions`),
  storyboardPreview: (sceneId: string, usePrevis = false) => call<StoryboardPreview>(`/scenes/${sceneId}/storyboard-video/preview?use_previs=${usePrevis}`),
  storyboardVideo: (sceneId: string, body: { prompt?: string; use_previs?: boolean; idempotency_key?: string } & Confirm) =>
    call<Scene>(`/scenes/${sceneId}/storyboard-video`, json(body)),
  restoreBeats: (sceneId: string, version_id: string) => call<BeatsResponse>(`/scenes/${sceneId}/beats/restore`, json({ version_id })),
  imageUrl: (id: string) => `/api/images/${id}/file`,
  clipUrl: (id: string) => `/api/clips/${id}/file`,
  mergedUrl: (id: string) => `/api/clips/${id}/merged`,
};
