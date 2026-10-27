# 14 - Adegan mentah (blockout 3D) dengan three.js untuk Storyboard (Implementation)

Plan: `docs/plan/14-scene-blockout-threejs-plan.md` (+ Revisi 1) · Grill: `docs/grill/14-scene-blockout-threejs-grill.md`
Tanggal: 2026-10-26 · Status: backend selesai dan teruji (256 test); editor 3D selesai dibangun (build hijau) dan **menunggu uji manual oleh user**. Uji Seedance dengan previs asli belum dijalankan (butuh previs yang dirender user).

## Yang dibangun
### Backend
- `blockout.py` (baru, murni): `clean()` memvalidasi dan menormalkan susunan; `SYSTEM` + `user_prompt()` untuk AI penyusun.
  - Batas: ≤ 12 key per jalur, ≤ 50 properti, ≤ 3 aktor, 64 KB, durasi 1–15 dtk, koordinat ±100 m, lensa 10–200 mm, angka harus finite.
  - Daftar tetap: 7 pose, 16 sendi, 3 jenis properti. Aktor hanya pemeran adegan, tanpa duplikat. Key dengan waktu sama digabung, hasil diurutkan.
  - Konvensi sumbu di prompt: Y atas, lantai y=0, `facing` 0 = menghadap +Z, 90 = +X.
- `db.py`: migrasi **v11** (`scenes.blockout`, `blockout_image_id`, `previs_ref_id`), tabel `text_jobs`; `committed_today()` ikut menjumlahkan `text_jobs`.
- `config.py`: `BLOCKOUT_MODEL` (bawaan `anthropic/claude-haiku-5.5`).
- `openrouter.py`: `list_models()`, `chat_json()` (chat completions dengan keluaran JSON).
- `scenes.py`:
  - `update()` menerima `blockout` (divalidasi terhadap pemeran adegan) dan `blockout_image_id`; `public()` mengeluarkan ketiganya; `duplicate()` menyalin susunan.
  - `blockout_estimate()`: token masuk (≈ karakter/3) × harga katalog + 2000–6000 token keluar × harga keluar. Alur biaya plan 04 dipakai utuh (`authorize`).
  - `generate_blockout()`: hasil berupa **draf** (tidak disimpan). Biaya dicatat di `text_jobs` sebelum parsing. Aktor di luar pemeran atau ganda dibuang, durasi dipaksa mengikuti adegan, lalu `clean()`. Balasan tidak terbaca / tidak valid → 502.
  - `attach_previs()`: previs lama dihapus (berkas + baris) bila tidak dipakai klip mana pun.
- `service.py`: `delete_image` mengosongkan `scenes.blockout_image_id`.
- `main.py`: `SceneUpdateIn.blockout/blockout_image_id`, estimasi kind `scene_blockout`, `POST /api/scenes/{id}/blockout`, `POST /api/scenes/{id}/previs` (unggah lewat jalur referensi yang ada).
- `media.py`: **perbaikan bug nyata** pada `probe()`: WebM dari `MediaRecorder` browser tidak punya durasi di header (`N/A`) sehingga `float("N/A")` melempar `ValueError` (500). Kini durasi dihitung dari hasil dekode bila header kosong. Berlaku juga untuk unggahan video biasa.

### Frontend
- `storyboard/blockoutMath.ts` (baru, tanpa React/three.js): tipe, pustaka 7 pose, batas 16 sendi, interpolasi (posisi/kamera linear, sudut hadap lewat jalur terpendek), siklus jalan/lari prosedural, lambaian, `fovFor`, `upsertKey`/`removeKeyAt`, `defaultLayout` (susunan awal dari pemeran + teks kamera), `alignToCast`.
- `storyboard/blockoutScene.ts` (baru): manekin 16 sendi dari primitif dengan label nama dan "hidung" penanda arah, properti, lantai + grid, pencahayaan.
- `storyboard/Blockout.tsx` (baru, dimuat dinamis): viewport (kamera bebas / lihat dari kamera), timeline dengan putar dan geser, auto-key (mengubah nilai menulis key di waktu sekarang), daftar objek, editor kamera/aktor (pose + slider per sendi dengan batas)/properti, "Susun dengan AI" (estimasi + dialog konfirmasi + "Kembalikan sebelum draf AI"), simpan, dan **Simpan & render previs**.
- Render previs: kanvas offscreen 1280×720 (atau 720×1280), `captureStream(24)` + `MediaRecorder`, real-time selama durasi susunan; dibatalkan bila tab disembunyikan. Frame pertama disimpan sebagai gambar (`blockout_image_id`). Video diunggah ke `/api/scenes/{id}/previs`.
- `Inspector.tsx`: section "Previs 3D (blockout)" dengan render diam, video previs, dan tombol pembuka editor. `Storyboard.tsx` meneruskan rasio film.
- `api.ts`, `styles.css`: tipe, `sceneBlockout`, `scenePrevis`, gaya `.bo-*`.
- `three@0.186.1` dan `@types/three@0.186.0` (versi pasti, berumur > 2 minggu). Terpisah di chunk `Blockout-*.js` (581 kB, gzip 147 kB); bundel utama tetap ±340 kB.

## Spike AI penyusun (berbayar, dalam batas $0.20 yang disetujui)
`scripts/spike_blockout.py`, 2 adegan nyata dengan Haiku 5.5:
- Adegan 1 (warung kopi, 2 pemeran, kamera dolly in): valid, $0.00113. Rani duduk lalu melambai, Budi berjalan masuk dari pintu ke meja, kamera 2 key, 3 properti.
- Adegan 2 (jalan desa 9:16, kamera mengikuti dari belakang): valid, $0.00066. Rani berlari menjauhi kamera, kamera ikut bergerak.
- Total **$0.0018**. Semua sampel pose/kamera dari kedua susunan finite (dicek dengan node).
- Temuan: AI menyimpulkan sendiri konvensi arah hadap (0 = +Z, 90 = +X); saya menuliskannya eksplisit di prompt.

## Temuan grill yang ditangani
| Grill | Penanganan |
|---|---|
| Biaya model teks tidak masuk anggaran | `text_jobs` + `committed_today`. Test `test_generate_returns_draft_without_saving_and_counts_cost`, `test_daily_budget_blocks_generation`. |
| Balasan rusak tetap berbiaya | Dicatat sebelum parsing. Test `test_unreadable_answer_is_502_but_cost_is_still_recorded`. |
| Biaya tidak ada di respons | Jatuh ke estimasi. Test `test_missing_cost_falls_back_to_estimate`. |
| Pemeran basi | Server menolak aktor non-pemeran; editor membuangnya saat memuat (`alignToCast`). |
| Previs menumpuk | `attach_previs` membersihkan yang lama bila tidak dipakai klip. Dua test. |
| Rekaman rusak saat tab disembunyikan | Perekaman dibatalkan dengan pesan. |
| Ukuran minimum Seedance | Previs dirender 1280×720 / 720×1280. |
| Duplikasi adegan | Susunan ikut disalin; previs dan render diam tidak. |
| Film sedang dirender | AI penyusun ditolak oleh `_editable`. |
| Bundel utama | three.js dimuat dinamis. |

## Menyimpang dari plan
- **Tanpa gizmo TransformControls.** Posisi, putaran, dan ukuran diubah lewat kolom angka dan slider (sesuai "tidak detail"). Gizmo bisa ditambah bila terasa kurang.
- **Keyframe dengan panduan blockout (`use_blockout`) ditunda.** Tidak muat dalam batas biaya uji dan belum terbukti; editor dan previs tetap berguna tanpanya. Perlu spike tambahan (±$0.10) bila diinginkan.
- Interpolasi sendi **linear pada sudut Euler**, bukan slerp kuaternion. Sudut hadap memakai jalur terpendek. Karena semua sendi dibatasi dalam rentang < 180°, tidak ada pembalikan arah.
- 16 sendi yang dapat diatur (perut, dada, leher, kepala, bahu/siku/pergelangan tangan ×2, pinggul/lutut/pergelangan kaki ×2); akar (panggul) digerakkan lewat posisi dan pose.
- Tujuh test migrasi lama diubah dari `user_version == 10` menjadi `== 11` (hanya nomor versi).
- Utang: referensi previs milik adegan yang dihapus tidak dibersihkan; hasil trim lama juga belum.

## Hasil tes
- `make test`: **256 passed** (214 → 221 plan 12 → 228 plan 13 → 256).
  - `backend/tests/test_blockout.py`: validasi (13 kasus), simpan/muat, aktor basi, duplikat, gambar blockout dibersihkan saat gambar dihapus, isolasi workspace, AI penyusun (konfirmasi, draf, biaya, JSON rusak, susunan tidak valid, biaya hilang, batas harian), previs (ganti, dipakai klip, bukan video, **WebM tanpa header durasi**), skema segar v11.
  - `conftest.py`: model teks dan `/chat/completions` palsu.
- `cd frontend && npm run build`: hijau.
- Logika `blockoutMath.ts` diperiksa dengan node (bukan browser): susunan AI dari spike finite di seluruh waktu, sudut hadap jalur terpendek, pose duduk, batas sendi, siklus jalan, key (urut, ganti, maks 12), susunan awal, penyelarasan pemeran, FOV (35 mm 16:9 = 37,85°).
- Uji Seedance dengan previs three.js asli: **belum dijalankan** (lihat bawah).

## Uji frontend: diuji manual oleh user
Restart backend dulu (`make dev`): ada migrasi v11 dan endpoint baru.
1. Storyboard → pilih adegan yang punya pemeran → section "Previs 3D" → "Susun adegan 3D": editor terbuka, manekin berwarna dengan nama berjejer, kamera di depan.
2. Kamera bebas: putar/zoom dengan mouse. "Lihat dari kamera": tampilan sesuai rasio film. Garis kerucut kamera hanya tampil di kamera bebas.
3. Pilih pemeran → ubah pose (Duduk, Berlari, Berbaring…), posisi, arah hadap. Pilih sendi → geser slider: lutut tidak bisa menekuk terbalik. Pose Berjalan/Berlari memberi ayunan kaki saat diputar.
4. Geser timeline ke detik lain lalu ubah posisi: chip key baru muncul; putar ulang, pemeran bergerak antar key. Hapus key lewat × pada chip. Batas 12 key per jalur memunculkan pesan.
5. Tambah Kotak/Silinder/Dinding, ubah ukuran, putaran, dan warna; hapus.
6. "Susun dari naskah adegan": dialog biaya (± $0.003), hasil menjadi draf; "Kembalikan sebelum draf AI" memulihkan susunan lama. Periksa apakah penempatan dan gerak kamera masuk akal.
7. Simpan, tutup, buka lagi: susunan sama. Ubah pemeran adegan lalu buka lagi: aktor yang dilepas hilang, yang baru muncul.
8. "Simpan & render previs": merekam real-time selama durasi (jangan pindah tab; pindah tab membatalkan dengan pesan). Setelah selesai, section Previs menampilkan render diam dan video.
9. Tiru Gerakan: previs bisa dipilih sebagai referensi (≤ 10 dtk; lebih panjang perlu dipotong). Unggahan ke model butuh tunnel/S3.
10. Uji Seedance (berbayar, **Mini 480p 4 dtk ≈ $0.177**): setelah langkah 8 dengan durasi 4 dtk, pakai mode "Animasikan gambar (kartun)" + gambar karakter. Nilai apakah gerak dan komposisi mengikuti previs dan apakah tampilan manekin tidak bocor. Beri tahu saya hasilnya.

## Riwayat
- 2026-10-26: implementasi awal.
- 2026-10-26: **koreksi.** Alur uji 9 ("previs bisa dipilih sebagai referensi di Tiru Gerakan") dan toast setelah render previs keliru. Halaman Tiru Gerakan (`pages/Motion.tsx`) hanya membuat referensi dari klip library atau unggahan; daftar referensi yang sudah ada (termasuk previs) tidak ditampilkan. Sementara: unduh video previs lalu unggah di Tiru Gerakan (butuh tunnel/S3). Penyambungan previs → video adegan diusulkan masuk fase C plan 15.
