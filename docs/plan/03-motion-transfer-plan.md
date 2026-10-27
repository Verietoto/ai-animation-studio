# 03 - Motion Transfer (Plan)

- Status: draft, sudah digrill (lihat `docs/grill/03-motion-transfer-grill.md`), menunggu persetujuan
- Tanggal: 2026-10-19

## Tujuan
Menirukan gerakan (dan suara) dari sebuah video referensi pada subjek dari sebuah gambar: input video referensi + gambar objek/karakter + prompt, output video baru yang objeknya mengikuti gerakan referensi.

Dua jalur dicoba, karena belum ada model di OpenRouter yang terbukti melakukan transfer gerakan:
- **Jalur A, "animasikan gambar"** (Seedance generasi 2+): video referensi + gambar objek sebagai `input_references`, model membuat video baru di mana objek gambar bergerak seperti referensi.
- **Jalur B, "ganti subjek di video"** (`black-forest-labs/flux-video-edit`, cadangan `runway/aleph-2`): video referensi menjadi video sumber yang diedit; subjeknya diganti sesuai prompt (dan gambar objek bila model menerimanya). Gerakan dan timing asli otomatis terjaga karena videonya sendiri yang diedit. Audio asli ditempel kembali dengan ffmpeg karena model ini tidak menghasilkan audio (`generate_audio: false`).

## Hasil riset (OpenRouter, per 2026-10-19)
Yang **terdokumentasi**:
- Model Seedance generasi 2 ke atas (`bytedance/seedance-2.5`, `-2.0`, `-2.0-fast`, `-2.0-mini`) menerima `input_references` bertipe `image_url`, `video_url`, dan audio dalam satu request (sampai 30 gambar, 10 video, 10 audio per request menurut halaman model; batas resmi endpoint tidak dipublikasikan). Video referensi ditagih dengan tarif token lebih murah ($0,0000064 vs $0,0000107 per token untuk 2.5). Sumber: [review Seedance 2.5](https://openrouter.ai/blog/insights/seedance-2-5-review/).
- Model lain dengan referensi gambar saja: Wan 3.0, Wan 2.7 (passthrough `video`/`videos`/`images`/`audio` terdaftar tapi tidak dijelaskan), HappyHorse. Model edit video: `runway/aleph-2`, `black-forest-labs/flux-video-edit` (mengedit video sumber, bukan memindahkan gerakan ke gambar). `heygen/avatar-iv`: foto + audio menjadi video bicara lip-sync (mengikuti suara, bukan gerakan video).
- **FLUX Video Edit** (`black-forest-labs/flux-video-edit`, data nyata `/videos/models` 2026-10-19): video sumber + prompt edit, "add, remove, or replace objects and characters, rebuild the setting". Harga **$0,03 per detik output**, tanpa audio, tidak ada daftar durasi/resolusi/rasio (mengikuti video sumber), passthrough `safety_tolerance`. Jauh lebih murah daripada Seedance.
- **Runway Aleph 2** (`runway/aleph-2`): edit in-context dengan instruksi teks dan keyframe (passthrough `keyframes`); $0,28 per detik, minimum $0,56 per job; tanpa audio. Cadangan bila FLUX Video Edit gagal.
- Belum diketahui untuk kedua model edit: nama field untuk video sumber (kemungkinan `input_references` bertipe `video_url`), apakah gambar objek bisa ikut sebagai referensi identitas (deskripsi hanya menyebut prompt), dan batas durasi/ukuran video sumber.
- Bila `frame_images` ikut dikirim, referensi diabaikan dan job diperlakukan sebagai image-to-video. Untuk fitur ini **jangan** kirim `frame_images`.
- `video_url` harus **URL HTTPS publik** yang bisa diunduh langsung; data URL ditolak (laporan komunitas). Gambar via data URL sudah terbukti diterima (plan 01), video belum.

Yang **belum terbukti** (inti risiko fitur ini):
- Apakah Seedance benar-benar *memindahkan gerakan* dari video referensi ke subjek gambar, atau hanya memakainya sebagai gaya/kelanjutan adegan. Dokumentasi menggambarkan "edit atau perpanjang footage" dan "ganti subjek", bukan transfer gerakan eksplisit. Perlu uji nyata dengan prompt yang jelas (mis. "gunakan gerakan di video 1 untuk karakter di gambar 1").
- Apakah suara referensi dibawa: kemungkinan lewat audio referensi + `generate_audio: true`, tanpa jaminan meniru suara/ucapan aslinya.
- Batas durasi/ukuran/format video referensi.
- Kling Motion Control dan Wan Animate (khusus transfer gerakan) **tidak ditemukan** di katalog OpenRouter; hanya tersedia di luar OpenRouter.

## Kunci karakter (permintaan user 2026-10-19)
Masalah: model video cenderung "melayang" dari wajah/pakaian karakter, dan jalur B (FLUX Video Edit) hanya menerima prompt. Cara yang diusulkan, dari yang paling murah:

1. **Entitas Karakter di aplikasi.** Nama, deskripsi teks baku (wajah, rambut, pakaian, warna; dipakai ulang di setiap prompt), dan 3 sampai 6 gambar referensi. Dipilih sekali, otomatis ikut di setiap generate. Ini juga fondasi untuk fitur episode nanti.
2. **Character sheet otomatis dari satu foto.** Edit foto (plan 02, sekitar $0,015 sampai $0,05 per gambar) membuat tampak depan, samping, tiga perempat, dan seluruh badan dengan pakaian sama di latar netral. User memilih/menyetujui sheet sebelum dipakai.
3. **Jalur A (Seedance): semua gambar sheet dikirim sebagai `input_references`** bersama video referensi, prompt menyebut "the character shown in images 1-4". Seedance 2.0 disebut OpenRouter "particularly strong at preserving character consistency". Tanpa `frame_images` (kalau dikirim, referensi diabaikan).
4. **Jalur B: metode "anchor frame".** Ambil frame pertama video referensi (ffmpeg) lalu edit foto dengan referensi sheet: "replace the person in image 1 with the character in image 2, keep pose, framing, lighting". Hasilnya dipakai sebagai keyframe untuk **Runway Aleph 2** (passthrough `keyframes`; satu gambar tanpa posisi diperlakukan sebagai frame pertama), yang menyebarkan tampilan itu ke seluruh klip. Ini alur yang didokumentasikan untuk Aleph (edit satu still, kirim kembali sebagai anchor). Untuk FLUX Video Edit, spike menguji apakah gambar anchor diterima; bila tidak, FLUX hanya untuk edit berbasis prompt.
5. **Gambar ke Video dan Extend (fitur 01)** sudah mengunci frame awal lewat `first_frame`; kunci bisa diperkuat dengan memakai pose dari sheet sebagai frame awal. Catatan: `frame_images` dan `input_references` tidak bisa digabung (frame menang), jadi sheet tidak bisa ikut di jalur ini.
6. **Cek konsistensi otomatis (opsional, eksperimental).** Beberapa frame hasil dibandingkan dengan sheet oleh model vision murah lewat OpenRouter (skor 1 sampai 10 + alasan), hasil di bawah ambang diberi peringatan. Keandalan penilaian ini belum terbukti; hanya sebagai sinyal, bukan penentu.

Yang harus dibuktikan di spike: (a) Seedance memakai sheet + video referensi sekaligus; (b) anchor frame + Aleph mempertahankan wajah di seluruh klip; (c) FLUX Video Edit menerima/mengabaikan gambar.
Biaya tambahan spike: sheet 4 gambar ≈ $0,10; anchor frame ≈ $0,02; Aleph 5 detik ≈ $1,40.

## Ruang lingkup
- Termasuk: halaman "Tiru Gerakan": unggah video referensi (dan opsional pakai audio dari video itu), pilih jalur (A: animasikan gambar / B: ganti subjek di video), pilih gambar objek (dari library, termasuk hasil edit foto; wajib untuk A, opsional untuk B bila model mendukung), prompt, model, durasi, resolusi; hasil masuk library klip.
- Jalur yang tersedia di UI hanya yang lolos spike.
- Pra-pemrosesan video referensi di server: validasi dengan ffprobe, batas durasi/ukuran, potong ke rentang yang dipilih, normalisasi ke mp4 h264, ekstraksi audio opsional.
- Tidak termasuk: fallback ke penyedia luar OpenRouter (Kling/Wan Animate) pada iterasi ini; pengenalan/penggantian wajah; kloning suara pihak ketiga; proyek berepisode.

## Desain (usulan)
- **Hosting URL publik untuk video referensi (wajib).** Opsi:
  1. *Cloudflare R2 / S3 dengan presigned GET URL berumur pendek* (rekomendasi): objek privat, URL kedaluwarsa (mis. 1 jam), dihapus setelah job selesai. Perlu akun dan kredensial dari user.
  2. Tunnel sementara ke server lokal (mis. cloudflared): tanpa akun storage, tapi server lokal terbuka selama job berjalan dan URL harus dibatasi ke satu berkas bertoken.
  Abstraksi `PublicMedia.publish(path) -> https_url` dengan dua implementasi; default dipilih user.
- Tabel `clips` mendapat kolom `kind` (`i2v`, `extend`, `motion`) dan `reference_video_path`; permintaan menyimpan `reference_asset_ids`. Klip hasil bisa di-extend seperti klip biasa.
- Backend endpoint `POST /api/motion` (multipart: video, image_id, prompt, model, durasi, resolusi, `use_reference_audio`). Validasi parameter dari `/videos/models` seperti sebelumnya, plus pemeriksaan model mendukung referensi video (daftar model yang diizinkan di config, bukan dari API karena API tidak mengekspos kemampuan itu secara terstruktur).
- **Adapter per jalur**: `ReferenceToVideo` (A: `input_references` gambar + video, tanpa `frame_images`) dan `VideoEdit` (B: video sumber + prompt). Keduanya memakai alur submit/poll/unduh yang sama dengan fitur 01.
- Jalur B: setelah unduh, audio asli video referensi ditempel ke hasil dengan ffmpeg (durasi diselaraskan, dipotong ke yang terpendek); opsi "buang audio".
- Prompt di-template (bahasa Inggris): A berisi instruksi eksplisit transfer gerakan; B berisi instruksi penggantian subjek dan larangan mengubah gerakan/kamera; user bisa mengedit.
- UI: halaman baru "Tiru Gerakan" dengan pratinjau video referensi dan gambar objek berdampingan.

## Langkah kerja
0. **Estimasi biaya sebelum setiap generate**: dipindah ke fitur tersendiri, `docs/plan/04-cost-estimate-plan.md`, dikerjakan lebih dulu.
0b. **Entitas Karakter + character sheet** (bagian "Kunci karakter"), sebelum spike agar sheet bisa diuji.
1. **Spike murah lewat skrip, tanpa membangun hosting** (temuan grill 1, 2, 5), satu video referensi yang sama untuk kedua jalur, kriteria lolos konkret di grill 03, anggaran maksimum spike ditetapkan di awal:
   - Jalur B dulu karena paling murah: FLUX Video Edit, 2 job (video referensi 4 sampai 5 detik ≈ $0,15 per job). Satu prompt saja, satu prompt + gambar objek (untuk mengetahui apakah gambar diterima/dipakai).
   - Jalur A: Seedance varian termurah yang menerima video, 480p, 4 detik, 2 job.
   - Aleph 2 hanya bila FLUX Video Edit gagal secara teknis (bukan sekadar kualitas), 1 job (minimum $0,56).
   Hasil dicatat di dokumen implementasi 03. Bila semua jalur gagal: berhenti, penyedia di luar OpenRouter jadi plan 04.
2. `PublicMedia` + implementasi pilihan user.
3. Pra-pemrosesan video referensi (ffprobe, potong, normalisasi, ekstrak audio).
4. Endpoint `/api/motion` + penyimpanan metadata.
5. Halaman UI "Tiru Gerakan".
6. Tes (mock + ffmpeg nyata) dan satu uji nyata end-to-end.

## Kriteria selesai
- Minimal satu jalur lolos kriteria spike (grill 03) dan bisa dipakai end-to-end dari UI: dari video referensi + gambar objek/prompt dihasilkan klip di library yang gerakannya mengikuti referensi; atau, bila semua jalur gagal, keputusan tertulis untuk beralih ke penyedia lain.
- Video referensi tidak pernah tersedia publik lebih lama dari batas umur URL, dan terhapus setelah job.
- Format/ukuran/durasi tak valid ditolak dengan pesan jelas sebelum biaya keluar.

## Perkiraan biaya
| Jalur | Model | Tarif | Spike |
|---|---|---|---|
| B | FLUX Video Edit | $0,03/detik output | 2 job x 5 detik ≈ $0,30 |
| A | Seedance (termurah yang lolos) | ≈ $0,10/detik di 480p untuk 2.5; varian lain belum dihitung | 2 job x 4 detik ≈ $0,80 |
| B cadangan | Runway Aleph 2 | $0,28/detik, min $0,56 | 0 atau 1 job ≈ $1,40 |
Total spike: sekitar $1,10 tanpa Aleph, sampai $2,50 bila Aleph dipakai. Biaya nyata sebelumnya 2,5x perkiraan untuk edit gambar, jadi anggaran spike diusulkan maksimum **$3** dengan berhenti otomatis bila terlampaui.

## Pertanyaan terbuka (butuh keputusanmu)
1. Hosting URL publik: R2/S3 (kamu sediakan kredensial) atau tunnel sementara?
2. Boleh jalankan spike berbayar (kira-kira $0,5 maksimal) sebelum membangun?
3. Seberapa penting suara? "Suara mirip" dari video referensi mungkin tidak tercapai di Seedance; apakah cukup suara yang dihasilkan model, atau suara harus persis?
4. Kalau semua jalur spike gagal, lanjut dengan penyedia di luar OpenRouter (Kling Motion Control / Wan Animate) atau berhenti di sini?
5. Anggaran spike maksimum $3 disetujui?

## Sumber
- [Seedance 2.5 review](https://openrouter.ai/blog/insights/seedance-2-5-review/)
- [Video Generation docs](https://openrouter.ai/docs/guides/overview/multimodal/video-generation)
- [Reference to Video cookbook](https://openrouter.ai/docs/cookbook/video-generation/reference-to-video)
- [Video model collection](https://openrouter.ai/collections/video-models)

## Riwayat
- 2026-10-19: draft awal.
- 2026-10-19: tambah bagian "Kunci karakter" (entitas karakter, character sheet, anchor frame + Aleph keyframes, cek konsistensi) dan pindahkan estimasi biaya ke plan 04, atas permintaan user.
- 2026-10-19: tambah jalur B (ganti subjek di video: FLUX Video Edit, cadangan Aleph 2) atas persetujuan user; spike dua jalur, anggaran usulan $3.
- 2026-10-19: setelah grill: tambah langkah 0 (pengaman biaya), spike tanpa hosting dengan kriteria konkret, tunnel hanya ke server berkas terpisah, definisi ulang suara, migrasi DB, upload streaming. Rincian di grill 03.
- 2026-10-21: backend plan ini (commit WIP `75b5c44`) diberi test, diperbaiki (4 bug), dan diberi UI lewat plan 09 (`docs/plan/09-frame-and-motion-reference-plan.md`). Status dan hasilnya dicatat di `docs/implementation/09-frame-and-motion-reference-implementation.md`.
