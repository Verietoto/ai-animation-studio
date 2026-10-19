# 03 - Motion Transfer (Plan)

- Status: draft (menunggu persetujuan, belum digrill)
- Tanggal: 2026-10-19

## Tujuan
Menirukan gerakan (dan suara) dari sebuah video referensi pada subjek dari sebuah gambar: input video referensi + gambar objek/karakter + prompt, output video baru yang objeknya mengikuti gerakan referensi.

## Hasil riset (OpenRouter, per 2026-10-19)
Yang **terdokumentasi**:
- Model Seedance generasi 2 ke atas (`bytedance/seedance-2.5`, `-2.0`, `-2.0-fast`, `-2.0-mini`) menerima `input_references` bertipe `image_url`, `video_url`, dan audio dalam satu request (sampai 30 gambar, 10 video, 10 audio per request menurut halaman model; batas resmi endpoint tidak dipublikasikan). Video referensi ditagih dengan tarif token lebih murah ($0,0000064 vs $0,0000107 per token untuk 2.5). Sumber: [review Seedance 2.5](https://openrouter.ai/blog/insights/seedance-2-5-review/).
- Model lain dengan referensi gambar saja: Wan 3.0, Wan 2.7 (passthrough `video`/`videos`/`images`/`audio` terdaftar tapi tidak dijelaskan), HappyHorse. Model edit video: `runway/aleph-2`, `black-forest-labs/flux-video-edit` (mengedit video sumber, bukan memindahkan gerakan ke gambar). `heygen/avatar-iv`: foto + audio menjadi video bicara lip-sync (mengikuti suara, bukan gerakan video).
- Bila `frame_images` ikut dikirim, referensi diabaikan dan job diperlakukan sebagai image-to-video. Untuk fitur ini **jangan** kirim `frame_images`.
- `video_url` harus **URL HTTPS publik** yang bisa diunduh langsung; data URL ditolak (laporan komunitas). Gambar via data URL sudah terbukti diterima (plan 01), video belum.

Yang **belum terbukti** (inti risiko fitur ini):
- Apakah Seedance benar-benar *memindahkan gerakan* dari video referensi ke subjek gambar, atau hanya memakainya sebagai gaya/kelanjutan adegan. Dokumentasi menggambarkan "edit atau perpanjang footage" dan "ganti subjek", bukan transfer gerakan eksplisit. Perlu uji nyata dengan prompt yang jelas (mis. "gunakan gerakan di video 1 untuk karakter di gambar 1").
- Apakah suara referensi dibawa: kemungkinan lewat audio referensi + `generate_audio: true`, tanpa jaminan meniru suara/ucapan aslinya.
- Batas durasi/ukuran/format video referensi.
- Kling Motion Control dan Wan Animate (khusus transfer gerakan) **tidak ditemukan** di katalog OpenRouter; hanya tersedia di luar OpenRouter.

## Ruang lingkup
- Termasuk: halaman "Tiru Gerakan": unggah video referensi (dan opsional pakai audio dari video itu), pilih gambar objek (dari library, termasuk hasil edit foto), prompt, model Seedance, durasi, resolusi; hasil masuk library klip.
- Pra-pemrosesan video referensi di server: validasi dengan ffprobe, batas durasi/ukuran, potong ke rentang yang dipilih, normalisasi ke mp4 h264, ekstraksi audio opsional.
- Tidak termasuk: fallback ke penyedia luar OpenRouter (Kling/Wan Animate) pada iterasi ini; pengenalan/penggantian wajah; kloning suara pihak ketiga; proyek berepisode.

## Desain (usulan)
- **Hosting URL publik untuk video referensi (wajib).** Opsi:
  1. *Cloudflare R2 / S3 dengan presigned GET URL berumur pendek* (rekomendasi): objek privat, URL kedaluwarsa (mis. 1 jam), dihapus setelah job selesai. Perlu akun dan kredensial dari user.
  2. Tunnel sementara ke server lokal (mis. cloudflared): tanpa akun storage, tapi server lokal terbuka selama job berjalan dan URL harus dibatasi ke satu berkas bertoken.
  Abstraksi `PublicMedia.publish(path) -> https_url` dengan dua implementasi; default dipilih user.
- Tabel `clips` mendapat kolom `kind` (`i2v`, `extend`, `motion`) dan `reference_video_path`; permintaan menyimpan `reference_asset_ids`. Klip hasil bisa di-extend seperti klip biasa.
- Backend endpoint `POST /api/motion` (multipart: video, image_id, prompt, model, durasi, resolusi, `use_reference_audio`). Validasi parameter dari `/videos/models` seperti sebelumnya, plus pemeriksaan model mendukung referensi video (daftar model yang diizinkan di config, bukan dari API karena API tidak mengekspos kemampuan itu secara terstruktur).
- Prompt di-template: menyertakan instruksi eksplisit transfer gerakan; user bisa mengedit.
- UI: halaman baru "Tiru Gerakan" dengan pratinjau video referensi dan gambar objek berdampingan.

## Langkah kerja
1. **Spike murah** (sebelum membangun apa pun): satu job nyata ke Seedance (varian termurah, 480p, pendek) dengan video referensi di URL publik sementara untuk menjawab: apakah gerakan ditransfer? apakah audio terbawa? format/ukuran apa yang diterima? Hasil dicatat di dokumen grill 03.
2. `PublicMedia` + implementasi pilihan user.
3. Pra-pemrosesan video referensi (ffprobe, potong, normalisasi, ekstrak audio).
4. Endpoint `/api/motion` + penyimpanan metadata.
5. Halaman UI "Tiru Gerakan".
6. Tes (mock + ffmpeg nyata) dan satu uji nyata end-to-end.

## Kriteria selesai
- Dari video referensi + gambar objek + prompt dihasilkan klip di library yang gerakannya jelas mengikuti referensi (dinilai manusia pada spike dan uji akhir), atau, bila spike menunjukkan model tidak mampu, keputusan tertulis untuk beralih ke penyedia lain.
- Video referensi tidak pernah tersedia publik lebih lama dari batas umur URL, dan terhapus setelah job.
- Format/ukuran/durasi tak valid ditolak dengan pesan jelas sebelum biaya keluar.

## Perkiraan biaya
Seedance 2.5 sekitar $0,10 per detik di 480p (belum termasuk potongan tarif video-input). Spike 4 detik 480p kira-kira $0,4 sampai $0,5; varian `seedance-2.0-fast`/`-mini` kemungkinan lebih murah (belum dihitung).

## Pertanyaan terbuka (butuh keputusanmu)
1. Hosting URL publik: R2/S3 (kamu sediakan kredensial) atau tunnel sementara?
2. Boleh jalankan spike berbayar (kira-kira $0,5 maksimal) sebelum membangun?
3. Seberapa penting suara? "Suara mirip" dari video referensi mungkin tidak tercapai di Seedance; apakah cukup suara yang dihasilkan model, atau suara harus persis?
4. Kalau spike gagal (gerakan tidak ditransfer), lanjut dengan penyedia di luar OpenRouter (Kling Motion Control / Wan Animate) atau berhenti di sini?

## Sumber
- [Seedance 2.5 review](https://openrouter.ai/blog/insights/seedance-2-5-review/)
- [Video Generation docs](https://openrouter.ai/docs/guides/overview/multimodal/video-generation)
- [Reference to Video cookbook](https://openrouter.ai/docs/cookbook/video-generation/reference-to-video)
- [Video model collection](https://openrouter.ai/collections/video-models)

## Riwayat
- 2026-10-19: draft awal.
