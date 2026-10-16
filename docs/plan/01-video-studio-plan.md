# 01 - Video Studio (Plan)

- Status: draft (menunggu persetujuan, belum digrill)
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
3. **Proyek film berepisode (fase 3, ditunda)**
   - Hanya disiapkan di model data (Project > Episode > Scene > Klip) agar tidak perlu migrasi besar nanti. Tidak dibangun sekarang.

## Ruang lingkup yang TIDAK dikerjakan sekarang
Editor timeline penuh, akun multi-user, pembayaran, fitur episode (UI dan alurnya).

## Desain (usulan, perlu disetujui)
- **Backend** (satu service): proxy ke OpenRouter agar API key tidak ada di browser; antrian job (submit, poll, simpan hasil); penyimpanan file lokal; ffmpeg untuk ambil frame terakhir dan menggabungkan klip.
- **Frontend**: web app. Halaman Generate (image-to-video + extend), Library klip, halaman Motion Transfer (fase 2).
- **Data**: SQLite. Tabel `projects`, `episodes`, `scenes`, `clips` (parent_clip_id untuk rantai extend), `jobs` (status, model, params, biaya, job id OpenRouter).
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

## Pertanyaan terbuka
- Stack: usul Python (FastAPI) + frontend web ringan; atau Node/TypeScript full-stack? Perlu keputusan.
- Dijalankan lokal saja, atau di-deploy?
- Model mana yang jadi default dan batas biaya per job?
- Seberapa panjang hasil akhir yang diharapkan (extend berapa kali)?

## Sumber
- [OpenRouter Video Generation](https://openrouter.ai/docs/features/multimodal/video-generation)
- [Image to Video cookbook](https://openrouter.ai/docs/cookbook/video-generation/image-to-video)

## Riwayat
- 2026-10-16: draft awal.
