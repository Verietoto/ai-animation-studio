# 08 - Storyboard per episode dan adegan: Spike keyframe (hasil nyata)

Plan: `docs/plan/08-episode-scene-storyboard-plan.md` (Revisi 1). Grill: `docs/grill/08-episode-scene-storyboard-grill.md` (no. 17, 19, 21).
Skrip: `scripts/spike_scene.py` (batas keras `SPIKE_CAP_USD`, default $0,50; dicek sebelum tiap panggilan).
Tanggal: 2026-10-20. Budget dari user: **$0,50** ("0.5 dolar").

Status: spike selesai. **Penilaian di bawah adalah pengamatan agent atas lembar perbandingan yang diperkecil; penilaian akhir (terutama wajah) ada di user.**

## Yang dijalankan
- **Biaya total $0,2413** dari $0,50 (15 panggilan berbayar, semua tercatat, tidak ada yang gagal atau menggantung).
- Gambar uji gratis dari `docs/spike/03-anchor-frame.png`: **karakter A** = perempuan bob hitam, jaket kulit merah, kaus putih, jeans (di depan dinding putih); **karakter B** = pria hoodie abu-abu, celana hitam (di depan dinding putih). Latar dibuat sendiri lewat teks (kasus a).
- Model (harga eksak katalog): FLUX 3 klein ($0,008 katalog), Seedream 5.0 flash ($0,018), Qwen image 2.1 turbo ($0,0184), ditambah gpt-image-2 `quality=low` (model bawaan aplikasi).
- Kasus: **(a)** latar dari teks tanpa gambar input; **(b)** latar + 1 karakter; **(c1)** latar + 2 karakter sekaligus; **(c2)** bertahap: hasil (b) + karakter B + karakter A sebagai pengunci identitas. Prompt berperan: "Image 1 is the LOCATION…; Image 2 shows the CHARACTER…, ignore the background of image 2; keep face, hair, skin tone, body shape, clothing and colors".
- Bukti: `docs/spike/08-latar-dari-teks.jpg` (3 model), `08-keyframe-3-model.jpg` (baris 1: latar FLUX, karakter A, karakter B; baris 2-4: FLUX, Seedream, Qwen dengan kolom (b), (c1), (c2)), `08-keyframe-rasio-dan-gpt-image-2.jpg` (Seedream 16:9 sekaligus; gpt-image-2 low satu dan dua karakter).

## Biaya nyata
| Model | latar teks | 1 karakter | 2 sekaligus | 2 bertahap (langkah 2) |
|---|---|---|---|---|
| flux-3-image-klein | $0,009 | $0,009 | $0,009 | $0,009 |
| seedream-5-0-flash | $0,018 | $0,018 | $0,018 | $0,018 |
| qwen-image-2.1-turbo | $0,0184 | $0,0184 | $0,0184 | $0,0184 |
| gpt-image-2 (low, 16:9) | tidak dijalankan | $0,0180 | $0,0238 | tidak dijalankan |

Biaya per panggilan tidak naik dengan jumlah gambar input pada tiga model pertama. Batas atas estimator gpt-image-2 sebelum panggilan: $0,167 (1 karakter) dan $0,183 (2 karakter) vs nyata $0,018 dan $0,024, jadi **7-8× di atas biaya nyata** (temuan yang sama dengan spike 06). FLUX klein ditagih $0,009 vs katalog "eksak" $0,008 (temuan lama terulang).

## Pengamatan
1. **(a) Latar dari teks berhasil di ketiga model** tanpa `input_references`. Hasil bagus (sawah, kabut, gubuk, cahaya senja). Estimator menerima 0 input dengan kepercayaan "exact". Jawaban atas grill 17: aman, `generate_image` tanpa gambar bisa dibuat.
2. **Latar dipertahankan di semua 12 komposit utama** (gubuk, pematang, langit sama dengan gambar 1).
3. **Identitas dan baju terjaga di semua hasil**: bob hitam, jaket merah, kaus putih, jeans untuk A; hoodie abu-abu, celana hitam untuk B. **Tidak ada karakter tertukar, tidak ada baju bertukar, dan background putih foto karakter tidak pernah muncul** (jawaban atas grill 19). Detail wajah (apakah orangnya sama) tidak bisa dipastikan di resolusi ini: **perlu dinilai user**.
4. **Aksi dan kamera**: perempuan berjalan ke arah kamera di semua model. Pria "tertawa mengikuti di belakang": jelas di Seedream dan gpt-image-2, samar di Qwen, tidak terlihat di FLUX klein (wajahnya kecil dan jauh).
5. **Ukuran tokoh**: FLUX menaruh tokoh kecil dan jauh (detail wajah minim). Seedream, Qwen, dan gpt-image-2 membuat tokoh lebih besar dan jelas.
6. **Sekaligus vs bertahap**: kualitas setara di ketiga model (identitas dan latar sama baiknya), dan bertahap **tidak memperbaiki apa pun** pada 2 karakter, hanya menggandakan biaya dan waktu. Jawaban atas grill 20, 21: **mode bertahap tidak dibuat di v1**.
7. **Rasio aspek**: Seedream **selalu 1:1 (2048×2048) bila rasio tidak dikirim**, meski gambar latar 16:9. Dengan `aspect_ratio=16:9` hasilnya 2048×1152 dan komposisinya baik. FLUX (1363×770) dan Qwen (2720×1536) mengikuti gambar pertama. gpt-image-2 dengan 16:9 menghasilkan 1536×864. Menguatkan grill 6: **rasio episode harus dikirim eksplisit** bila model mendukung.
8. gpt-image-2 low pada 1 dan 2 karakter menghasilkan komposisi bersih dan identitas terjaga, dengan biaya sebanding Seedream.

## Dampak pada plan 08 (keputusan, menunggu persetujuan user)
- **Mode bertahap dihapus dari v1** (tidak ada manfaat terukur). Satu panggilan "sekaligus" untuk 1-3 pemeran.
- **Model bawaan keyframe:** Seedream 5.0 flash ($0,018, tokoh jelas, aksi terbaca). gpt-image-2 dan Qwen turbo sebagai alternatif. FLUX klein tidak direkomendasikan untuk adegan (tokoh kecil).
- **Rasio:** kirim `films.aspect_ratio` ke model sebagai `aspect_ratio` bila didukung; bila tidak, ikuti gambar pertama (latar).
- **Latar dari teks:** model yang lolos = ketiga model di atas. Rasio latar mengikuti rasio episode.
- **Estimasi:** `scene_keyframe` memakai jumlah gambar input dari `compose` yang sama dengan generate. Batas atas gpt-image-2 yang 7-8× terlalu tinggi tetap muncul di dialog konfirmasi (sudah diketahui, di luar plan ini).

## Yang tidak diuji (risiko tersisa)
- **Tiga pemeran** (hanya 1 dan 2; butuh gambar karakter ketiga yang berbeda).
- **Tampilan/baju yang berbeda dari gambar sumber** (di sini gambar karakter = tampilan bawaan) dan tampilan hanya-teks ("change the outfit to…").
- **Wajah detail**: penilaian user.
- **Video i2v dari keyframe dua karakter**: apakah kedua tokoh bertahan selama klip belum diuji (butuh panggilan video, jauh lebih mahal).
- Latar dengan gambar yang di-upload user (bukan dari teks): diharapkan sama, tidak diuji.

## Yang perlu dinilai user
Buka tiga file `docs/spike/08-*.jpg` dan putuskan: (1) apakah wajah perempuan dan pria pada hasil masih orang yang sama dengan sumber; (2) apakah Seedream flash cukup bagus sebagai model bawaan keyframe; (3) apakah latar dari teks cukup bagus.

## Riwayat
- 2026-10-20: spike dijalankan, total $0,2413 dari $0,50.
