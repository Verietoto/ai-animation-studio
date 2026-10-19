export interface Health { ffmpeg: boolean; api_key: boolean; spent_today: number; daily_budget: number }
export interface VideoModel {
  id: string; name?: string;
  supported_durations?: number[]; supported_resolutions?: string[]; supported_aspect_ratios?: string[];
  supported_frame_images?: string[] | null; generate_audio?: boolean | null;
}
export interface ImageModel { id: string; name?: string }
export interface Img {
  id: string; parent_image_id: string | null; kind: "upload" | "edit" | "frame";
  prompt: string | null; model: string | null; width: number; height: number; cost: number | null;
}
export interface Clip {
  id: string; parent_clip_id: string | null; source_image_id: string | null; prompt: string; model: string;
  status: "submitted" | "in_progress" | "completed" | "failed" | "failed_download";
  cost: number | null; error: string | null; chain_depth: number; has_file: boolean; has_merged: boolean;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init);
  if (!res.ok) {
    let detail = `${res.status}`;
    try { detail = (await res.json()).detail ?? detail; } catch { /* body bukan JSON */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export const api = {
  health: () => call<Health>("/health"),
  videoModels: () => call<VideoModel[]>("/models/video"),
  imageModels: () => call<ImageModel[]>("/models/image"),
  images: () => call<Img[]>("/images"),
  upload: (file: File) => { const f = new FormData(); f.append("file", file); return call<Img>("/images", { method: "POST", body: f }); },
  editImage: (id: string, body: { prompt: string; model: string; reference_image_ids: string[] }) =>
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
