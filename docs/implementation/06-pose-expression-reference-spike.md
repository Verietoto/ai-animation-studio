# 06 - Referensi Pose & Ekspresi: Spike (hasil nyata)

Plan: `docs/plan/06-pose-expression-reference-plan.md`
Grill: `docs/grill/06-pose-expression-reference-grill.md`
Skrip: `scripts/spike_pose.py` (batas keras `SPIKE_CAP_USD`, default $0,50)
Tanggal: 2026-10-20

Status: spike selesai. **Penilaian di bawah adalah pengamatan agent atas lembar perbandingan yang diperkecil; penilaian akhir (terutama detail wajah) ada di user**, sesuai keputusan grill nomor 9. Belum ada kode fitur; plan/grill belum disetujui untuk implementasi.

## Yang dijalankan
- **Biaya total: $0,3314** dari batas $0,50 (19 panggilan berbayar tercatat; satu panggilan FLUX sketsa ulangan #2 kena `read timeout` sebelum respons, sehingga mungkin tertagih ≤ $0,009 yang tidak tercatat).
- Gambar uji diambil gratis dari `docs/spike/03-*.png`: **sumber** = perempuan bob hitam, jaket kulit merah, kaus putih, jeans, berdiri di depan dinding putih; **sheet karakter** = 2 tampilan (depan, tiga perempat); **orang lain** = pria hoodie abu-abu. Satu-satunya gambar yang dibuat: **referensi pose** (pria duduk di bangku, satu tangan di pinggang, satu tangan terangkat, tertawa) lewat 1 panggilan edit Seedream flash ($0,018).
- Model dipilih dari katalog nyata (`/images/models`, harga eksak, menerima input gambar, murah): Seedream 5.0 flash, FLUX 3 klein, Qwen image 2.1 turbo; ditambah `openai/gpt-image-2` (model bawaan aplikasi) dengan `quality=low` agar murah.
- Kasus: **raw** (pose dari gambar asli), **sketch** (pose dari sketsa garis hasil PIL `FIND_EDGES` atas gambar yang sama), **text** (pose + ekspresi hanya teks), **lock** (2 gambar sheet + pose asli = 4 gambar input). Prompt berperan seperti di plan (kalimat gambar 1: pose boleh berubah).
- Bukti: `docs/spike/06-pose-seedream-5-flash.jpg`, `06-pose-flux-3-klein.jpg`, `06-pose-qwen-image-2-1-turbo.jpg`, `06-pose-gpt-image-2-dan-ulangan.jpg` (baris atas: sumber, referensi, sketsa pria berdiri hasil `prep` (bukan yang dikirim), sheet depan; baris bawah: hasil). Sketsa yang benar-benar dikirim dibuat dari gambar pose duduk.

## Biaya nyata per panggilan
| Model | raw | sketch | text | lock | Catatan |
|---|---|---|---|---|---|
| bytedance-seed/seedream-5-0-flash | $0,018 | $0,018 | $0,018 | $0,018 | sama dengan katalog |
| black-forest-labs/flux-3-image-klein | $0,009 (+ulangan $0,009) | $0,009 | $0,009 | $0,009 | **katalog: $0,008 "eksak"; ditagih $0,009** |
| qwen/qwen-image-2.1-turbo | $0,0184 (+ulangan) | $0,0184 (+ulangan) | $0,0184 | $0,0184 | sama dengan katalog |
| openai/gpt-image-2 (low) | $0,0253 | $0,0252 | tidak dijalankan | $0,0355 | batas atas estimator ±$0,17; nyata 5-7× lebih murah |

Jumlah gambar input (1 sampai 4) tidak mengubah biaya model per-gambar; pada gpt-image-2 (token) 4 gambar ≈ +40%.

## Pengamatan (kasar, dari lembar yang diperkecil)
1. **Identitas terjaga di semua 19 hasil**: bob hitam, jaket merah, kaus putih, jeans, ruangan sama. **Tidak terlihat** hoodie abu-abu, rambut, atau wajah pria dari gambar pose. Detail wajah (apakah wajah perempuannya tetap orang yang sama) belum bisa dipastikan di resolusi ini: **perlu dinilai user**.
2. **Pose diikuti** (duduk di bangku, tangan di pinggang, satu tangan terangkat):
   - Seedream flash dan gpt-image-2: semua kasus (raw, sketch, lock).
   - FLUX klein: sketch ✓, lock ✓; raw 1 dari 2 (percobaan pertama tetap berdiri dengan gestur tangan, ulangan duduk) → variasi acak.
   - Qwen turbo: sketch 2 dari 2 ✓, lock ✓; **raw 0 dari 2** (tetap berdiri, hanya tangan berubah).
   - Kesimpulan: sketsa garis **tidak dibutuhkan** model kuat, tetapi **menaikkan keandalan** model murah.
3. **Ekspresi**: pada raw, FLUX dan Qwen ikut menyalin **tawa lebar** pria padahal prompt menyebut pose saja (gpt-image-2 tidak menyalin, wajahnya netral/tersenyum tipis). Pada sketch, ekspresi tidak bocor. Kasus **text** ("big open smile") dipenuhi semua model (senyum lebar, tangan di pinggang, tetap berdiri).
4. **Urutan input terjaga** pada kasus lock (4 gambar: sumber, 2 sheet, pose): hasil mengikuti pose dari gambar ke-4 dan identitas dari gambar 1-3 di keempat model. Belum diuji di 5 gambar atau lebih.
5. Pose duduk di bangku juga memunculkan **bangku sebagai properti** dan memotong latar (dinding lebih sempit); ini wajar, tapi pose yang membutuhkan properti membawa propertinya.
6. Peran gambar 1 dengan "pose boleh berubah" bekerja: tidak ada hasil yang menyalin pose berdiri sumber pada Seedream/gpt-image-2.

## Dampak pada plan 06 (usulan, menunggu persetujuan)
- **Sketsa garis menjadi default untuk slot pose** (gambar asli sebagai opsi "pakai gambar asli"), karena: mengurangi kebocoran ekspresi, menaikkan keandalan model murah, murah dibuat (PIL tanpa dependency). Sketsa dibuat on-the-fly saat edit (keputusan grill).
- **Ekspresi lewat preset teks sebagai jalur utama**; gambar ekspresi tetap opsional dengan peringatan (model murah menyalin ekspresi dari gambar pose mentah, jadi jangan mengandalkan gambar pose untuk ekspresi).
- Model yang ditonjolkan di katalog untuk fitur ini: Seedream 5.0 flash (terbaik per harga, $0,018), gpt-image-2 low (identitas/ekspresi terkontrol, $0,025-0,036); FLUX klein dan Qwen turbo bisa dipakai dengan sketsa.
- Batas atas estimator untuk model token (gpt-image-2) 5-7× di atas biaya nyata: dialog konfirmasi akan menampilkan angka konservatif. Bila `quality=low` dipilih, estimator bisa memakai batas token yang lebih kecil (perbaikan terpisah, di luar plan ini) atau riwayat setelah beberapa panggilan.
- **Temuan estimator**: FLUX klein ditagih $0,009 vs katalog/estimasi "eksak" $0,008 (≈ 12% kurang). Perlu dicek apakah ada biaya tambahan (mis. per gambar input atau pembulatan); sementara estimasi "eksak" untuk model ini bisa meleset sedikit.
- Aspek rasio otomatis (grill nomor 7): **tidak diperlukan**; semua hasil mengikuti rasio gambar sumber pada pengamatan kasar.
- Pertanyaan terbuka plan (ekstraksi kerangka pose dengan ML): **tidak perlu untuk sekarang**; sketsa garis cukup untuk 4 dari 4 model.

## Penyimpangan dari rencana spike
- Rencana: 2 run per kasus untuk 2 model teratas. Dilakukan: 1 run per kasus untuk 4 model, ulangan hanya untuk raw FLUX, raw dan sketch Qwen (kasus yang menentukan keputusan sketsa); tidak ada ulangan untuk Seedream/gpt-image-2.
- Model: bukan "Gemini image" (token, batas atas melampaui anggaran); dipilih dari katalog nyata berdasarkan harga eksak + gpt-image-2 low.
- Kasus ekspresi dari **gambar** tidak diuji terpisah (tidak ada gambar ekspresi tanpa pose); hanya teks dan efek samping dari gambar pose.
- Tidak diuji: lebih dari satu orang di scene, pose yang membutuhkan gambar close-up wajah, resolusi tinggi.

## Yang perlu dinilai user
Buka empat file `docs/spike/06-*.jpg` dan putuskan: (1) apakah wajah perempuan pada hasil masih orang yang sama dengan sumber; (2) apakah sketsa garis cukup sebagai default pose; (3) apakah hasil Seedream flash cukup bagus sebagai model rekomendasi.

## Riwayat
- 2026-10-20: spike dijalankan, total $0,3314.
