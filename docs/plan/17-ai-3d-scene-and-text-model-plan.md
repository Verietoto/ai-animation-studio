# 17 - Scene 3D yang lebih kaya dibuat AI + pilihan model LLM (Plan)

- Status: draft, menunggu persetujuan
- Tanggal: 2026-10-26

## Tujuan
Dua permintaan user:
1. "harusnya di buat dengan model ai biar ai yang buatkan three js nya".
2. "aku juga mau bisa milih model llmnya".

Sekarang AI hanya mengisi data posisi/pose/kamera (plan 14); dunianya (manekin abu-abu, kotak, silinder, dinding) dibuat kode dari bahan yang terbatas, jadi hasil previs kasar dan seragam. Tujuannya: AI merancang **scene 3D yang jauh lebih kaya** (set, benda, pencahayaan, langit, bentuk dan penampilan tokoh sesuai deskripsi), tetap sebagai data yang aman dan bisa disunting di editor. Dan model LLM untuk semua fitur AI teks bisa dipilih user, bukan terkunci di `.env`.

## Keadaan sekarang (dicek 2026-10-26)
- Satu model teks global: `Settings.blockout_model` (`BLOCKOUT_MODEL`, bawaan Claude Haiku 5.5), dipakai `textai.estimate/ask` untuk empat jalur: susunan blockout, naskah, pecah naskah (dan jalur baru nanti). Estimasi kind `scene_blockout`, `episode_script`, `episode_split` mengirim `model: "teks"` sebagai placeholder; model nyata tidak datang dari klien.
- Scene three.js (`storyboard/blockoutScene.ts`): manekin 16 sendi dari primitif seragam; properti hanya `box | cylinder | plane` (maks 50); warna properti hex; pencahayaan, langit, dan lantai tetap; tidak ada pengaruh waktu/suasana adegan atau deskripsi tokoh.
- Validasi susunan: `blockout.py` (`clean`), batas 64 KB, 12 key per jalur, 3 aktor, 50 properti.
- Katalog nyata (`GET /models`, dicek hari ini): 467 model, **303 model teks mendukung `response_format`**; harga per juta token berkisar $0.02 sampai $150 (masukan) dan $0.09 sampai $600 (keluaran). Ada entri yang tidak layak dipilih: router otomatis dengan harga negatif (placeholder -1), konteks sangat kecil (6–8 ribu token), dan model super mahal (satu pemecahan naskah dengan `o1-pro` ≈ $7, di atas batas $1 per job).

## Ruang lingkup
### A. Scene 3D lebih kaya, dirancang AI (data, bukan kode)
- **Kosakata baru** (divalidasi server, dirender client):
  - bentuk: `box, cylinder, sphere, cone, capsule, torus, plane`;
  - objek siap pakai (prefab): `table, chair, bench, bed, shelf, counter, door, window, lamp, tree, bush, rock, fence, house, road, car, motorbike` dan sejenisnya, dibangun dari primitif oleh kode (konsisten dan murah);
  - material per objek: warna, kekasaran, emisi (lampu menyala);
  - pencahayaan: warna dan intensitas cahaya sekitar, arah dan warna matahari, lampu titik; langit dan warna tanah menurut waktu (pagi, siang, senja, malam), kabut opsional.
- **Tokoh sesuai deskripsi:** AI mengisi `look` per aktor dari deskripsi karakter: tinggi relatif, lebar badan, warna kulit, rambut (gaya sederhana: pendek, panjang, kepang, sanggul, botak), warna atasan dan bawahan, aksesori sederhana (kacamata, topi). Manekin dibangun dari parameter itu.
- Batas dinaikkan wajar (mis. 120 objek, 128 KB), tetap divalidasi.
- Editor: daftar objek memuat jenis baru, material dan `look` bisa disunting; prefab dan bentuk baru bisa ditambah manual.
- Prompt AI diperluas dengan kosakata dan aturan tata letak (skala meter, lantai y=0, objek tidak saling tembus berlebihan).

### B. Pilihan model LLM untuk semua fitur AI teks
- **Daftar yang disaring** `GET /api/models/text`: hanya keluaran teks, mendukung `response_format`, harga ≥ 0 (membuang router berharga negatif), konteks ≥ 32 ribu token, tanpa varian `:free`/`:batch`. Setiap entri menampilkan nama, harga per juta token (masuk/keluar), konteks, dan penanda "direkomendasikan" untuk beberapa model terukur.
- **Pilihan per permintaan:** `model` ikut di semua endpoint AI teks (susunan 3D, naskah, pecah naskah, estimasi). Server memvalidasi ulang terhadap daftar yang sama (tidak percaya klien) dan memakainya untuk estimasi dan pencatatan `text_jobs.model`.
- **Bawaan:** `BLOCKOUT_MODEL` di `.env` tetap menjadi bawaan server (diganti nama alias `TEXT_MODEL`, nama lama tetap berlaku). Pilihan terakhir user diingat di browser (`localStorage`, boleh gagal) dan dipakai sebagai nilai awal di semua pemilih.
- **Komponen `TextModelPicker`** (dengan pencarian) dipakai di empat tempat: editor 3D, naskah, pecah naskah, dan aksi massal previs. Estimasi biaya yang ada (`EstimateLine`) otomatis mengikuti model terpilih.

Tidak termasuk:
- AI menulis **kode** three.js yang dijalankan di browser (jalur "A" di diskusi): tidak aman tanpa sandbox terpisah, hasil tidak bisa disunting. Bisa jadi tambahan terpisah untuk "bentuk kustom" bila kosakata tidak cukup.
- Impor model 3D (GLB) dan tekstur gambar; animasi tokoh per sendi yang ditulis AI per langkah (siklus jalan tetap prosedural).
- Memilih model untuk fitur gambar/video (sudah punya pemilih sendiri).

## Desain / pendekatan
- `textai.estimate/ask` menerima `model` eksplisit; `Studio.text_model(model_id)` memvalidasi dan mengembalikan harga (satu sumber, memakai `list_models()` yang sudah ada dengan cache 5 menit). Semua pemanggil di `scenes.py` dan `journey.py` meneruskan `model`.
- Jawaban model diurai lebih toleran: buang pagar kode, ambil objek JSON pertama yang seimbang; jawaban kosong (model berpikir yang menghabiskan token) dan JSON rusak memberi pesan yang menyarankan ganti model. Biaya tetap tercatat sebelum parsing (pola plan 14).
- `blockout.py`: skema versi 2 dengan kosakata baru, `look`, `environment`; susunan versi 1 lama tetap terbaca (diisi bawaan). `clean()` memvalidasi semuanya dan membuang elemen tak dikenal dengan peringatan (bukan menolak seluruh susunan).
- `blockoutScene.ts`: pembangun prefab, material, lampu, langit; `buildMannequin(look)`.
- Frontend: `TextModelPicker` + `useTextModel()` (nilai awal dari `localStorage`/`health`), perubahan editor dan tiga step.

## Risiko awal (bahan grill)
- **Kualitas rancangan AI bergantung model.** Model murah bisa membuat scene aneh (objek melayang, skala salah). Perlu spike membandingkan 3 model pada satu adegan nyata.
- **Model yang tidak patuh `response_format`:** JSON rusak/teks tambahan; mitigasi parser toleran + pesan jelas.
- **Model berpikir:** token keluaran habis untuk penalaran, jawaban kosong; estimasi harus memakai batas token yang sama.
- **Biaya:** model mahal; batas per job ($1) dan harian melindungi, tetapi estimasi harus jujur (memakai `max_tokens` penuh). Harga negatif/tidak ada harus ditolak.
- **Ukuran dan kinerja render:** 120 objek dengan prefab bisa berat; batasi jumlah segmen geometri dan uji di editor.
- **Kompatibilitas data:** susunan versi 1 tersimpan harus tetap terbuka; editor harus mengisi bawaan untuk field baru.
- **Dua perubahan besar sekaligus:** dipecah fase supaya tiap fase bisa diuji.

## Langkah kerja
1. Grill plan ini.
2. **Fase 1, pilihan model LLM:** backend (`/api/models/text`, validasi, `model` di semua jalur AI teks, parser toleran, test) lalu `TextModelPicker` di empat tempat. Berguna sendiri dan murah diuji.
3. **Fase 2, scene kaya:** `blockout.py` v2, prompt AI baru, pembangun prefab/material/lampu/tokoh di `blockoutScene.ts`, editor.
4. Spike berbayar (usul ≤ $0.10): satu adegan nyata dengan 3 model berbeda (murah, menengah, kuat); nilai tata letak, skala, dan kepatuhan JSON. Hasil menentukan model yang diberi tanda "direkomendasikan".
5. Dokumen implementation 17 (satu berkas, bagian per fase) dan daftar uji manual untuk user.

## Kriteria selesai
- `make test` hijau dengan test baru; `npm run build` hijau.
- Model teks bisa dipilih di keempat tempat; pilihan tidak valid (tak dikenal, harga negatif, konteks kecil) ditolak server sebelum biaya; biaya dan `text_jobs.model` mengikuti pilihan.
- AI membuat scene dengan objek, pencahayaan, langit, dan tokoh sesuai deskripsi; susunan lama versi 1 tetap terbuka; hasil tetap bisa disunting di editor.
- Spike membuktikan scene kaya dapat dihasilkan oleh sedikitnya satu model murah dengan JSON valid.

## Pertanyaan terbuka
1. Setuju jalur **B (data kaya, aman)** dulu, dengan jalur kode AI sebagai tambahan terpisah nanti?
2. Tokoh mengikuti deskripsi karakter (tinggi, rambut, pakaian, aksesori), setuju? Atau cukup warna dan ukuran saja?
3. Pilihan model **per permintaan dengan nilai awal yang diingat browser** (usul), atau satu pengaturan global di satu tempat?
4. Boleh model berbiaya tinggi tampil di daftar (batas $1 per job tetap melindungi, dengan peringatan), atau sembunyikan yang lebih mahal dari ambang tertentu (mis. keluaran > $20 per juta token)?
5. Spike berbayar ≤ $0.10 untuk membandingkan 3 model?

## Riwayat
- 2026-10-26: draft awal.
- 2026-10-26: **Revisi 1, tinjauan atas permintaan user** ("review plan biar jadi jauh lebih baik"). Bagian di atas yang bertentangan dengan revisi ini **digantikan** oleh rincian di bawah.

### Revisi 1: masalah pada draft
1. **Satu panggilan AI untuk seluruh dunia per adegan itu boros dan tidak konsisten.** Latar dipakai ulang di banyak adegan, tokoh muncul di banyak adegan; draft meminta AI merancang ulang warung dan penampilan Rani di setiap adegan. Hasilnya: warung berubah-ubah antar adegan, biaya berlipat, keluaran besar dan mudah rusak.
2. **LLM lemah di koordinat 3D.** Meminta angka x/y/z mentah untuk 120 objek hampir pasti menghasilkan benda melayang, saling tembus, dan tokoh di luar bingkai, terutama di model murah. Draft hanya berharap pada prompt.
3. **Mode JSON yang dipakai paling lemah.** Kode sekarang mengirim `response_format: json_object`. Katalog (dicek hari ini): dari 290 model yang lolos saringan, **268 mendukung `structured_outputs`** (skema JSON ketat). Draft tidak memakainya.
4. **Model penalaran tidak dikendalikan.** **220 model** mendukung parameter `reasoning`; tanpa batas, token keluaran bisa habis untuk berpikir (jawaban kosong) dan biaya tidak terduga.
5. **Gambar yang sudah ada diabaikan.** Latar punya gambar (plan 08/16) dan tokoh punya potret/lembar tampilan; **179 model** bisa membaca gambar dan keluaran terstruktur (Haiku 5.5 termasuk). Merancang set dari gambar latar membuat previs cocok dengan keyframe nantinya.
6. **"Direkomendasikan" ditebak.** Draft menandai model tanpa pengukuran.
7. **Kopling yang terlewat:** `Scenes.previs_video_plan` (plan 15) memetakan tokoh ke **warna manekin tetap** (biru, oranye, hijau, ungu). Bila manekin memakai warna pakaian dari deskripsi, prompt video dari previs harus ikut berubah, kalau tidak Seedance diberi petunjuk yang salah.
8. **Dua tabel ukuran prefab** (Python untuk validasi, TS untuk render) akan menyimpang, masalah yang sama dengan tabel sendi di plan 14.
9. **Kualitas render diabaikan.** Tanpa bayangan dan tone mapping, set sekaya apa pun tetap tampak datar; ini murah dan berdampak besar, tidak butuh AI.
10. **Kriteria selesai tidak terukur.** "AI membuat scene kaya" tidak bisa diuji.

### Revisi 1: desain baru
**a. Tiga lapis, dibuat sekali dan dipakai ulang**
| Lapis | Disimpan di | Dibuat | Dipakai ulang |
|---|---|---|---|
| **Set latar** (bangunan, perabot, langit, cahaya bawaan) | `locations.set_layout` (baru) | sekali per latar, AI atau manual | semua adegan di latar itu |
| **Penampilan tokoh** (`look`: tinggi, badan, kulit, rambut, pakaian, aksesori) | `characters.look` (baru) | sekali per karakter, dari deskripsi (dan potret bila model bisa membaca gambar) | semua adegan |
| **Pementasan adegan** (aktor, gerak, kamera, properti tambahan, waktu/cuaca) | `scenes.blockout` v2 | per adegan | - |

Keluaran AI per panggilan jadi kecil, warung yang sama di setiap adegan, dan biaya per adegan turun. Mengubah set latar memperbarui semua adegan di latar itu.

**b. AI menulis relasi, server yang menghitung koordinat**
- Objek boleh ditaruh dengan relasi sederhana: `on` (di atas objek lain), `against` (menempel dinding utara/selatan/timur/barat), `near` (dekat objek), `at` (koordinat lantai x/z). AI tidak perlu menulis y.
- **Pemecah tata letak deterministik di backend** (`layout_solver.py`, murni Python, teruji `pytest`): menempatkan objek di lantai atau di atas permukaan sesuai kotak batasnya, mendorong objek yang saling tembus, menjaga semua di dalam batas set, menjaga kamera di luar objek, dan memastikan setiap aktor terlihat di bingkai kamera pada t=0 (mundurkan kamera / lebarkan lensa bila perlu, dengan peringatan).
- Pemecah dijalankan di `clean()` untuk hasil AI maupun simpanan manual; frontend hanya merender.

**c. Satu sumber kosakata**
- `GET /api/blockout/vocabulary` dari backend: daftar bentuk, prefab (dengan ukuran kotak batas dan permukaan atas untuk `on`), gaya rambut, aksesori, preset waktu. Validasi, prompt AI, dan editor semuanya membaca daftar ini; geometri prefab dibangun frontend dari ukuran yang sama. Tidak ada tabel ganda.

**d. Pilihan model LLM yang lebih cerdas**
- Saringan katalog (dicek: 290 lolos): keluaran teks, `response_format`, harga ≥ 0, konteks ≥ 32 ribu, tanpa `:free`/`:batch`. Model dengan harga keluaran > $20 per juta token (21 model) tampil di bagian "mahal" dengan peringatan.
- **Kemampuan per model dipakai otomatis:** `structured_outputs` → kirim skema JSON ketat (`json_schema`, strict); bila tidak → `json_object` + pengurai toleran. `reasoning` didukung → kirim upaya rendah dan batas token penalaran agar biaya dan jawaban terduga; estimasi memakai batas yang sama. Bisa membaca gambar → opsi "pakai gambar latar/potret" aktif.
- **Bawaan per tugas**, bukan satu untuk semua: naskah (kualitas tulisan), pecah naskah (konteks panjang), set/penampilan/pementasan (kepatuhan skema). Disimpan di browser per tugas, bawaan server dari `.env`.
- **Rekomendasi dari pengukuran:** `scripts/eval_text_models.py` menjalankan set uji tetap (2 set latar, 2 pementasan, 1 pecah naskah pendek) pada model kandidat dan mencatat: JSON valid tanpa perbaikan, jumlah peringatan pemecah, biaya, waktu. Tanda "direkomendasikan" dan bawaan per tugas diambil dari hasil ini dan dicatat di dokumen implementation.
- Tidak ada percobaan ulang berbayar otomatis. JSON rusak → perbaikan lokal gratis (buang pagar, ambil objek seimbang) → validasi; bila gagal, pesan menyarankan model lain.

**e. Kualitas render (tanpa AI)**
- Bayangan dari matahari (dibatasi jumlah benda yang melempar bayangan), tone mapping ACES, langit gradien dan kabut sesuai waktu, wajah manekin minimal (mata) supaya arah hadap terbaca, `InstancedMesh` untuk prefab berulang (pohon, pagar). Anggaran kinerja: target 30 fps pada 1280×720 dengan 120 objek.

**f. Penyesuaian previs → video (plan 15)**
- Prompt "video dari previs" menyebut tokoh dengan penampilannya ("the girl in the red kebaya") dari `look`, bukan warna indeks; warna manekin di editor = warna pakaian dari `look`.

**g. Opsi berbasis gambar (dipisah, opsional)**
- "Susun set dari gambar latar" dan "Penampilan dari potret": hanya untuk model yang bisa membaca gambar; gambar dikirim sebagai data URL (sudah dipakai untuk model gambar). Biaya masukan naik, ditampilkan di estimasi.

### Revisi 1: data dan migrasi
- Migrasi v13: `locations.set_layout TEXT`, `characters.look TEXT`.
- `scenes.blockout` versi 2 menunjuk set latar (tidak menyalinnya); versi 1 tetap terbaca dan diubah ke v2 saat dimuat (properti v1 menjadi properti adegan).
- Estimasi kind baru: `location_set`, `character_look`; kind lama menerima `model` nyata.

### Revisi 1: fase baru (masing-masing bisa dikirim sendiri)
1. **Fase 1, model LLM:** saringan + `/api/models/text`, `model` di semua jalur AI teks, skema ketat / `json_object`, kontrol `reasoning`, pengurai toleran, `TextModelPicker` dengan bawaan per tugas, `eval_text_models.py`. Spike = menjalankan eval (usul ≤ $0.30).
2. **Fase 2, kosakata + pemecah + render:** `GET /api/blockout/vocabulary`, `layout_solver.py`, skema v2, prefab dan material di `blockoutScene.ts`, bayangan/tone mapping/langit. Belum ada AI baru; susunan manual dan susunan AI lama langsung tampak lebih baik.
3. **Fase 3, AI tiga lapis:** set latar per latar, `look` per karakter, pementasan adegan yang merujuk set; editor untuk set dan `look`; penyesuaian prompt video dari previs.
4. **Fase 4 (opsional), berbasis gambar:** set dari gambar latar, `look` dari potret.

### Revisi 1: kriteria selesai yang terukur
- `make test` hijau, termasuk test pemecah: 0 pasangan objek bertabrakan lebih dari 2 cm, semua objek di dalam batas set, semua aktor di dalam bingkai kamera pada t=0, objek `on` duduk tepat di permukaan; susunan v1 terbaca.
- Eval: sedikitnya satu model dengan harga keluaran ≤ $1 per juta token menghasilkan JSON valid tanpa perbaikan untuk ≥ 4 dari 5 kasus uji; hasil eval dicatat.
- Pilihan model tidak valid ditolak sebelum biaya; `text_jobs.model` mengikuti pilihan.
- Set latar yang sama tampil identik di semua adegannya; mengubahnya mengubah semua adegan.
- Diuji user: render lancar (target 30 fps) dan scene terbaca jelas pada 3 adegan nyata.

### Revisi 2 (2026-10-26): jenis tubuh dan konteks latar
Pemicu, pertanyaan user: "apakah nanti ai nya sudah bisa mendapatkan kontext tentang karakter (misalnya momon adalah kucing jadi dia bikinnya bukan bentuk manusia), terus latarnya isi apa aja".

Temuan:
- AI penyusun sekarang (plan 14, `Scenes._blockout_context`) hanya menerima **nama dan aksi** pemeran, **tanpa deskripsi karakter**. AI tidak tahu Momon kucing.
- Manekin hanya satu bentuk (manusia, 16 sendi); `look` di Revisi 1 juga kosakata manusia (rambut, atasan, bawahan). Kucing tetap jadi manusia.
- Latar: set per latar memakai nama + deskripsi latar (Revisi 1), tetapi benda yang tidak ada di kosakata belum punya perilaku yang jelas.

Perubahan:
- **Jenis tubuh (`body`) di `look`:** `humanoid`, `quadruped` (kucing, anjing, kuda, sapi), `bird`, `serpent` (ular, ikan, cacing), `blob` (robot kecil, makhluk sederhana, benda hidup). Dipilih AI dari deskripsi karakter; bisa diganti user di editor.
  - Tiap jenis punya kerangka sendi, batas sendi, pustaka pose, dan siklus gerak sendiri (berkaki empat: langkah diagonal; burung: kepak; ular: gelombang), semua dari satu sumber kosakata di backend.
  - Ukuran nyata dari deskripsi (kucing ±0,3 m tinggi bahu), parameter tubuh per jenis: panjang badan, ekor, telinga runcing/bulat, belang/warna bulu.
  - Validasi `clean()`: sendi dan pose harus milik jenis tubuh aktor itu.
- **Konteks karakter selalu dikirim:** deskripsi baku karakter ikut ke AI di lapis penampilan **dan** pementasan (dipotong wajar), supaya aksi "Momon melompat ke meja" dipentaskan sebagai kucing.
- **Benda di luar kosakata:** AI boleh menulis benda bebas (mis. "gerobak bakso") dengan bentuk pendekatan: kumpulan bentuk dasar + label nama yang terlihat di editor; tidak ditolak, tidak diam-diam hilang.
- **Isi latar dari deskripsi:** prompt set meminta AI menurunkan isi latar dari deskripsi (dan, di fase 4, dari gambarnya); bila deskripsi miskin, AI mengisi isi yang wajar dan menandainya sebagai "tebakan" agar user tahu mana yang perlu diperiksa.
- **Video dari previs:** prompt menyebut tokoh berdasarkan jenis tubuh dan penampilan ("the orange cat Momon"), sehingga Seedance memetakan manekin kucing ke gambar Momon.
- Fase: jenis tubuh `humanoid` + `quadruped` di fase 2–3 (kucing dan anjing paling sering); `bird`, `serpent`, `blob` menyusul di fase yang sama bila waktu cukup, atau dipisah.
- Kriteria selesai tambahan: kasus uji eval memuat satu karakter hewan; pemecah dan validasi menguji sendi/pose per jenis tubuh.

### Setelah grill (2026-10-26)
User: "oke grill". Bawaan pertanyaan dianggap disetujui. Keputusan dari grill 17:
- Jenis tubuh di plan ini hanya `humanoid` + `quadruped`; `bird`/`serpent`/`blob` dan fase 4 (berbasis gambar) dipindah ke plan terpisah.
- Kosakata tunggal di `shared/blockout_vocabulary.json` (bukan endpoint), dibaca Python dan diimpor TS.
- Pemecah tata letak jalan saat simpan dan di `GET /api/scenes/{id}/blockout/resolved`, tidak di daftar adegan; objek set ber-id stabil.
- Daftar model di-cache 5 menit; skema ketat + `require_parameters` bila didukung, ulang sekali dengan `json_object` bila skema ditolak; `reasoning: {"effort": "low"}` hanya untuk model ber-`reasoning`; isi kosong karena kehabisan token diberi pesan khusus.
- Migrasi v13 `locations.set_layout`, `characters.look`, `characters.look_hash`; salin workspace ikut menyalin `look`.

### Revisi 1: pertanyaan untuk user (menggantikan daftar lama)
1. Setuju desain tiga lapis (set per latar, penampilan per karakter, pementasan per adegan)?
2. Bawaan model **per tugas** dan disimpan di browser: setuju?
3. Anggaran eval model ≤ $0.30 (lebih besar dari usul $0.10 sebelumnya karena 5 kasus × beberapa model)?
4. Fase 4 (berbasis gambar) dikerjakan sekarang, atau setelah fase 1–3 dicoba?
