# 17 - Scene 3D yang lebih kaya dibuat AI + pilihan model LLM (Grill)

Plan terkait: `docs/plan/17-ai-3d-scene-and-text-model-plan.md` (draft + Revisi 1 tiga lapis + Revisi 2 jenis tubuh).
Tanggal: 2026-10-26. Sumber:
- Dokumentasi OpenRouter (dibaca hari ini): `docs/features/structured-outputs`, `docs/use-cases/reasoning-tokens`.
- Katalog nyata `GET /models` (467 model; 290 lolos saringan; 268 `structured_outputs`; 220 `reasoning`; 179 gambar + terstruktur).
- Kode: `textai.py`, `openrouter.py` (`chat_json`), `scenes.py` (`_blockout_context`, `previs_video_plan`), `workspaces.py` (salin), `blockout.py`, `storyboard/blockoutMath.ts`, `storyboard/blockoutScene.ts`.

User menjawab "oke grill" atas plan + Revisi 1 + Revisi 2; bawaan pertanyaan terbuka dianggap disetujui (tiga lapis; bawaan model per tugas di browser; eval ≤ $0.30; fase 4 setelah fase 1–3 dicoba). Dikonfirmasi ulang di laporan.

## Temuan dari dokumentasi
1. **Skema ketat tidak didukung → permintaan GAGAL** ("The request will fail with an error indicating lack of support"), bukan diabaikan. Penegakan "varies by provider": sebagian penyedia menjamin, sebagian hanya menganggapnya petunjuk. Ada `provider.require_parameters: true` agar hanya diarahkan ke penyedia yang mendukung.
2. **Batasan mode ketat tidak dicantumkan** ("See the provider's documentation"). Contoh resmi: semua field di `required`, `additionalProperties: false`.
3. **Token penalaran ditagih sebagai keluaran dan memakan `max_tokens`**, juga saat `exclude: true`. Bila penalaran menghabiskan `max_tokens`: `finish_reason: "length"` dengan isi kosong, tetap ditagih.
4. Bentuk `reasoning`: `{"effort": …}` **atau** `{"max_tokens": …}` (tidak keduanya), plus `exclude`, `enabled`. Perilaku mengirim `reasoning` ke model tanpa penalaran **tidak dijelaskan**.
5. Bentuk masukan gambar di chat completions **belum diverifikasi** dari dokumen (halaman yang dibaca tidak membahasnya). Fase 4 harus memverifikasinya dulu.

## Temuan dari kode
6. **`textai.prices()` memanggil `GET /models` (467 model) setiap estimasi, tanpa cache.** `useEstimate` di UI memintanya tiap kali isian berubah. Dengan pemilih model di empat tempat, ini lambat dan boros. Perlu cache 5 menit (pola `video_models()`).
7. **Salin karakter ke workspace lain menulis kolom satu per satu** (`workspaces.py`, `new_chars.append({...})`): kolom `characters.look` baru akan hilang saat disalin.
8. **Tabel sendi, batas, dan pose ada di dua tempat** (`blockout.py` dan `blockoutMath.ts`). Grill 14 memutuskan batas hanya di frontend. Revisi 1 meminta satu sumber; dengan jenis tubuh baru, dua tabel pasti menyimpang.
9. **Rumus lensa → FOV (`fovFor`) hanya ada di TS.** Pemecah di Python yang memeriksa "aktor di dalam bingkai" harus memakai rumus yang sama persis.
10. **`previs_video_plan` memetakan tokoh ke warna indeks** (`MANNEQUIN_COLORS`). Dengan `look`, pemetaan harus diganti, dengan cadangan ke cara lama bila `look` kosong.
11. `public()` adegan dipanggil saat film dimuat dan saat polling tiap 3 dtk selama ada render/video berjalan. Pemecah tata letak tidak boleh berjalan di jalur itu.

## Lubang pada plan
1. **Referensi pementasan ke objek set:** "Rani duduk di kursi_2". Bila set diubah (kursi dipindah/dihapus), pementasan bisa menunjuk objek yang hilang. Objek set butuh **id stabil**; relasi ke id yang hilang jatuh ke koordinat terakhir dengan peringatan.
2. **Kapan pemecah dijalankan:** saat simpan (hasilnya disimpan) **dan** di endpoint "susunan siap render" (`GET /api/scenes/{id}/blockout/resolved`, menggabungkan set latar + pementasan lalu memecahkannya). Editor dan render previs memakai endpoint ini; daftar adegan tidak.
3. **Waktu adegan vs cahaya set:** set punya cahaya bawaan, adegan punya `time_of_day`. Aturan: lingkungan adegan menimpa bawaan set.
4. **`look` basi:** deskripsi karakter berubah setelah `look` dibuat. Simpan hash deskripsi; editor menandai "deskripsi berubah, perbarui penampilan".
5. **Sumber kosakata tunggal:** endpoint `GET /api/blockout/vocabulary` membuat editor bergantung jaringan. Lebih sederhana: **satu berkas JSON di repo** (`shared/blockout_vocabulary.json`) dibaca Python dan diimpor TS saat build. Risiko: Vite dev membatasi impor di luar root → perlu `server.fs.allow` (diuji lewat build; dev diuji user).
6. **Eval:** batas $0.30 bisa terlewati bila ada model mahal di kandidat. Eval menghitung estimasi per model sebelum jalan dan melewati model yang estimasinya melebihi sisa batas.
7. **Ruang lingkup jenis tubuh:** `bird`, `serpent`, `blob` menambah kerangka, pose, dan gerak masing-masing. Terlalu besar untuk satu putaran.

## Risiko
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| Skema ketat ditolak model/penyedia | Galat, user bingung | Sedang | Skema hanya untuk model ber-`structured_outputs`, dengan `require_parameters`; galat 4xx tentang skema → ulang **sekali** dengan `json_object` (permintaan yang ditolak sebelum diproses tidak menghasilkan token; diverifikasi di eval). |
| Skema memakai fitur yang tidak didukung penyedia | Galat | Sedang | Skema konservatif: semua field `required` (nilai kosong lewat `null`), `additionalProperties: false`, enum, tanpa `oneOf`, kedalaman ≤ 5, larik dibatasi. |
| Penalaran menghabiskan token | Isi kosong, tetap ditagih | Sedang | `reasoning: {"effort": "low"}` hanya untuk model ber-`reasoning`; `finish_reason: "length"` + isi kosong → pesan "model kehabisan token untuk berpikir; pilih model lain atau upaya lebih rendah"; biaya tetap tercatat. |
| Estimasi terlalu rendah (penalaran tidak dihitung dalam `max_tokens` pada sebagian penyedia) | Biaya nyata > estimasi | Rendah | Estimasi tetap `max_tokens` penuh × harga keluaran; biaya nyata dicatat dari `usage.cost`; dicatat sebagai asumsi. |
| Pemecah tidak konvergen di set padat | Objek masih bertabrakan | Rendah | Batas iterasi; sisa tabrakan dilaporkan sebagai peringatan, bukan galat. |
| Rotasi bebas mengacaukan kotak batas | Tabrakan salah hitung | Sedang | Pemecah memakai kotak batas sejajar sumbu setelah rotasi sumbu Y; rotasi X/Z hanya untuk benda dekoratif (tidak ikut tabrakan). |
| FOV Python ≠ three.js | "Aktor di bingkai" salah | Sedang | Rumus di satu tempat (berkas kosakata/konstanta) + test paritas Python vs TS dengan node (pola parser mention plan 15). |
| Bayangan + perekaman real-time | Previs patah-patah | Sedang | Bayangan dibatasi; resolusi peta bayangan diturunkan saat merekam; target 30 fps diuji user. |
| Ukuran pekerjaan | Mutu turun, jadwal molor | Tinggi | Lihat keputusan ruang lingkup di bawah. |

## Edge case
- Susunan v1 tersimpan: dimuat sebagai v2 dengan `body: humanoid`, tanpa set latar (properti v1 menjadi properti adegan).
- Adegan tanpa latar: pementasan tanpa set (lantai kosong + langit sesuai waktu).
- Latar tanpa set: tombol "susun set latar" di editor; pementasan tetap bisa dibuat.
- Karakter tanpa `look`: dibuat otomatis saat pementasan pertama memintanya, atau manekin bawaan dengan peringatan.
- Model dipilih lalu hilang dari katalog: server menolak (422) sebelum biaya; pemilih jatuh ke bawaan.
- Dua adegan di latar yang sama dibuka berbarengan dan set diubah di salah satunya: set disimpan sekali; adegan lain mengambil versi terbaru saat dibuka.

## Potensi bug
1. `look` hilang saat salin workspace (temuan 7). Test.
2. Cache harga model kosong saat OpenRouter gagal: estimasi 502 yang jelas, bukan harga 0.
3. JSON dengan teks pengantar (`"Here is the JSON: {...}"`): pengurai toleran mengambil objek seimbang pertama; test.
4. Objek `on` di atas objek yang juga `on` (cangkir di atas piring di atas meja): pemecah memproses berurutan topologis; siklus ditolak dengan peringatan.
5. Relasi `against` ke dinding yang tidak ada (set tanpa dinding): pakai batas set.

## Asumsi yang belum terbukti
- Model murah (≤ $1/juta token keluaran) mampu mengisi skema set/pementasan dengan relasi yang masuk akal. Diuji eval.
- Permintaan yang ditolak karena skema tidak berbiaya. Diuji eval (bandingkan saldo/`usage`).
- Manekin berkaki empat yang dibuat dari primitif cukup terbaca sebagai hewan oleh Seedance. Diuji user setelah fase 3.

## Keputusan setelah grilling (perubahan pada plan)
- **Ruang lingkup:** jenis tubuh di plan ini hanya `humanoid` dan `quadruped`. `bird`, `serpent`, `blob` dipindah ke plan terpisah. Fase 4 (berbasis gambar) tidak dikerjakan sekarang.
- **Kosakata tunggal:** `shared/blockout_vocabulary.json` (bentuk, prefab + ukuran dan permukaan atas, jenis tubuh + sendi + batas + pose + parameter, gaya rambut, aksesori, preset waktu, konstanta lensa). Python membacanya; TS mengimpornya. `LIMITS/POSE_LIB/JOINTS` di TS dan daftar di `blockout.py` dipindah ke sana.
- **Pemecah:** `layout_solver.py` murni; dijalankan saat simpan dan di `GET /api/scenes/{id}/blockout/resolved`; tidak di daftar adegan. Objek set punya id stabil; relasi ke id hilang jatuh ke koordinat terakhir + peringatan.
- **Model teks:** cache daftar model 5 menit; skema ketat + `require_parameters` untuk model ber-`structured_outputs`, ulang sekali dengan `json_object` bila ditolak karena skema; `reasoning: {"effort": "low"}` hanya untuk model ber-`reasoning`; isi kosong + `length` diberi pesan khusus.
- **Data:** migrasi v13 `locations.set_layout`, `characters.look`, `characters.look_hash`; salin workspace menyalin `look`.
- **Video dari previs:** pakai `look` (jenis tubuh + penampilan) bila ada, cadangan warna indeks bila tidak.
- **Urutan fase tetap** (1 model → 2 kosakata/pemecah/render → 3 AI tiga lapis); eval dijalankan di akhir fase 1 dan diulang singkat di fase 3 dengan kasus hewan.

## Riwayat
- 2026-10-26: grill awal.
