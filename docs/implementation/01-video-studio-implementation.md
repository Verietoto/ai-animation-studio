# 01 - Video Studio (Implementation)

Plan: `docs/plan/01-video-studio-plan.md`
Grill: `docs/grill/01-video-studio-grill.md`
Mencakup juga plan/grill 02 (edit foto), yang dibangun pada iterasi yang sama (`docs/implementation/02-image-edit-implementation.md`).

## Yang dibangun
Iterasi 1: gambar → video, extend lewat frame terakhir + ffmpeg, library, gabung rantai extend.
- Backend FastAPI + SQLite (WAL) + penyimpanan lokal; frontend React + Vite + TypeScript.
- Satu klien tipis OpenRouter (`backend/app/openrouter.py`), logika di `service.py`, ffmpeg/Pillow di `media.py`.
- Worker thread polling job; job aktif di DB otomatis dilanjutkan setelah restart.

## File yang diubah
`backend/app/{config,db,storage,media,openrouter,service,main}.py`, `backend/tests/`, `frontend/src/`, `scripts/{fake_openrouter,smoke_openrouter}.py`, `.env.example`, `.gitignore`, `README.md`.

## Penyimpangan dari plan (dan alasannya)
- Frontend memakai CSS biasa, bukan Tailwind (lebih sedikit dependensi untuk UI sekecil ini).
- Storage hanya lokal. Aset dikirim ke OpenRouter sebagai data URL (gambar). Storage S3/URL publik **belum** dibuat karena iterasi ini tidak mengirim video referensi (hanya perlu saat extend native / copy gerakan).
- Extend native Seedance tidak diimplementasikan; hanya jalur frame terakhir + ffmpeg.
- Crossfade antar klip tidak dibuat.
- Copy gerakan + suara tidak dibangun (sesuai keputusan grill).

## Temuan grill yang sudah ditangani
| Temuan | Penanganan | Bukti |
|---|---|---|
| API key bocor | Hanya di env backend; tidak ada di respons API; token disanitasi dari pesan error | `test_api_key_sent_only_as_bearer_never_in_responses`, `test_error_text_redacts_token` |
| Biaya | Batas harian (402), idempotency key, tombol dikunci saat kirim, validasi parameter sebelum kirim | `test_daily_budget_blocks_new_jobs`, `test_idempotency_key_prevents_duplicate_job`, `test_invalid_params_rejected_before_calling_provider` |
| Job hilang saat restart | Polling dilanjutkan dari DB | `test_jobs_resume_after_restart` |
| Unduhan gagal | Status `failed_download`, retry tanpa submit ulang | `test_download_failure_then_retry` |
| Timeout polling | `JOB_TIMEOUT_SECONDS` | `test_job_timeout` |
| Frame akhir hitam | Mundur ke frame lebih awal | `test_extract_last_frame_skips_black_frames` |
| Klip tanpa audio saat digabung | Normalisasi profil + audio senyap | `test_merge_handles_clip_without_audio` |
| Rantai extend panjang | Maks `MAX_EXTEND_CHAIN` + peringatan di UI | `test_extend_uses_last_frame_and_chain_limit` |
| Upload berbahaya/besar | Tipe dari isi file, batas ukuran, normalisasi (EXIF, alpha, 2048px), tolak GIF animasi | `test_upload_*` |
| Path traversal | Nama file UUID; `Storage.resolve` menolak path di luar root | (kode; belum ada tes khusus) |
| ffmpeg tidak ada | `/api/health` + banner di UI | diverifikasi manual |

Belum ditangani: estimasi biaya sebelum kirim (hanya biaya aktual setelah job), crossfade, SSRF tidak relevan karena tidak ada impor URL.

## Pengujian (perintah dan hasil nyata)
- `.venv/bin/python -m pytest backend`: **21 lulus** (dijalankan dari root dan dari `backend/`). Memakai OpenRouter palsu berbasis `httpx.MockTransport` dan ffmpeg sungguhan.
- `npm run build` di `frontend/`: lulus (tsc + vite).
- Uji end-to-end UI dengan Chromium (Playwright) terhadap server nyata + `scripts/fake_openrouter.py`: unggah gambar → buat video → status `completed` → extend → klip kedua `completed` → gabung rantai → edit foto → "Jadikan video". Semua langkah lolos. Satu-satunya error konsol adalah 404 `/favicon.ico`.
- Pemutaran video tidak diperiksa secara visual: Chromium open-source tidak punya codec H.264, jadi pemutar menampilkan 0:00 di screenshot. Endpoint file mengembalikan 200 dan ffprobe memvalidasi file.

## Verifikasi nyata (2026-10-19)
Dengan akses jaringan ke openrouter.ai (tanpa key), diverifikasi terhadap API nyata: `GET /videos/models` (30 model, bentuk field sesuai asumsi `openrouter.py`) dan `GET /models?output_modalities=image` (63 model, `architecture.input_modalities` sesuai asumsi; 62 menerima input gambar; model di plan 02 semuanya ada). Dari situ ditambah: penolakan `generate_audio` untuk model tanpa audio, penolakan model non-image-to-video, dan filter model di UI. Tes backend: **23 lulus**.

## Verifikasi terhadap dokumentasi resmi video (2026-10-19)
Dokumentasi resmi video (`/docs/guides/overview/multimodal/video-generation`) cocok dengan asumsi klien: `POST /videos` mengembalikan `id`, `polling_url`, `status`; status `pending|in_progress|completed|failed`; hasil lewat `unsigned_urls` / `GET /videos/{id}/content?index=0` (butuh header Authorization); `usage.cost` ada di respons poll; `frame_images` bentuk `{type:"image_url", image_url:{url}, frame_type}`. Dokumentasi hanya menunjukkan URL HTTPS untuk gambar; **data URL untuk `frame_images` belum terbukti** dan baru bisa dibuktikan dengan satu job video nyata.

## Masalah tersisa
- **Endpoint berotentikasi belum diuji nyata** (submit/polling/content `/videos`, `/chat/completions`): key belum tersedia di environment sesi. Sebelumnya seluruh kontrak belum teruji; kini hanya bagian berikut yang masih asumsi: (tidak ada API key; openrouter.ai tidak bisa diakses dari lingkungan pengembangan). Nama field `frame_images`/`frame_type`/`usage.cost`, bentuk respons job, dan status job (`completed`/`failed`) berasal dari dokumentasi dan dibaca longgar. Jalankan `scripts/smoke_openrouter.py` dengan key untuk memverifikasi; kemungkinan perlu penyesuaian kecil di `openrouter.py`.
- Apakah data URL diterima untuk `frame_images` belum terbukti; jika ditolak, perlu storage URL publik.
- Tidak ada autentikasi: hanya untuk lokal.

## Riwayat
- 2026-10-16: iterasi 1.
