# 18 - Storyboard v2 (Grill)

Plan terkait: `docs/plan/18-storyboard-v2-plan.md` (draf + Revisi 1)

Jawaban user atas pertanyaan terbuka plan: "y" (2026-10-26), dibaca sebagai menerima semua usulan default: Proyek = workspace; suara dari unggahan + TTS bila tersedia; model gambar default di pengaturan proyek; batas spike $2,00; model video default `bytedance/seedance-2.0`; riwayat naskah 50 versi.

Tingkat: (B) berat = mengubah desain, (S) sedang = perlu mitigasi di kode, (R) ringan = catatan/UI.

## Lubang pada plan
1. **(B) Dua sumber rasio.** v2 memakai rasio proyek, alur lama (plan 15, keyframe, `scenes.video_aspect`) memakai `films.aspect_ratio`. Episode yang sama dibuka di dua section akan menghasilkan aset dengan rasio berbeda.
   - Mitigasi: satu sumber kebenaran. Begitu rasio proyek ditetapkan, semua `films.aspect_ratio` di workspace itu diselaraskan (dengan konfirmasi bila ada episode berbeda + daftar aset yang jadi tidak cocok), dan field rasio per episode menjadi baca-saja. Kode lama terus membaca `films.aspect_ratio`, jadi tidak perlu diubah.
2. **(B) Batas biaya per job $1 memblokir adegan 15 dtk.** Halaman OpenRouter menyebut Seedance 2.0 "from $0.06726/sec": 15 dtk ≈ $1,01 di resolusi terendah, 720p/1080p dan audio lebih mahal. Default `MAX_COST_PER_JOB_USD=1` akan menolak adegan panjang di model default.
   - Mitigasi: (a) estimasi menampilkan alasan blokir dengan saran konkret (turunkan durasi, ganti ke `-fast`/`-mini`, atau naikkan `MAX_COST_PER_JOB_USD` di `.env`); (b) pengaturan proyek menampilkan perkiraan biaya per 10 dtk untuk kombinasi model/resolusi yang dipilih, supaya keputusan default terlihat; (c) batas tidak diubah oleh agent.
3. **(B) Anggaran harian $5 vs produksi massal.** Satu episode 10 adegan × ±$0,6 sudah melewati $5; batch berhenti di tengah.
   - Mitigasi: dialog batch menampilkan total vs sisa anggaran hari ini dan jumlah adegan yang muat; user memilih "jalankan yang muat saja" atau batal. Tidak ada batch yang sengaja menabrak 409 di tengah.
4. **(S) Tidak ada batas ukuran payload.** 9 gambar sebagai data URL resolusi penuh bisa puluhan MB; batas body OpenRouter tidak diketahui.
   - Mitigasi: referensi gambar diperkecil server-side (sisi panjang ≤ 1536 px, JPEG q85) sebelum di-encode; total payload dicatat di log; spike Fase 0 mengukur apakah request 9 gambar diterima.
5. **(S) Model gambar tidak mendukung rasio proyek** (mis. 21:9 / 9:21). Gambar beat akan keluar dengan rasio lain dan menjadi referensi yang menyesatkan.
   - Mitigasi: daftar model gambar di pengaturan proyek dan di beat difilter/ditandai berdasarkan dukungan rasio (`_aspect_option` yang sudah ada); bila user tetap memakai model yang tidak cocok, hasil di-crop tengah ke rasio proyek dengan peringatan.
6. **(S) Durasi adegan lama 1–120 dtk di tabel yang sama.** Membatasi `planned_seconds` ke 4–15 akan merusak alur lama.
   - Mitigasi: batas 4–15 hanya diterapkan saat generate v2 (validasi di `seedance_request.build`), bukan di skema. UI v2 menandai adegan di luar batas; data tidak diubah.
7. **(S) Persetujuan suara.** Unggahan suara bisa berisi suara orang lain.
   - Mitigasi: centang wajib "ini suara saya atau saya punya izin pemiliknya" saat unggah (disimpan di versi suara); teks larangan kloning tokoh publik di UI; TTS hanya suara sintetis dari katalog.
8. **(S) Privasi audio di URL publik.** Suara user dikirim lewat URL publik (tunnel/S3).
   - Mitigasi: hanya URL presigned/berumur pendek (pola plan 10), dibuat per request; dicatat di UI bahwa audio diunggah ke host publik sementara.
9. **(R) Salin workspace** belum menyebut pengaturan dan suara.
   - Mitigasi: copy menyalin pengaturan proyek dan versi suara aktif (bukan riwayat versi naskah/beat).

## Risiko (dampak, kemungkinan, mitigasi)
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| Seedance mengabaikan `@Image N` / gambar beat dipakai sebagai kolase, bukan acuan per shot | Tinggi (inti kebutuhan 5–6) | Sedang | Spike uji 1–2 sebelum kode; cadangan mode frame; bila keduanya lemah, gambar beat hanya untuk shot pertama + prompt bertimecode, didokumentasikan |
| Timing per detik tidak presisi (durasi keluaran beda, plan 03: 4 vs 5 dtk) | Sedang | Tinggi | UI menyebut beat sebagai "acuan", bukan jaminan; timeline episode memakai durasi klip nyata (`media.probe`) |
| Referensi audio tidak diterima / suara tidak mengikuti | Sedang | Sedang | Spike uji 3; cadangan deskripsi suara di prompt; peringatan "suara tidak dikunci" di pratinjau |
| Lip-sync/dialog bahasa Indonesia buruk | Sedang | Sedang | Tambah uji spike dialog bahasa Indonesia vs Inggris; pengaturan proyek "bahasa dialog" |
| Wajah fotorealistis ditolak Seedance | Tinggi untuk proyek realis | Tinggi | Gaya proyek default non-fotoreal; error penolakan diterjemahkan ke pesan jelas + saran |
| Biaya estimasi meleset (token/detik tidak dipublikasikan) | Sedang | Tinggi | Kalibrasi spike; setelah tiap job, rasio biaya nyata/estimasi dicatat; estimasi memakai kalibrasi terbaru + margin 20% |
| Ledakan versi/take memenuhi disk | Rendah | Sedang | Soft-delete + bulk delete (plan 12) berlaku untuk take; versi naskah dibatasi 50 |
| Rantai basi salah (positif palsu/negatif palsu) | Sedang | Sedang | Hash input eksplisit per jenis hasil, unit test tiap mata rantai |

## Edge case
- Beat tanpa pemeran (shot latar saja): gambar beat hanya dengan referensi latar; prompt tanpa legenda karakter.
- Pemeran beat tidak ada di pemeran adegan (`scene_cast`): ditolak validasi; bila pemeran adegan dihapus, beat yang menyebutnya ditandai rusak, tidak dihapus diam-diam.
- Karakter tanpa gambar, latar tanpa gambar: generate gambar beat ditolak dengan alasan; video masih boleh dari gambar beat saja.
- Beat > 6, atau beat + karakter + latar > 9 gambar: aturan pembuangan; peringatan di pratinjau.
- Adegan 1 beat: mode referensi tetap; mode frame hanya first_frame.
- Mode frame dengan 3+ beat: beat tengah tidak dikirim sebagai gambar; peringatan "beat 2–N hanya lewat teks".
- Dialog terlalu panjang untuk durasi beat (> ±3 kata/detik): peringatan di beat.
- Durasi adegan berubah setelah beat dibuat: beat diskalakan proporsional (bawaan) atau beat terakhir dipotong/diperpanjang; gambar beat ditandai basi bila beat bergeser > 1 dtk.
- Take terpilih dihapus (soft-delete): `image_id` beat dikosongkan, video yang memakainya basi.
- Suara aktif berganti ke versi lebih lama: video ditandai basi (hash berubah) walau versinya pernah dipakai; benar secara definisi hash.
- Rasio proyek diubah saat belum ada aset v2, tetapi ada keyframe lama: diizinkan dengan peringatan (aset lama di luar v2 tidak mengunci).
- Hosting publik mati di tengah batch: adegan yang butuh audio/video gagal dengan pesan; yang tidak butuh tetap jalan.
- Workspace dihapus/diarsipkan saat batch berjalan: job yang sudah terkirim tetap dicatat (perilaku plan 07).
- Model video di pengaturan hilang dari katalog OpenRouter: pengaturan ditandai tidak valid; generate diblokir sampai diganti.

## Potensi bug
- `@Image N` dihitung termasuk audio/video, atau gambar dinomori ulang setelah pembuangan tetapi legenda prompt tidak: penomoran harus dihasilkan dari daftar akhir yang sama (satu fungsi, satu sumber), dan diuji.
- Urutan beat setelah drag batas: `start`/`end` float bertumpuk (0,1 + 0,2): bulatkan ke 0,1 dtk di validasi; bandingkan dengan toleransi.
- Hash input memakai `json.dumps` tanpa `sort_keys` → hash berubah tanpa perubahan nyata: wajib JSON kanonik (`sort_keys=True`, separator tetap).
- Basi dihitung untuk banyak adegan per request daftar episode (N+1 query): hitung per episode dalam satu kueri gabungan.
- Snapshot beat diambil setelah penerapan (bukan sebelum) → "kembalikan" tidak mengembalikan apa-apa: urutan di satu transaksi, diuji.
- Revisi gambar beat memakai take terpilih saat itu, tetapi user berganti take sebelum konfirmasi: id sumber ikut di body request dan di estimasi (409 bila berubah, pola plan 04).
- Batch berjalan di browser (pola `useBatch`): menutup tab menghentikan sisa; dicatat, tidak diperbaiki di plan ini.
- Migrasi v14 mengisi rasio proyek dari modus episode: seri → rasio episode terbaru; workspace tanpa episode → 16:9.

## Asumsi yang belum terbukti
1. Seedance lewat OpenRouter menghormati notasi `@Image N` (spike 1).
2. Prompt bertimecode multi-shot diikuti (spike 2).
3. Audio diterima sebagai `input_references` dan nama tipenya (spike 3).
4. 9 gambar diterima dalam satu request (spike 4).
5. Token per detik per SKU (spike 5).
6. Ada model TTS di OpenRouter yang bisa dipanggil dengan kunci yang sama (spike 6, gratis).
7. Edit video terarah lewat `video_url` (spike 7).
8. Dialog bahasa Indonesia dengan lip-sync layak (spike 8, baru).
9. Gambar beat buatan model gambar lain (bukan Seedance) cukup konsisten dengan karakter sehingga tidak "melawan" gambar karakter di referensi yang sama. Diamati di spike 2.

## Keputusan setelah grilling (perubahan pada plan)
1. Rasio: satu sumber; `films.aspect_ratio` diselaraskan ke rasio proyek dan jadi baca-saja (lubang 1).
2. Estimasi menampilkan alasan blokir per job dan perkiraan biaya per 10 dtk di pengaturan proyek; batas tidak diubah agent (lubang 2).
3. Batch v2 menghitung sisa anggaran harian dan menawarkan "jalankan yang muat saja" (lubang 3).
4. Referensi gambar diperkecil ≤ 1536 px JPEG q85 sebelum dikirim (lubang 4).
5. Model gambar difilter/ditandai berdasarkan rasio; crop tengah sebagai cadangan (lubang 5).
6. Batas 4–15 dtk hanya di generate v2 (lubang 6).
7. Centang izin suara wajib; URL audio presigned berumur pendek (lubang 7–8).
8. Copy workspace menyalin pengaturan + suara aktif (lubang 9).
9. Spike ditambah uji 8 (dialog bahasa Indonesia vs Inggris) dan pengamatan asumsi 9; batas tetap $2,00 (disetujui user).
10. Penomoran referensi dan legenda prompt dihasilkan dari satu daftar akhir; hash input pakai JSON kanonik.

## Riwayat
- 2026-10-26: grill awal.
- 2026-10-26: plan Revisi 2 (user: "gausa ada batas di sini") menggantikan keputusan 2, 3, dan batas spike di keputusan 9: v2 tidak diblokir batas per job/harian, spike tanpa plafon. Temuan baru dari revisi itu, untuk dimitigasi di implementasi:
  - (S) Tanpa batas, satu klik batch bisa menagih sangat besar. Mitigasi: dialog konfirmasi menampilkan total dengan huruf besar + jumlah request; konfirmasi total di atas $10 meminta ketik ulang angka totalnya (bukan batas, hanya pengaman salah klik). Perlu persetujuan user saat implementasi; bila ditolak, dihapus.
  - (S) Segmen otomatis: sambungan antar segmen bisa terlihat (lompatan pose/cahaya). Mitigasi: gambar beat terakhir segmen sebelumnya jadi referensi; pratinjau menampilkan titik potong segmen; user bisa menggeser titik potong ke batas beat lain.
  - (S) `merge_videos` antar segmen: durasi keluaran tiap segmen bisa beda dari rencana; timeline memakai durasi nyata.
  - (R) Batas 120 dtk skema lama dilepas untuk v2: kolom `planned_seconds` INTEGER tanpa CHECK di DB, validasi ada di `scenes.py`; v2 memakai validasi sendiri (≥ 4 dtk total, tanpa batas atas).
  - (R) Total harian tetap dihitung untuk informasi; `committed_today` tidak boleh dipakai untuk memblokir jalur v2 (diuji).

---

## Grill Revisi 4 — format prompt shot Seedance 2.0

| # | Temuan | Mitigasi |
|---|---|---|
| R4-1 | `@image_N` dan timestamp `m:ss` belum terbukti diterima Seedance via OpenRouter (spike dilewati, kredit habis). | Format ada di satu fungsi (`seedance_request.build`); didokumentasikan sebagai "belum terbukti". |
| R4-2 | Model teks murah melanggar aturan (shot >3 dtk, tumpang tindih, total ≠ durasi). | Keluaran JSON, divalidasi `beats.clean()`; satu kali ulang dengan pesan galat; lalu ditolak (422), tidak diperbaiki diam-diam. |
| R4-3 | Migrasi v16 menyentuh 5 tabel; beat lama tidak punya size/lens. | Semua kolom nullable; bagian kosong dilewati di prompt. Tes migrasi dari v15. |
| R4-4 | WARDROBE kosong memicu model mengarang pakaian di tiap shot. | Bagian dihilangkan; baris konsistensi tetap merujuk gambar acuan. |
| R4-5 | Tes lama mengunci `@Image N`. | Ditulis ulang, bukan dilonggarkan. |
| R4-6 | Panggilan AI berbayar. | Estimasi + konfirmasi (kind `scene_beats`); tes memakai OpenRouter palsu. |
| R4-7 | Deadlock `db._lock` tak reentrant. | Prefetch sebelum `transaction()`. |

---

## Grill Revisi 5 — naskah berformat Seedance

| # | Temuan | Mitigasi |
|---|---|---|
| R5-1 | Model murah melanggar format (label hilang, timestamp salah, shot >3 dtk, total ≠ FORMAT). | Keluaran AI diurai `script_format.parse` + `beats.clean`; salah → ulang SEKALI dengan daftar galat, lalu 502. Tidak diperbaiki diam-diam. |
| R5-2 | Naskah campuran (sebagian prosa). | Deteksi: ≥1 baris `SHOT n — … to …` DAN ≥1 `FORMAT:`. Teks di luar blok diabaikan dengan peringatan; tanpa blok → jalur AI lama. |
| R5-3 | Nama berspasi / beda huruf besar-kecil di mention. | Pencocokan memakai `script.key` (casefold) seperti `analyze`; nama tak dikenal → peringatan, mention dilepas dari pemeran (tidak membuat entitas baru). |
| R5-4 | >3 pemeran per adegan (batas aplikasi) atau adegan >15 dtk (batas Seedance). | Galat per adegan dengan nomor adegan; tidak ada pemotongan diam-diam. |
| R5-5 | Dialog tidak punya sintaks di format asli. | Diputuskan `@[Nama] says: "…"`; baris lain tetap sebagai aksi. |
| R5-6 | Penerapan sebagian (adegan dibuat, beat gagal). | `apply_split` memvalidasi SEMUA beat sebelum membuat adegan pertama. |
| R5-7 | Draf dari klien dipalsukan. | `apply_split` memvalidasi ulang lewat `clean_split` + `beats.clean` terhadap pemeran episode saat ini. |
| R5-8 | Deadlock `db._lock`. | Tidak ada `db.*` di dalam `transaction()`; `Beats.replace` dipanggil di luar transaksi. |
| R5-9 | Label tidak baku (`Adegan`, `SCENE`). | Hanya `ADEGAN`/`SCENE` dikenali sebagai pemisah; selebihnya galat yang menyebut barisnya. |

---

## Grill Revisi 6 — ubah adegan dengan AI

| # | Temuan | Mitigasi |
|---|---|---|
| R6-1 | Model mengubah hal yang tidak diminta. | Prompt "ubah seperlunya"; server menandai tiap shot `changed` (dibanding beat lama) supaya UI menyorot; user melihat sebelum/sesudah; draf tidak tersimpan. |
| R6-2 | Total durasi bergeser. | Instruksi boleh mengubah durasi lewat `total_seconds` (1–15); shot terakhir wajib berakhir tepat di sana (atau durasi sekarang bila tak disebut). Salah → ulang sekali → 502. |
| R6-3 | `keep` salah/ganda/di luar rentang. | Hanya bilangan bulat 1..N sekali pakai yang dipercaya; sisanya dianggap shot baru (tanpa id/gambar lama). |
| R6-4 | Instruksi berisi perintah ("abaikan aturan…"). | Instruksi ditaruh di blok terpisah berlabel data; aturan format dan skema tetap divalidasi server, jadi keluaran menyimpang ditolak. |
| R6-5 | Penerapan menimpa kerja yang belum tersimpan. | Konfirmasi bila editor adegan itu dirty; penyimpanan memotret versi lama (bisa dikembalikan). |
| R6-6 | MOOD/waktu tersimpan padahal user membuang. | Hanya masuk ke adegan saat Simpan; Buang draf = tak ada efek. |
| R6-7 | Biaya ganda saat ulang. | Estimasi memakai batas atas; konfirmasi yang sama dipakai untuk kedua panggilan; keduanya tercatat. |
| R6-8 | Deadlock kunci DB. | Tanpa `db.*` di dalam transaksi; sama dengan `generate_ai`. |

---

## Grill Revisi 7 — ubah naskah dengan AI

| # | Temuan | Mitigasi |
|---|---|---|
| R7-1 | Model menulis ulang blok yang tidak diminta. | Prompt "salin utuh"; server menandai `changed` per blok (dibanding naskah lama) supaya terlihat; draf tidak tersimpan. |
| R7-2 | Naskah panjang terpotong di batas token keluaran. | Batas keluaran = f(panjang naskah) (4.000–16.000); jawaban `finish_reason=length` sudah ditolak `textai` (502). Naskah > batas dicegah dengan 422 sebelum memanggil AI. |
| R7-3 | Biaya besar (naskah masuk + keluar utuh). | Estimasi memakai batas atas yang sama dengan panggilan; konfirmasi wajib; kedua percobaan tercatat. |
| R7-4 | Nomor adegan bergeser membuat perbandingan salah. | Pencocokan blok berdasarkan isi (normalisasi spasi, header ADEGAN n diabaikan), bukan nomor. |
| R7-5 | Instruksi menyuntik perintah. | Instruksi di blok DATA; keluaran tetap diurai dan ditolak bila melanggar format. |
| R7-6 | User mengedit naskah saat AI bekerja, hasil menimpa. | Respons memuat `base_hash` naskah yang dikirim; UI menolak menerapkan bila editor sudah berubah (konfirmasi), dan Simpan tidak otomatis. |
| R7-7 | Mention ke karakter/latar baru yang dikarang AI. | Pengurai: nama tak dikenal = peringatan yang ditampilkan di pratinjau; tidak ada entitas dibuat. |
| R7-8 | Duplikasi logika `_check_script`. | Digeneralisasi (parameter jenis & batas token), bukan salinan. |

---

## Grill Revisi 8 — prompt adegan sebagai sumber tunggal

| # | Temuan | Mitigasi |
|---|---|---|
| R8-1 | Prompt tidak bisa diurai → user tak bisa menyimpan. | PUT mengembalikan 422 dengan nomor adegan/baris; teks tetap di editor (tidak dibuang); tidak ada penyimpanan sebagian karena semua divalidasi (urai + `beats.clean` + nama) SEBELUM menulis. |
| R8-2 | Dua jalur edit (editor Beat, revisi AI, API cast) membuat prompt basi. | Setiap jalur lain yang mengubah latar/pemeran/beat/mood/durasi mengosongkan `scenes.prompt`; GET merender ulang dari data. PUT prompt menulis kolom `prompt` TERAKHIR. Tes untuk tiap jalur. |
| R8-3 | Hilangnya tampilan (outfit)/aksi karakter per adegan saat pemeran diturunkan dari prompt. | Karakter yang sudah ada di adegan mempertahankan `outfit_id` dan `action`; hanya karakter baru yang kosong. |
| R8-4 | Nama ganda di proyek (dua karakter bernama sama). | Galat eksplisit ("bernama ganda"), tidak dipilih acak. |
| R8-5 | Nama tak dikenal di prompt. | Galat 422, bukan entitas baru; karakter/latar PROYEK yang ada tapi belum di episode otomatis ikut masuk episode. |
| R8-6 | `time_of_day`, `camera`, `dialogue` adegan tidak ada di format. | Tidak ditimpa oleh PUT prompt (tetap data lama); di inspector v2 disembunyikan karena prompt memuatnya. |
| R8-7 | Adegan lama tanpa prompt / data yang tak bisa dirender. | `render` selalu menghasilkan blok yang lolos urai (tes sapuan: render → urai → data sama); tanpa beat dibuat satu shot sepanjang durasi. |
| R8-8 | Transaksi: promise "satu transaksi". | Dilakukan berurutan di bawah `Studio._lock` (RLock) setelah validasi penuh; simpan `prompt` terakhir. Penyimpangan dicatat; gagal di tengah hanya mungkin karena galat I/O, bukan input. |
| R8-9 | Nomor `@image_N` basi saat aset berubah. | Prompt menyimpan NAMA (`@[Momon]`); `@image_N` ditentukan server saat kirim dari daftar referensi aktual. |
| R8-10 | Mention aset tanpa gambar. | Peringatan di editor dan panel video; tetap boleh kirim (karakter hanya-teks sah). Penyimpangan dari plan (yang menolak 422), karena karakter tanpa gambar adalah kasus sah. |
| R8-11 | Dua kotak prompt di panel video. | Satu: panel video menyunting prompt adegan yang sama; override `prompt` di POST tidak lagi dikirim UI. |
| R8-12 | Deadlock `db._lock`. | Tanpa `db.*` di dalam `transaction()`. |

---

## Grill Revisi 9 — frame awal dari adegan sebelumnya

| # | Temuan | Mitigasi |
|---|---|---|
| R9-1 | `frame_images` + `input_references` tidak boleh digabung; mengirim keduanya bisa ditolak atau frame diabaikan. | Mode frame TIDAK mengirim `input_references` sama sekali (tes memastikan payload). Gambar/latar/suara dijelaskan di UI. |
| R9-2 | Adegan sebelumnya belum punya klip selesai / berkas hilang / dihapus. | `plan` strict → 422 dengan nomor adegan; pratinjau non-strict memberi peringatan dan `can_start_from_prev` supaya kotak centang tetap bisa dilepas. |
| R9-3 | Adegan pertama atau urutan berubah. | Kolom ditolak 422 untuk adegan pertama; "sebelumnya" dihitung dari urutan SAAT generate; adegan yang jadi pertama setelah dihapus/reorder diperlakukan tanpa frame awal dengan peringatan (bukan galat). |
| R9-4 | Frame akhir hitam/fade. | Tidak bisa dideteksi andal; dicatat sebagai keterbatasan, frame tersimpan di library sehingga bisa dilihat. |
| R9-5 | Rasio frame ≠ rasio proyek. | Klip adegan sebelumnya dibuat dengan rasio proyek; rasio terkunci setelah ada klip v2 (sudah ada). |
| R9-6 | Frame yatim di library bila penyedia menolak. | Hapus gambar + berkas pada galat (pola `extend_clip`); tes. |
| R9-7 | Klip adegan sebelumnya diganti setelah adegan ini dibuat. | `params.start_from.clip_id` tercatat; UI menandai "berantai dari adegan N". Peringatan basi otomatis di luar lingkup. |
| R9-8 | Batch menjalankan adegan berantai sebelum induknya selesai. | Batch hanya mengikutkan adegan berantai yang induknya sudah `completed`; sisanya "menunggu adegan N". |
| R9-9 | Previs + frame bentrok. | 422 jelas (previs butuh `input_references`). |
| R9-10 | Biaya. | Estimasi i2v 1 gambar; konfirmasi biaya wajib; basi → 409. |
| R9-11 | Deadlock kunci DB. | Ekstraksi ffmpeg di luar `Studio._lock` dan di luar transaksi. |

---

## Grill Revisi 10 — ubah adegan dengan AI di langkah Adegan

| # | Temuan | Mitigasi |
|---|---|---|
| R10-1 | Model mengubah bagian yang tidak diminta. | Prompt "ubah seperlunya, salin sisanya persis"; server menandai baris berubah (multiset, bukan posisi) sehingga terlihat; draf tidak tersimpan. |
| R10-2 | Mengembalikan >1 blok / menghapus label / format rusak. | `ScenePrompt.parse` (satu blok, FORMAT/SUBJECT/ENVIRONMENT, SHOT bersambung); salah → ulang sekali → 502. |
| R10-3 | Nama karakter/latar dikarang. | `parse` menolak nama yang tidak ada di proyek (sama seperti Simpan), jadi tidak mungkin lolos ke editor sebagai draf valid. |
| R10-4 | Instruksi menyuntik perintah. | Blok DATA; keluaran tetap divalidasi. |
| R10-5 | Editor kotor saat tombol ditekan; estimasi ≠ panggilan. | UI mengunci tombol selama kotor; server selalu memakai prompt TERSIMPAN (atau render dari data). Estimasi dengan instruksi dipadatkan konstan. |
| R10-6 | Nomor ADEGAN/durasi berubah. | Aturan prompt "nomor tetap"; durasi >15 dtk ditolak oleh `parse`. |
| R10-7 | Biaya ganda saat ulang. | Estimasi batas atas, konfirmasi yang sama, kedua panggilan tercatat. |
| R10-8 | Draf menimpa teks tanpa sadar. | Hanya masuk ke editor lewat "Terapkan"; editor lalu "belum disimpan" dan bisa "Batalkan perubahan". |

---

## Grill Revisi 11 — pilih adegan sumber frame awal

| # | Temuan | Mitigasi |
|---|---|---|
| R11-1 | Migrasi data lama (`start_from_prev = 1`). | Diisi id adegan tepat sebelumnya (posisi - 1, episode sama) saat migrasi; tes migrasi v18 → v19. `start_from_prev` tak dibaca lagi. |
| R11-2 | Adegan sumber dihapus (satuan, massal, hapus episode). | Semua jalur hapus mengosongkan `start_from_scene_id` yang menunjuk ke sana; tes. |
| R11-3 | Sumber di episode lain atau workspace lain. | Validasi: sumber harus satu `film_id` dengan adegan ini dan bukan dirinya (422); workspace dicek lewat `_scene`. |
| R11-4 | Rantai melingkar (A dari B, B dari A). | Aman: hanya butuh klip selesai, tidak rekursif. Batch: keduanya "menunggu" sampai salah satu punya video (tidak macet karena user bisa membuat salah satu tanpa frame awal). |
| R11-5 | Sumber tanpa video selesai / berkas hilang. | `start_info` per sumber; generate 422; pratinjau non-strict + daftar kandidat dengan alasan. |
| R11-6 | Duplikat adegan. | Tidak menyalin pilihan (bawaan Tidak). |
| R11-7 | Adegan diurutkan ulang: nomor sumber bergeser. | Disimpan sebagai id, nomor dihitung saat tampil/generate (`start_from_number`). |
| R11-8 | Klaim keamanan klien: id sembarang. | Validasi server (R11-3); id tak dikenal → 404/422. |
