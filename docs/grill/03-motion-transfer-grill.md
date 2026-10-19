# 03 - Motion Transfer (Grill)

Plan terkait: `docs/plan/03-motion-transfer-plan.md`

Keparahan: **T** tinggi, **S** sedang, **R** rendah.

## Lubang pada plan

1. **(T) Spike butuh URL publik, padahal hosting baru dibangun di langkah 2.** Urutan plan melingkar: spike (langkah 1) tidak bisa jalan tanpa `PublicMedia` (langkah 2).
   - Mitigasi: spike memakai video referensi yang **sudah** berada di URL HTTPS publik (klip contoh bebas lisensi atau berkas yang kamu unggah sendiri ke tempat publik sementara), dikirim lewat skrip, tanpa kode aplikasi. Hosting baru dibangun bila spike lolos.

2. **(T) Kriteria lolos spike kabur.** "Gerakan jelas mengikuti referensi, dinilai manusia" tidak bisa diputuskan dan rawan bias, apalagi model generatif bersifat acak: satu sampel tidak representatif.
   - Mitigasi: kriteria konkret ditulis sebelum spike. Video referensi dengan urutan gerak khas dan mudah dihitung (mis. angkat tangan kanan, lalu berputar ke kiri, lalu melompat) + gambar subjek yang jelas berbeda. Lolos bila pada **2 dari 2** percobaan urutan gerak muncul dalam urutan yang sama **dan** identitas subjek gambar terjaga. Dua prompt: satu netral, satu instruksi eksplisit ("use the motion from video 1 for the character in image 1"). Total 2 sampai 4 job.

3. **(T) Pengaman biaya yang ada tidak mencegah satu job mahal.** Kode sekarang (`Studio._check_budget`) hanya menolak bila *biaya yang sudah terpakai* ≥ batas harian. Satu job Seedance 2.5 30 detik 720p (sekitar $6,9) tetap lolos walau batas $5. Ini **bug di fitur 01 yang sudah jalan**, bukan hanya risiko fitur 03, dan fitur 03 justru memakai model termahal.
   - Mitigasi: estimasi biaya per job dari `pricing_skus` sebelum kirim; tolak bila `terpakai + estimasi > batas` atau estimasi > `MAX_COST_PER_JOB_USD`. Bila harga tidak bisa dihitung (satuan token), pakai perkiraan konservatif per detik per resolusi, atau minta konfirmasi eksplisit. Perbaiki untuk semua jenis job, bukan hanya motion.

4. **(T) Asumsi "Seedance memindahkan gerakan" mungkin keliru, dan kegagalannya bisa diam-diam.** Model bisa mengabaikan video referensi dan tetap menghasilkan video generik yang **tetap ditagih**. Tidak ada sinyal error.
   - Mitigasi: spike (nomor 2) adalah gerbang; di UI, beri label "eksperimental" dan simpan prompt + referensi di metadata agar hasil bisa dibandingkan. Jangan janjikan transfer gerakan di UI sebelum terbukti.

5. **(T) Bug mode edit Seedance yang sudah diketahui diabaikan plan.** Laporan typescript-sdk #1096: request dengan referensi video meminta `duration=-1` dan `aspect_ratio=adaptive`, yang tidak diterima OpenRouter. Akibatnya job bisa ditolak, atau durasi/rasio keluaran tidak sesuai permintaan (dan biaya mengikuti durasi aslinya).
   - Mitigasi: spike juga mencatat apakah request dengan `duration` eksplisit diterima dan berapa durasi keluaran nyata. Validasi durasi keluaran vs permintaan setelah unduh; selisih dicatat.

6. **(T) Opsi tunnel bisa membuka aplikasi utama ke internet.** Aplikasi tidak punya login dan bisa menghabiskan saldo OpenRouter. Bila tunnel diarahkan ke port aplikasi, siapa pun yang tahu URL bisa membuat job berbayar.
   - Mitigasi: tunnel (bila dipilih) **hanya** ke server berkas statis terpisah yang melayani satu berkas per token acak, mati otomatis setelah job selesai atau timeout. Tidak pernah ke port aplikasi. Rekomendasi tetap R2/S3 presigned.

7. **(S) Umur presigned URL vs waktu antre.** Plan menetapkan 1 jam, tetapi tidak diketahui kapan provider mengambil video: saat submit atau saat job mulai diproses. Job yang antre lama bisa gagal karena URL kedaluwarsa. Sebaliknya, menghapus berkas "setelah job selesai" tidak berlaku bila server mati sebelum itu.
   - Mitigasi: umur URL sama dengan `JOB_TIMEOUT_SECONDS` (default 30 menit) + margin; pembersih berkas di startup untuk objek yang lebih tua dari batas; aturan lifecycle bucket (hapus otomatis setelah 1 hari) sebagai lapisan kedua.

8. **(S) Lingkup suara bertentangan dengan dirinya sendiri.** Tujuan menyebut meniru "suara", tetapi ruang lingkup mengecualikan "kloning suara pihak ketiga". Yang sebenarnya bisa dilakukan Seedance adalah memakai audio referensi sebagai acuan, tanpa jaminan meniru suara/ucapan.
   - Mitigasi: definisikan ulang: "pakai audio dari video referensi sebagai referensi audio" (opsional) atau "pakai audio asli apa adanya" (gabungkan audio referensi ke hasil dengan ffmpeg, tanpa model). Yang kedua deterministik dan murah; tawarkan sebagai pilihan.

9. **(S) Migrasi database tidak direncanakan.** Plan menambah kolom `kind` dan `reference_video_path` ke `clips`, tetapi skema memakai `CREATE TABLE IF NOT EXISTS`, jadi DB yang sudah ada tidak berubah dan query kolom baru akan error.
   - Mitigasi: migrasi sederhana bernomor (`PRAGMA user_version`) dengan `ALTER TABLE ... ADD COLUMN`, plus tes yang membuka DB versi lama.

10. **(S) Upload video dibaca penuh ke memori dengan batas 20 MB.** Video referensi umumnya lebih besar; `await file.read()` memuat semuanya ke RAM.
    - Mitigasi: simpan streaming ke disk dengan batas terpisah `MAX_VIDEO_UPLOAD_MB`, validasi dengan ffprobe setelah tersimpan, lalu potong/kompres ke batas provider.

## Risiko

| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| Moderasi menolak wajah manusia nyata pada referensi (umum pada model ByteDance) sehingga kasus pakai utama gagal | Tinggi | Sedang | Uji di spike dengan foto orang dan dengan karakter ilustrasi; tampilkan alasan penolakan asli |
| Deepfake/peniruan: menempelkan gerakan dan suara orang nyata ke wajah orang lain | Tinggi | Sedang | Persetujuan eksplisit di UI (hak atas video dan gambar), simpan asal aset; tolak di dokumentasi penggunaan untuk orang nyata tanpa izin |
| Hak cipta video referensi (klip media sosial, musik di audio) | Sedang | Tinggi | Peringatan di UI; opsi buang audio; tidak ada impor dari URL media sosial |
| Video dan gambar pengguna dikirim ke pihak ketiga (OpenRouter, ByteDance) dengan kebijakan retensi yang tidak kita kendalikan | Sedang | Tinggi | Nyatakan di UI; hapus salinan publik secepatnya |
| Biaya input video ikut dihitung (token input video), sehingga estimasi hanya dari durasi output terlalu rendah; edit gambar sebelumnya 2,5x perkiraan | Sedang | Tinggi | Ukur biaya nyata di spike; faktor koreksi di estimator |
| Varian murah (`2.0-fast`/`-mini`) mungkin tidak mendukung referensi video walau satu generasi | Sedang | Sedang | Daftar model yang diizinkan diisi hanya dari hasil uji nyata |
| Seedance minimal 4 detik, jadi tidak ada uji "1 detik murah" seperti fitur 01 | Rendah | Tinggi | Anggarkan spike sesuai, 480p |

## Edge case
- Rasio video referensi (mis. 9:16 dari ponsel) berbeda dengan gambar objek (16:9) dan rasio output: tentukan aturan (ikuti referensi, ikuti gambar, atau pilih) dan normalisasi sebelum kirim.
- Video referensi lebih panjang dari batas provider: wajib pilih rentang; default potong ke durasi output.
- Video referensi tanpa audio sementara `use_reference_audio` aktif: matikan otomatis dengan pemberitahuan.
- Video dengan rotasi metadata, VFR, codec tidak umum (HEVC/ProRes), atau beberapa trek audio: normalisasi ke h264 + aac stereo CFR.
- Gambar objek dengan beberapa orang, atau objek bukan makhluk (meja, mobil): hasil tak terdefinisi; peringatkan.
- Pengguna mengirim `frame_images` sekaligus (mis. dari alur "jadikan video"): referensi akan diabaikan diam-diam; backend harus menolak kombinasi ini untuk jenis `motion`.
- Klip hasil motion lalu di-extend lewat frame terakhir: gerakan referensi tidak berlanjut; jelaskan di UI.

## Potensi bug
- Menghapus berkas publik sebelum provider selesai mengunduh (mis. menghapus saat status `in_progress`).
- Retry job yang gagal memakai URL yang sudah kedaluwarsa atau dihapus: publish ulang setiap retry.
- Kebocoran presigned URL di log atau respons API: URL itu memberi akses baca; perlakukan seperti rahasia.
- Idempotency key per permintaan motion: upload ganda membuat dua salinan publik.
- Prompt template berbahasa Indonesia: kemungkinan dipahami lebih lemah oleh model; template default berbahasa Inggris, teks user tetap bebas.

## Asumsi yang belum terbukti
- `video_url` lewat data URL ditolak (hanya dari laporan komunitas; bisa diuji gratis? tidak: memerlukan submit job).
- Seedance menerima video referensi lewat OpenRouter tanpa `duration=-1`.
- Batas durasi/ukuran video referensi.
- Gerakan benar-benar ditransfer, dan audio referensi memengaruhi audio hasil.

## Keputusan setelah grilling (perubahan pada plan)
1. **Langkah 0 baru:** perbaiki pengaman biaya (estimasi per job + `MAX_COST_PER_JOB_USD`) untuk semua job, karena celah ini sudah ada di kode yang berjalan.
2. **Spike tanpa membangun hosting**: skrip saja, video referensi di URL publik yang sudah ada, kriteria lolos konkret, 2 sampai 4 job, anggaran maksimum spike ditetapkan di awal (usul $2).
3. Tunnel hanya ke server berkas terpisah bertoken; tidak pernah ke aplikasi.
4. Suara didefinisikan ulang: (a) audio asli ditempel ke hasil dengan ffmpeg, atau (b) audio sebagai referensi model (eksperimental).
5. Tambah migrasi DB, upload video streaming, aturan rasio, label eksperimental, dan persetujuan hak aset di UI.
6. Bila spike gagal: berhenti dan tulis keputusan; penyedia di luar OpenRouter dibuat plan terpisah (04), bukan ditambal ke plan ini.

## Riwayat
- 2026-10-19: draft awal.
