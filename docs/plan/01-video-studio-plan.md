# 01 - Video Studio (Plan)

- Status: disetujui user (2026-10-16); stack: FastAPI + React
- Tanggal: 2026-10-16

## Tujuan
Aplikasi studio untuk membuat video AI lewat OpenRouter (API video asinkron `POST /api/v1/videos`, polling `GET /api/v1/videos/{jobId}`, unduh `GET /api/v1/videos/{jobId}/content`; daftar model `GET /api/v1/videos/models`).

## Fitur dan prioritas
1. **Image-to-video + extend (fase 1)**
   - Upload gambar + prompt, pilih model/durasi/resolusi/aspect ratio dari `/videos/models`, hasilnya muncul di library.
   - Extend di tempat yang sama: pilih klip hasil, tulis prompt lanjutan. Pendekatan awal: ambil frame terakhir klip, kirim sebagai `frame_images` (first-frame) untuk generasi klip berikutnya, lalu gabungkan klip dengan ffmpeg. (Belum diverifikasi: apakah ada model OpenRouter dengan extend native.)
2. **Copy gerakan + suara dari video referensi ke objek gambar (fase 2)**
   - Input: video referensi (gerakan + suara) + gambar objek/karakter + prompt.
   - Bergantung pada model yang mendukung reference/motion transfer dan audio di OpenRouter. **Harus diriset dan diuji dulu** sebelum desain final; bila tidak ada, fallback: gerakan lewat model reference-to-video, suara lewat langkah terpisah (mis. voice conversion) di luar OpenRouter.
3. **Edit foto dengan prompt**: lihat `docs/plan/02-image-edit-plan.md`. Hasil edit bisa langsung dipakai sebagai input image-to-video.
4. **Proyek film berepisode (ditunda)**
   - Hanya disiapkan di model data (Project > Episode > Scene > Klip) agar tidak perlu migrasi besar nanti. Tidak dibangun sekarang.

## Riset model OpenRouter (per 2026-10-16)
Semua angka dan kemampuan harus dicek ulang ke `GET /api/v1/videos/models` saat implementasi; daftar model berubah cepat dan API masih bisa berubah. Riset dilakukan lewat pencarian web karena akses langsung ke openrouter.ai dari container diblokir.

### Parameter API yang relevan
- `frame_images`: jangkar frame dengan `frame_type` `first_frame` / `last_frame`. Dukungan per model ada di `supported_frame_images`.
- `input_references`: referensi gambar, video, dan audio. Video dan audio saat ini hanya dihormati Seedance generasi 2 ke atas; model lain hanya memakai referensi gambar. Bila `frame_images` dan `input_references` dikirim bersamaan, frame image yang diprioritaskan.
- `generate_audio`: boolean, default mengikuti kemampuan model.
- `video_url` di referensi **harus URL HTTPS publik**; `data:` URL ditolak. Ini memengaruhi arsitektur (lihat Desain).
- SDK Go punya field `PreviousJobID` untuk edit/extend job lama, tapi belum ditemukan di dokumentasi REST. Belum terverifikasi.

### Rekomendasi model per fitur
| Fitur | Model utama | Alternatif | Catatan |
|---|---|---|---|
| Image-to-video | Seedance 2.5 | Veo 3.1 / Veo 3.1 Lite, Kling v3.0 Pro, Wan 3.0 | Veo 3.1 Lite: 720p/1080p, 4/6/8 detik, first+last frame, audio native. Wan 3.0: 2 sampai 30 detik. |
| Extend video | Seedance 2.5 (video sebagai `input_references`) | Fallback: frame terakhir sebagai `first_frame` di model mana pun, lalu digabung ffmpeg | Seedance 2.5: sampai 30 detik per generasi, bisa extend berkali-kali. Ada laporan terbuka (typescript-sdk #1096) bahwa mode edit Seedance butuh `duration=-1` dan `aspect_ratio=adaptive` yang belum diekspos OpenRouter. |
| Copy gerakan + suara ke objek gambar | Seedance 2.5 (video + audio + gambar sebagai referensi, mode ganti subjek) | Di luar OpenRouter: Kling Motion Control, Wan 2.2 Animate (open-weight, bisa dijalankan sendiri) | Belum ditemukan bukti Kling Motion Control atau Wan Animate tersedia di OpenRouter. Kualitas transfer gerakan Seedance harus diuji nyata dulu. |

### Implikasi
- Seedance 2.5 kandidat model inti karena satu-satunya yang menerima video dan audio referensi di OpenRouter. Ketergantungan pada satu model adalah risiko; dibahas di grill.
- Lapisan model dibuat sebagai adapter per model, supaya model bisa diganti atau provider luar (mis. Kling/Wan langsung) ditambahkan tanpa mengubah UI.

## Ruang lingkup yang TIDAK dikerjakan sekarang
Editor timeline penuh, akun multi-user, pembayaran, fitur episode (UI dan alurnya).

## Desain (usulan, perlu disetujui)
- **Backend** (satu service): proxy ke OpenRouter agar API key tidak ada di browser; antrian job (submit, poll, simpan hasil); penyimpanan file lokal; ffmpeg untuk ambil frame terakhir dan menggabungkan klip.
- **Frontend**: web app. Halaman Generate (image-to-video + extend), Library klip, halaman Motion Transfer (fase 2).
- **Data**: SQLite. Tabel `projects`, `episodes`, `scenes`, `clips` (parent_clip_id untuk rantai extend), `jobs` (status, model, params, biaya, job id OpenRouter).
- **Hosting media**: karena `video_url` harus HTTPS publik, upload dan hasil disimpan di object storage dengan signed URL (mis. S3/R2), bukan hanya disk lokal. Ini juga berarti mode "lokal saja" butuh storage publik.
- **Model adapter**: satu adapter per model, membaca kemampuan dari `/videos/models` untuk validasi parameter di UI.
- **Config**: `OPENROUTER_API_KEY` lewat environment, tidak pernah di-commit.

## Langkah kerja (fase 1)
1. Skeleton repo, config, klien OpenRouter (list model, submit, poll, download).
2. Penyimpanan job/klip + worker polling.
3. UI Generate image-to-video.
4. Extend: ekstraksi frame terakhir, generasi lanjutan, penggabungan ffmpeg.
5. Tes (klien dengan mock, pipeline ffmpeg) + satu uji nyata dengan key sungguhan.

## Kriteria selesai fase 1
- Dari gambar + prompt dihasilkan video yang tersimpan dan bisa diputar.
- Dari klip itu, extend dengan prompt menghasilkan klip lanjutan yang tersambung dan bisa digabung.
- Parameter yang tidak didukung model ditolak di UI sebelum kirim, bukan error 400 mentah.

## Keputusan
- Stack: backend Python + FastAPI + SQLite; frontend React + Vite + TypeScript. Disetujui user.
- Storage media: abstraksi `Storage` dengan backend lokal (default dev) dan S3-compatible (R2) untuk URL publik. Keputusan deploy/biaya menyusul.

## Pertanyaan terbuka
- Dijalankan lokal saja, atau di-deploy?
- Model mana yang jadi default dan batas biaya per job?
- Seberapa panjang hasil akhir yang diharapkan (extend berapa kali)?

## Sumber
- [OpenRouter Video Generation](https://openrouter.ai/docs/features/multimodal/video-generation)
- [Image to Video cookbook](https://openrouter.ai/docs/cookbook/video-generation/image-to-video)
- [Reference to Video cookbook](https://openrouter.ai/docs/cookbook/video-generation/reference-to-video)
- [Submit a video generation request](https://openrouter.ai/docs/api/api-reference/video-generation/submit-a-video-generation-request)
- [Seedance 2.5 review](https://openrouter.ai/blog/insights/seedance-2-5-review/)
- [Image-to-Video models compared](https://openrouter.ai/blog/insights/image-to-video-models-compared/)
- [Video model collection](https://openrouter.ai/collections/video-models)
- [typescript-sdk issue #1096](https://github.com/OpenRouterTeam/typescript-sdk/issues/1096)
- [Wan-Animate](https://humanaigc.github.io/wan-animate/)

## Riwayat
- 2026-10-16: draft awal.
- 2026-10-16: stack diputuskan (FastAPI + React); status disetujui.
- 2026-10-16: tambah riset model, hosting media publik, adapter model, tautan ke plan 02.
