export interface Health { ffmpeg: boolean; api_key: boolean; spent_today: number; daily_budget: number; max_per_job: number }
export interface VideoModel {
  id: string; name?: string;
  supported_durations?: number[]; supported_resolutions?: string[]; supported_aspect_ratios?: string[];
  supported_frame_images?: string[] | null; generate_audio?: boolean | null;
}
export interface ParamDesc { type: "enum" | "range" | "boolean"; values?: string[]; min?: number; max?: number }
export interface ImageModel { id: string; name?: string; supported_parameters?: Record<string, ParamDesc> }
export interface Img {
  id: string; parent_image_id: string | null; kind: "upload" | "edit" | "frame" | "sheet";
  prompt: string | null; model: string | null; width: number; height: number; cost: number | null; estimated_cost?: number | null;
}
export interface Clip {
  id: string; parent_clip_id: string | null; source_image_id: string | null; prompt: string; model: string;
  status: "submitted" | "in_progress" | "completed" | "failed" | "failed_download";
  cost: number | null; estimated_cost?: number | null; error: string | null; chain_depth: number; has_file: boolean; has_merged: boolean;
}

export interface Estimate {
  low: number; high: number; confidence: "exact" | "formula" | "history" | "bound" | "unknown"; basis: string[];
  committed_today: number; daily_budget: number; remaining: number; max_per_job: number; blocked?: string | null;
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

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init);
  if (!res.ok) {
    let body: Record<string, unknown> = {};
    try { body = await res.json(); } catch { /* body bukan JSON */ }
    const detail = body.detail ?? `${res.status}`;
    throw new ApiError(typeof detail === "string" ? detail : JSON.stringify(detail), res.status, body);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export interface EstimateRequest {
  kind: "video" | "image_edit" | "character_sheet"; model: string; duration?: number; resolution?: string; aspect_ratio?: string;
  generate_audio?: boolean; reference_count?: number; quality?: string;
}

export interface Character { id: string; name: string; description: string; source_image_id: string; images: { image_id: string; label: string }[] }

export const api = {
  characters: () => call<Character[]>("/characters"),
  createCharacter: (body: { name: string; description: string; source_image_id: string }) => call<Character>("/characters", json(body)),
  makeSheet: (id: string, body: { model: string; aspect_ratio?: string } & Confirm) => call<Character>(`/characters/${id}/sheet`, json(body)),
  estimate: (body: EstimateRequest) => call<Estimate>("/estimate", json(body)),
  health: () => call<Health>("/health"),
  videoModels: () => call<VideoModel[]>("/models/video"),
  imageModels: () => call<ImageModel[]>("/models/image"),
  images: () => call<Img[]>("/images"),
  upload: (file: File) => { const f = new FormData(); f.append("file", file); return call<Img>("/images", { method: "POST", body: f }); },
  editImage: (id: string, body: { prompt: string; model: string; reference_image_ids: string[]; resolution?: string; aspect_ratio?: string; quality?: string; character_id?: string } & Confirm) =>
    call<Img[]>(`/images/${id}/edit`, json(body)),
  clips: () => call<Clip[]>("/clips"),
  createClip: (body: Record<string, unknown>) => call<Clip>("/clips", json(body)),
  extend: (id: string, body: Record<string, unknown>) => call<Clip>(`/clips/${id}/extend`, json(body)),
  merge: (id: string) => call<Clip>(`/clips/${id}/merge`, { method: "POST" }),
  retryDownload: (id: string) => call<Clip>(`/clips/${id}/retry-download`, { method: "POST" }),
  imageUrl: (id: string) => `/api/images/${id}/file`,
  clipUrl: (id: string) => `/api/clips/${id}/file`,
  mergedUrl: (id: string) => `/api/clips/${id}/merged`,
};
