# 09 - Frame akhir + Tiru Gerakan di UI (Plan)

- Status: disetujui, diimplementasi (lihat implementation 09)
- Tanggal: 2026-10-21

## Tujuan
Permintaan user: "image to video masih belum bisa pake referensi frame dan video yang diikuti".

1. **Frame akhir (referensi frame).** Gambar→Video sekarang hanya mengunci frame awal. User ingin memberi gambar kedua sebagai frame akhir, supaya model membuat transisi dari A ke B.
2. **Video yang diikuti (tiru gerakan).** Backend plan 03 sudah ada di `backend/app/motion.py`: referensi video, anchor frame, tiga mode, dan endpoint `/api/references*`, `/api/motion*`, serta estimasi `motion`/`motion_anchor`. Yang belum ada adalah UI dan test. Fitur ini membuatnya bisa dipakai dari aplikasi.

## Keadaan sekarang (dicek 2026-10-21)
- `Studio.create_clip` mengirim `frame_images` hanya dengan `frame_type: "first_frame"`. Tidak ada parameter frame akhir.
- Katalog `/videos/models` (fixture) sudah memberi `supported_frame_images`:
  - Model dengan `last_frame`: Seedance 2.x/1.5, Kling v3/o1, Veo 3.1, Wan 2.7/3.0, Hailuo 3, FLUX 3 video.
  - Model tanpa `last_frame`: Grok Imagine, Runway gen-4.5, HappyHorse, Hailuo 2.3, Wan 2.6.
  - Frontend sudah menerima `capabilities.last_frame` (dipakai sebagai label di `catalog.tsx`).
- Tiru Gerakan:
  - Mode dan hasil spike plan 03:
    - `flux_edit`: ganti subjek di video, prompt saja, ±$0,03/dtk, identitas perkiraan.
    - `anchor_edit`: kunci karakter lewat anchor frame + Runway Aleph 2, $0,28/dtk, minimum $0,56, identitas lolos.
    - `reference`: Seedance, animasikan gambar dengan gerakan video. Ditolak moderasi untuk orang foto-realistik; hanya untuk kartun/ilustrasi.
  - Video referensi harus berupa URL HTTPS publik:
    - Klip dari library memakai URL bertanda tangan OpenRouter, yang kedaluwarsa ±24 jam setelah klip dibuat. Ini gratis dan tanpa setup.
    - Video unggahan butuh S3/R2 (`S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ENDPOINT_URL`). Tanpa itu, backend menjawab 501.
  - Plan 03 berstatus "menunggu persetujuan" dan tidak punya file implementation. Kodenya masuk lewat commit WIP `75b5c44`. Plan ini sekaligus menutup plan 03 (Riwayat plan 03 diberi catatan).

## Ruang lingkup
Termasuk:
- **A. Frame akhir di Gambar→Video.**
  - Picker "Frame akhir (opsional)" di inspector halaman Buat. Picker hanya muncul bila model yang dipilih mendukung `last_frame`. Bila model diganti ke yang tidak mendukung, pilihan dikosongkan dan ada catatan singkat.
  - Backend menerima `last_image_id`.
- **B. Halaman "Tiru Gerakan"** (`#/motion`, ikon di sidebar), di atas backend plan 03.
- Test backend untuk A dan untuk `motion.py`. `motion.py` belum punya test sama sekali; FakeOpenRouter dipakai, tanpa biaya.

Tidak termasuk (bisa menyusul):
- Frame akhir di Storyboard (mis. "akhiri di keyframe adegan berikutnya"). Ini ide bagus, tapi baru setelah A terbukti di halaman Buat.
- Frame akhir di Extend.
- Cek konsistensi otomatis (plan 03 butir 6).
- Penyedia di luar OpenRouter.
- Halaman pengaturan S3 di UI. Konfigurasi tetap lewat `.env`.

## Desain

### A. Frame akhir
- `ClipIn.last_image_id: str | None`. `create_clip` menerimanya dan mengecek dua hal:
  - Model punya `last_frame`. Bila tidak: 400 "model X tidak mendukung frame akhir".
  - Gambar ada di workspace yang sama. Bila tidak: 404.
- Payload `frame_images` mendapat elemen kedua `{"type":"image_url","image_url":{"url":…},"frame_type":"last_frame"}`.
- `last_image_id` disimpan di `params` (JSON, tanpa migrasi). `public_clip` mengeluarkannya supaya Lightbox bisa menampilkan "frame akhir" di jejak asal.
- Estimasi: harga per detik tidak berubah menurut katalog. Bila spike menunjukkan sebaliknya, estimator diperbaiki.
- Rasio: bila rasio frame awal dan akhir jauh berbeda (> 10%), UI memberi peringatan. Tidak diblokir, karena perilaku model belum diketahui.

### B. Halaman Tiru Gerakan
Alur dalam satu halaman (layout `Stage`: kanvas + inspector):

1. **Video referensi** (kanvas atas):
   - "Pilih dari library": klip selesai → `POST /api/references/from-clip/{id}`. Berlaku hanya ±24 jam sejak klip dibuat; klip yang lebih tua diberi label "mungkin kedaluwarsa".
   - "Unggah video": `POST /api/references`. Tombol ini aktif hanya bila S3 terpasang (`/api/health` mendapat `public_media: bool`). Bila tidak aktif, ada penjelasan singkat cara memasang S3/R2.
   - Pratinjau video referensi, durasi, dan apakah video dipotong ke `MAX_REFERENCE_SECONDS`.
2. **Mode**: tiga kartu dengan label jujur dari hasil spike, harga per detik, dan kapan dipakai:
   - "Ganti subjek (murah)": `flux_edit`, karakter opsional; deskripsinya ditambahkan ke prompt.
   - "Kunci karakter (mahal, paling mirip)": `anchor_edit`, karakter wajib, dua langkah berbayar:
     1. "Buat anchor frame": edit gambar, dialog biaya sendiri, hasil ditampilkan.
     2. "Buat video": Aleph. Tombol ini aktif setelah anchor ada; anchor bisa dibuat ulang.
   - "Animasikan gambar (kartun/ilustrasi)": `reference`, karakter dan/atau gambar subjek, durasi/resolusi/rasio/suara dari katalog Seedance. Ada peringatan bahwa orang foto-realistik ditolak.
3. **Prompt**: template bawaan per mode (bahasa Inggris, sesuai yang lolos spike) yang bisa diedit.
4. **Biaya**: `useEstimate` + `useConfirmedRun` (pintu tunggal). Kind `motion`/`motion_anchor` sudah ada di `/api/estimate`.
5. **Hasil**: klip masuk QueueDock dan Library seperti klip lain. Klip `kind: motion` bisa dipakai di Storyboard lewat picker video adegan yang sudah ada.

Pesan moderasi (Seedance/Seedream) diterjemahkan jadi pesan Indonesia dengan saran ganti mode/model. Ini sekalian menjawab keluhan error Seedream kemarin. Pengaturannya ada di satu tempat, `api.ts`, berdasarkan pola teks "moderation" / "SensitiveContent".

## Risiko awal (bahan grill)
- `motion.py` belum pernah dijalankan dari UI dan tanpa test. Bisa ada bug yang baru ketahuan sekarang, mis. `_public_url` menunggu `time.sleep` di dalam `st._lock` sampai 10 detik.
- URL klip kedaluwarsa 24 jam. User akan bingung kalau klip lama gagal; pesan error harus jelas.
- Frame akhir belum pernah diuji nyata. Kualitas transisi dan apakah biayanya sama dengan tanpa frame akhir masih harus dibuktikan.
- Biaya Aleph tinggi. Satu klik salah = $1,40 untuk 5 detik. Dialog konfirmasi wajib, dan batas per job $1 (bawaan) sudah otomatis memblokir Aleph 5 detik. Ini harus terlihat jelas di UI, bukan hanya error 402.

## Langkah kerja
1. Backend A: `last_image_id` di `ClipIn`/`create_clip`/`public_clip`. Test: payload berisi dua frame, model tanpa `last_frame` ditolak, workspace lain 404, estimasi sama.
2. Test `motion.py` dengan FakeOpenRouter: tiga mode, referensi dari klip, unggahan tanpa S3 → 501, moderasi → 422, anchor wajib untuk `anchor_edit`. Perbaiki bug yang ditemukan.
3. `/api/health` + `public_media`.
4. Frontend A: picker frame akhir di `pages/Generate.tsx`.
5. Frontend B: `pages/Motion.tsx` + `api.ts` (references, anchor, motion) + sidebar/route/palette.
6. Pesan moderasi yang ramah.
7. Spike nyata kecil (butuh persetujuan anggaran):
   - 1× frame akhir di model murah, mis. Seedance 2.0 mini 4 dtk 480p ≈ $0,15.
   - 1× `flux_edit` dari klip library ≈ $0,15.
   - Total maksimum diusulkan **$0,50**.
8. Dokumen implementation 09 + Riwayat plan 03.

## Kriteria selesai
- `make test` hijau, termasuk test baru untuk A dan `motion.py`. `npm run build` hijau.
- Spike: satu klip dengan frame akhir dan satu klip `flux_edit` berhasil dari backend nyata, dengan biaya tercatat.
- Uji frontend dilakukan manual oleh user (daftar alur ditulis di implementation 09).

## Pertanyaan terbuka
1. Video referensi cukup dari klip library dulu, atau kamu mau pasang S3/R2 supaya bisa unggah video sendiri (mis. rekaman HP)? Tanpa S3, tombol unggah nonaktif.
2. Anggaran spike $0,50 untuk langkah 7 disetujui?
3. Batas per job bawaan $1 memblokir Aleph 5 detik ($1,40). Biarkan (pilih durasi referensi ≤ 3 dtk), atau kamu naikkan `MAX_COST_PER_JOB_USD`?

## Riwayat
- 2026-10-21: draft awal.
- 2026-10-21: user menyetujui ("ya"). Setelah grill:
  - Tiga bug di `motion.py` diperbaiki dulu sebelum UI: `ws` tidak diteruskan ke estimate, `sleep` di dalam lock, dan `n_inputs` anchor tetap 3.
  - `friendlyError()` dipakai juga untuk `clip.error`.
  - Pertanyaan terbuka diisi dengan pilihan aman: referensi hanya dari library, batas $1 tetap, spike menunggu anggaran eksplisit.
  - Rincian di grill 09.
- 2026-10-21: diimplementasi. Satu bug tambahan ditemukan saat test (`/api/motion` TypeError). Spike berbayar belum dijalankan.
