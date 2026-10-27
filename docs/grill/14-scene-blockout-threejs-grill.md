# 14 - Adegan mentah (blockout 3D) dengan three.js untuk Storyboard (Grill)

Plan terkait: `docs/plan/14-scene-blockout-threejs-plan.md` (termasuk Revisi 1: previs bergerak, disusun AI, pose per sendi).
Tanggal: 2026-10-26. Sumber:
- Kode: `motion.py` (`add_upload`, `_check_ref`, `estimate`, `SEEDANCE`), `db.py` (`committed_today`, skema `refs`), `service.py` (`authorize`), `main.py` (`/api/references`), `openrouter.py`, `config.py`.
- Gratis: `GET /models`, `GET /videos/models`, `npm view three` / `@types/three`.
- Estimasi dihitung dengan `pricing.estimate_video` pada katalog nyata, tanpa panggilan berbayar.

## Temuan yang mengubah plan
1. **Biaya AI penyusun tidak masuk anggaran harian.** `committed_today` hanya menjumlahkan `clips` dan `images`. Panggilan model teks perlu baris biaya sendiri, kalau tidak batas harian bisa dilewati diam-diam.
2. **Batas spike $0.20 hanya cukup untuk satu uji Seedance.** Seedance reference minimal 4 detik. Estimasi aplikasi: Seedance 2.0 Mini 480p 4 detik **$0.177**, 5 detik $0.222; 2.0 Fast 4 detik $0.209. Ditambah AI penyusun (< $0.01), totalnya ≈ $0.18. Perbandingan keyframe dengan dan tanpa panduan tidak muat.
3. **Agent tidak bisa merender previs three.js** (aturan proyek: agent tidak membuka browser). Uji Seedance dengan video three.js asli hanya bisa dilakukan setelah editor jadi dan user merender satu previs.
4. **Batas video referensi 10 detik** (`MAX_REFERENCE_SECONDS`), sedangkan previs bisa sampai 15 detik. Previs yang lebih panjang harus dipotong dulu (trim untuk unggahan berjalan lokal, plan 11) sebelum dipakai di Tiru Gerakan.
5. **Pemeriksaan ukuran minimum Seedance (854×480) hanya berlaku untuk referensi dari klip** (`_check_ref` memeriksa `source_clip_id`), bukan untuk unggahan. Previs harus dirender minimal 854×480 (16:9) atau 480×854 (9:16), kalau tidak Seedance menolak di sisi provider setelah job dikirim.

## Lubang pada plan
1. Tidak ada pencatatan biaya untuk model teks (temuan 1).
2. Previs diunggah ulang setiap kali dirender, jadi `refs` dan berkasnya menumpuk. Tabel `refs` tidak punya penghapusan. Ini utang yang sama dengan hasil trim.
3. Satu tabel batas sendi di dua tempat (frontend dan backend) akan menyimpang.
4. Pemeran yang dilepas dari adegan setelah susunan dibuat: susunan menyimpan `character_id` yang basi.
5. `MediaRecorder` merekam waktu nyata. Tab yang disembunyikan memperlambat `requestAnimationFrame`, sehingga rekaman rusak. Safari merekam MP4, Chrome dan Firefox WebM.
6. Duplikasi adegan (`Scenes.duplicate`) belum menentukan nasib susunan dan previs.
7. Tidak ada test runner frontend; logika interpolasi, siklus jalan, dan batas sendi hanya bisa dicek lewat build dan uji manual user.

## Risiko
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| Seedance tidak mengikuti gerak manekin, atau menyalin tampilan abu-abu | Fitur "previs → video" tidak berguna | Sedang | Spike dengan previs asli buatan user. Editor dan previs tetap berguna sebagai pratinjau bila gagal. |
| JSON dari AI rusak atau di luar batas | Susunan aneh, error | Sedang | Structured outputs (`response_format` JSON schema); server memangkas angka, membuang key tidak valid, menolak bila tidak ada yang valid. |
| Biaya AI tidak tercatat | Batas harian bocor | Pasti (bila tidak ditangani) | Tabel `text_jobs` ikut dijumlahkan `committed_today`. |
| three.js masuk bundel utama | Aplikasi lambat dimuat | Rendah | Import dinamis di dalam Storyboard (yang sudah lazy); dicek di keluaran build. |
| WebGL tidak tersedia | Editor kosong | Rendah | Deteksi dan pesan; Storyboard lain tetap jalan. |
| Rekaman rusak karena tab disembunyikan | Video tersendat | Sedang | Rekaman dibatalkan bila `document.hidden`, dengan pesan. |
| Prompt injection lewat naskah | Rendah: keluaran hanya data | Rendah | Keluaran divalidasi skema; tidak ada eksekusi. |

## Edge case
- Adegan tanpa pemeran: AI tetap menyusun kamera dan properti; manekin nol.
- Adegan tanpa `planned_seconds`: previs 5 detik.
- Pemeran dilepas setelah susunan dibuat: aktor dengan `character_id` yang tidak lagi di adegan dibuang saat dimuat; penyimpanan menolak id di luar pemeran.
- Film sedang dirender: simpan dan "Susun dengan AI" ditolak (`_editable`).
- Rasio 9:16: previs 720×1280.
- Previs > 10 detik dipakai di Tiru Gerakan: pesan "potong dulu" yang sudah ada.
- Duplikasi adegan: JSON susunan ikut disalin; previs dan render diam tidak (dibuat ulang).

## Potensi bug
1. Key waktu tidak urut atau ganda: server mengurutkan, menyatukan `t` yang sama.
2. Interpolasi rotasi lewat Euler menghasilkan putaran salah arah: pakai quaternion slerp.
3. Siklus jalan menimpa pose eksplisit dari AI: siklus hanya pada pinggul/lutut, dan hanya di segmen tanpa key pose kaki di antaranya.
4. Unggahan previs memakai `/api/references` yang sudah ada; `prepare_reference_video` menambahkan audio kosong. Tidak masalah, tetapi dicek tidak menggandakan durasi.

## Asumsi yang belum terbukti
- Haiku 5.5 bisa menyusun posisi dan kamera yang masuk akal dari naskah. Diuji di spike langkah 1 (murah).
- Seedance reference mengikuti gerak previs manekin dan memakai penampilan dari gambar karakter. Diuji setelah editor jadi.
- 15 sendi dengan pustaka pose cukup untuk "ga detail".

## Keputusan setelah grilling (perubahan pada plan)
- **Model teks:** `anthropic/claude-haiku-5.5` ($0.10/M input, $0.50/M output, mendukung structured outputs). `max_tokens` 6000. Estimasi = token prompt (panjang/3) × harga input + 6000 × harga output, sekitar $0.003. Biaya nyata dari `usage.cost`.
- **Tabel baru `text_jobs`** (`id, kind, model, cost, estimated_cost, scene_id, workspace_id, created_at`) di migrasi v11. `committed_today` ikut menjumlahkannya.
- **Batas sendi hanya di frontend** (tempat pose diterapkan). Server hanya memvalidasi struktur, angka finite, rentang ±180°, nama sendi dari daftar tetap.
- **Previs lama dibersihkan saat render ulang:** referensi previs sebelumnya untuk adegan itu dihapus (berkas + baris) bila tidak dipakai klip mana pun (`clips.reference_id`).
- **Render previs:** 1280×720 atau 720×1280, 24 fps, `MediaRecorder` dengan mime yang didukung, batal bila tab disembunyikan; server mentranskode lewat jalur unggahan referensi yang ada.
- **Urutan kerja diubah:** (a) spike AI penyusun (< $0.02, bagian dari batas $0.20); (b) backend + editor; (c) user merender satu previs 4 detik; (d) satu uji Seedance 2.0 Mini 480p 4 detik ($0.177) dengan previs itu. Perbandingan keyframe dengan panduan **tidak** dijalankan dengan batas sekarang (perlu tambahan sekitar $0.10).
- Logika data frontend (interpolasi, siklus jalan, batas sendi) dibuat sebagai modul murni tanpa React di `storyboard/blockoutMath.ts` supaya mudah diperiksa; diuji manual oleh user.

## Riwayat
- 2026-10-26: grill awal.
