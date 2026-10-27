# 13 - Negative prompt di Gambar → Video (Implementation)

Plan: `docs/plan/13-negative-prompt-plan.md` · Grill: `docs/grill/13-negative-prompt-grill.md`
Tanggal: 2026-10-23 · Status: backend selesai dan teruji; UI selesai dibangun (build hijau), menunggu uji manual oleh user. Efek nyata di video belum diverifikasi (uji berbayar tidak dijalankan, sesuai grill).

## Yang dibangun
### Backend
- `openrouter.py`: `get_video_endpoints(model)` → `GET /models/{id}/endpoints`, mengembalikan `data.endpoints` (field slug: `tag`, dicek pada respons nyata Veo 3.1 Lite).
- `service.py`:
  - `_video_endpoints` (cache 5 menit, berbagi `_endpoint_cache` dengan kunci `video:<id>`).
  - `_negative_param(info)`: nama parameter dari `allowed_passthrough_parameters` (`negative_prompt` / `negativePrompt`).
  - `_provider_options(model, values)`: `{"options": {slug: …}}` untuk semua slug penyedia; `google-vertex` dibungkus `parameters`, slug lain datar. 502 bila penyedia tidak diketahui.
  - `video_catalog()`: `capabilities.negative_prompt` (nama parameter atau `null`).
  - `create_clip(…, negative_prompt=None)`: di-trim; kosong = tidak ada. Model tanpa dukungan → 400 sebelum estimasi/biaya. Payload mendapat `provider`; nilai disimpan di `params.negative_prompt`.
- `main.py`: `ClipIn.negative_prompt` dan `ExtendIn.negative_prompt` (maks 2000); `public_clip` mengeluarkan `negative_prompt`. Extend meneruskannya lewat `**kw` yang sudah ada.

### Frontend
- `api.ts`: `VideoModel.allowed_passthrough_parameters`, `Clip.negative_prompt`.
- `prompts.ts`: `NEGATIVE_PRESETS` (Teks, Watermark, Blur, Tangan cacat, Wajah berubah).
- `components.tsx`: `supportsNegative()` dan `NegativePrompt` (kolom + chip + catatan "efeknya tidak bisa dipastikan aplikasi"). Kolom hanya tampil bila model mendukung; isinya dikosongkan saat model diganti ke yang tidak mendukung.
- `pages/Generate.tsx`: kolom di bawah "Model & parameter".
- `lightbox.tsx`: kolom di form Extend; fakta "Negative prompt" di detail klip.

## Temuan grill yang ditangani
| Grill | Penanganan |
|---|---|
| Slug dari penyedia endpoint, bukan id model | `get_video_endpoints` + `tag`. FakeOpenRouter memakai slug nyata (`atlas-cloud`, `google-vertex`). |
| Bentuk berbeda per penyedia | Test untuk keduanya. |
| Beberapa penyedia | Opsi dikirim ke semua slug. |
| Parameter opsional untuk pemanggil lama (`scenes.py`, `extend_clip`) | Default `None`; seluruh test lama tetap hijau. |
| Kosong/spasi | Diabaikan, bahkan untuk model tanpa dukungan. |

## Menyimpang dari plan
- Frontend memakai `allowed_passthrough_parameters` dari `GET /api/models/video` mentah (sudah dipakai halaman ini untuk `last_frame`), bukan `capabilities.negative_prompt` katalog. Kemampuan katalog tetap ditambahkan untuk modal katalog bila nanti perlu.
- Storyboard tidak termasuk (pertanyaan terbuka 1 tidak dijawab; default plan).

## Hasil tes
- `make test`: **228 passed** (221 sebelumnya + 7 baru di `backend/tests/test_negative_prompt.py`: atlas-cloud datar, google-vertex `parameters`, model tanpa dukungan ditolak tanpa submit, kosong diabaikan, extend, katalog, batas 2000).
- `cd frontend && npm run build`: hijau.
- Uji nyata berbayar: **tidak dijalankan**. Bentuk payload mengikuti contoh dokumentasi resmi; OpenRouter mengabaikan kunci yang salah tanpa error, jadi efek di video belum terbukti.

## Uji frontend: diuji manual oleh user
Restart backend dulu (`make be` / `make dev`).
1. Gambar → Video, pilih Kling v3.0 / Veo 3.1 / Wan 2.6: kolom "Negative prompt (opsional)" muncul dengan chip.
2. Ganti ke Seedance atau Hailuo: kolom hilang; kembali ke Kling: kolom kosong.
3. Klik chip "Watermark" dua kali: frasa tidak tergandakan.
4. Buat video dengan negative prompt (berbayar, dialog biaya muncul seperti biasa). Di Lightbox klip itu ada "Negative prompt".
5. Extend klip dengan model yang mendukung: kolom yang sama muncul di form Extend.
6. Bila mau menilai efeknya: dua klip Kling/Wan dengan prompt sama, satu tanpa dan satu dengan negative prompt, lalu bandingkan.

## Riwayat
- 2026-10-23: implementasi awal.
