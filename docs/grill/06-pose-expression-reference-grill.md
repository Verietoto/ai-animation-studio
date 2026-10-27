# 06 - Referensi Pose & Ekspresi di Edit Foto (Grill)

Plan terkait: `docs/plan/06-pose-expression-reference-plan.md`

Keparahan: **T** tinggi, **S** sedang, **R** rendah. Temuan bertanda (kode) sudah dicek di repo.

## Lubang pada plan
1. **(T) Estimasi dan generate bisa menghitung jumlah gambar berbeda (kode).** `EstimateIn` hanya membawa `reference_count`; server tidak tahu isi sheet karakter, apakah pose sama dengan referensi umum, atau sheet mana yang dipangkas. Frontend sekarang menebak `refs.length + (characterId ? 3 : 0)` (`EditPage.tsx`), padahal sheet bisa 4-5 gambar. Generate menghitung ulang di server → estimasi lebih tinggi dari yang dikonfirmasi → 409 dan dialog konfirmasi muncul lagi, berulang di setiap edit dengan karakter.
   - Mitigasi: satu fungsi bersama `plan_inputs(source_id, character_id, pose_id, expression_id, reference_ids, max_refs)` yang mengembalikan daftar id terurut + peran. Dipakai oleh `edit_image` **dan** `/api/estimate`; `EstimateIn` untuk `image_edit` menerima id yang sama (bukan hitungan). Tes: angka estimasi == angka yang diotorisasi saat generate untuk kombinasi karakter/pose/ekspresi/umum.
2. **(T) Kebocoran identitas dari gambar pose/ekspresi belum ada mitigasi nyata selain kalimat prompt.** Model edit cenderung menyalin wajah, rambut, baju, bahkan warna kulit dari gambar referensi yang memuat orang. Instruksi "ignore identity" tidak terbukti dipatuhi.
   - Mitigasi: spike membandingkan **pose mentah** vs **pose sebagai sketsa garis** (grayscale + deteksi tepi PIL `FIND_EDGES` + kontras; tanpa dependency baru). Bila sketsa jelas lebih sedikit bocor dan pose tetap diikuti, sketsa jadi default untuk slot pose (dengan opsi "pakai gambar asli"). Untuk ekspresi, **preset teks jadi jalur utama** di UI; gambar ekspresi diberi peringatan dan dianjurkan crop wajah sebelum diunggah.
3. **(T) Instruksi bertentangan di prompt.** "Image 1 is the scene to edit, keep it" vs "copy the pose from image 4": model bisa mempertahankan pose asli gambar 1 (sumber paling kuat) dan mengabaikan pose referensi.
   - Mitigasi: kalimat peran gambar 1 diubah eksplisit: "Image 1 provides the character's identity, background and lighting. Change the pose to match image 4 even though it differs from image 1." Diuji di spike (kasus: pose sumber berdiri → referensi duduk).
4. **(S) Urutan `input_references` belum terbukti dipertahankan OpenRouter/provider.** Seluruh skema "Image N" bergantung pada urutan.
   - Mitigasi: spike memakai gambar pose yang sangat berbeda dari sumber (orang lain, baju warna mencolok) sehingga kalau urutan/peran tertukar terlihat jelas. Tes backend memastikan urutan yang **kita kirim** benar; urutan di sisi provider hanya bisa dibuktikan oleh spike.
5. **(S) Panjang prompt (kode).** `edit_image` memeriksa `len(prompt) > 4000` **sebelum** menambah teks karakter; prompt berperan menambah ~600-900 karakter + deskripsi karakter (maks 2000) + teks pose/ekspresi (2 × 200). Prompt final bisa melewati batas provider tanpa pernah diperiksa.
   - Mitigasi: batas diperiksa pada prompt final; batas prompt user diturunkan ke 2000 di UI dan server (pesan jelas), deskripsi karakter dipotong di batas kalimat bila perlu.
6. **(S) Gambar yang sama dipakai di beberapa peran.** Pose == gambar sumber, pose == salah satu sheet, pose juga ada di referensi umum, pose == ekspresi.
   - Mitigasi: aturan di `plan_inputs`: pose/ekspresi sama dengan sumber → 400 ("pose sudah sama dengan gambar sumber"); sama dengan referensi umum → dihapus dari referensi umum; pose == ekspresi → satu gambar dengan dua peran ("Image 4 is the POSE and EXPRESSION reference"); sama dengan sheet → tetap sebagai sheet dan dipakai juga sebagai pose (satu gambar, dua peran). Tes untuk tiap kasus.
7. **(S) Rasio/ukuran output ikut gambar referensi.** Sebagian model memakai ukuran gambar input tertentu sebagai acuan bila `aspect_ratio` kosong; gambar pose potret bisa membuat hasil potret padahal sumbernya lanskap.
   - Mitigasi: bila user tidak memilih rasio dan model punya enum `aspect_ratio`, kirim rasio terdekat dengan gambar sumber. Diamati di spike; bila tidak terjadi, aturan ini tidak dipakai (YAGNI).
8. **(S) Biaya naik diam-diam.** Model berharga per token input menagih setiap gambar tambahan (batas atas estimator 2000 token per gambar); pose + ekspresi + 4 sheet = 6 gambar input.
   - Mitigasi: estimasi (setelah nomor 1) sudah menghitung tepat; inspector menampilkan "N gambar input" di samping biaya. Tidak menambah batas baru.
9. **(S) Validitas spike.** Satu karakter, satu kali per kasus, model stokastik: kesimpulan bisa kebetulan. Siapa yang menilai "identitas bocor"?
   - Mitigasi: 2 run per kasus untuk 2 model teratas (masih ≤ $1); kriteria tertulis sebelum spike (pose diikuti ya/tidak; wajah, rambut, baju, warna dari karakter ya/tidak); gambar disimpan sebagai bukti; **user** yang memberi penilaian akhir (agent hanya mencatat), konsisten dengan aturan bahwa user menguji hasil visual.
10. **(S) Model mana untuk spike belum pasti.** Nama "model Gemini image" dan "Seedream" adalah tebakan; daftar nyata datang dari katalog (`/api/catalog/image`).
    - Mitigasi: spike memilih 3 model dari katalog nyata yang `selectable` dan berbeda provider, dicatat id dan harga per gambar saat itu.
11. **(R) Referensi pose dari foto orang sungguhan.** Mengunggah foto orang lain untuk diambil posenya bisa menyentuh privasi; provider bisa menolak (moderasi).
    - Mitigasi: teks UI menyarankan pose dari preset, gambar sendiri, atau sketsa; error moderasi provider ditampilkan apa adanya (sudah lewat `OpenRouterError`). Tidak ada pemblokiran tambahan.
12. **(R) Scene dengan lebih dari satu orang.** Prompt mengasumsikan satu karakter utama; pose bisa diterapkan ke orang yang salah.
    - Mitigasi: di luar lingkup; dicatat di UI ("paling baik untuk satu karakter dalam gambar").
13. **(R) Prompt yang tersimpan jadi panjang.** `images.prompt` menyimpan prompt final berperan; Lightbox dan pencarian Library menampilkan teks teknis panjang.
    - Mitigasi tanpa migrasi: prompt user disimpan di depan, peran sesudah pemisah `\n---\n`; Lightbox menampilkan bagian sebelum pemisah dan "lihat prompt lengkap".

## Risiko
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| Identitas bocor dari gambar pose | Tinggi | Tinggi | Sketsa garis (spike A/B), preset teks sebagai jalur utama, kunci karakter |
| Pose diabaikan karena gambar sumber lebih kuat | Sedang | Sedang | Kalimat peran eksplisit (nomor 3), diuji di spike |
| Dialog konfirmasi berulang karena estimasi beda | Sedang | Tinggi (tanpa nomor 1) | `plan_inputs` bersama |
| Biaya input bertambah | Rendah | Tinggi | Estimasi tepat + jumlah gambar ditampilkan |
| Spike menyimpulkan salah | Sedang | Sedang | 2 run, kriteria tertulis, penilaian user |

## Edge case
- Hanya teks pose/ekspresi (tanpa gambar): tidak menambah gambar; prompt hanya baris "Pose:"/"Expression:".
- Kunci karakter tanpa sheet (hanya gambar source): identitas = gambar source karakter; bila itu juga gambar yang diedit, tidak ada gambar identitas tambahan.
- Gambar yang diedit adalah salah satu gambar sheet: tidak dikirim dua kali (sudah begitu di kode sekarang, dipertahankan di `plan_inputs`).
- Pose/ekspresi menunjuk gambar terhapus (soft delete) → 404 dari `get_image`.
- Model tanpa `input_references.max` → fallback 4 (perilaku lama).
- Model hanya menerima 1 input (batas 0 referensi): slot pose/ekspresi gambar dinonaktifkan di UI dengan alasan; teks tetap bisa.
- Teks pose/ekspresi kosong atau hanya spasi → diabaikan.

## Potensi bug
- Nomor gambar di prompt meleset satu (off-by-one) setelah dedupe/pemangkasan. Prompt harus dibangun **dari daftar final** hasil `plan_inputs`, bukan dari input mentah. Tes membandingkan nomor di prompt dengan posisi URL di payload.
- "Images 2-3" untuk rentang satu gambar harus jadi "Image 2"; rentang kosong tidak boleh menulis "Images 2-1".
- `EditPage` mengirim `reference_count` lama; setelah perubahan `EstimateIn` frontend harus mengirim id, atau estimasi salah lagi.
- Sketsa garis dibuat on-the-fly di memori (PIL, deterministik) saat edit, tidak disimpan sebagai gambar baru di library (menghindari sampah).

## Asumsi yang belum terbukti
- Provider mempertahankan urutan `input_references` (spike).
- Model mematuhi peran per nomor gambar (spike).
- Sketsa garis cukup untuk menyampaikan pose (spike).
- gpt-image-2 dan model lain menerima ≥ 5 gambar input dalam praktik, bukan hanya di metadata (spike dengan kunci karakter penuh + pose + ekspresi).

## Keputusan setelah grilling (perubahan pada plan)
- Tambah `plan_inputs` bersama untuk edit dan estimasi; `EstimateIn` (`image_edit`) menerima id (`source_image_id`, `character_id`, `pose_image_id`, `expression_image_id`, `reference_image_ids`).
- Kalimat peran gambar 1 diubah agar pose boleh berubah (nomor 3).
- Spike menambah A/B pose mentah vs sketsa garis, 2 run untuk 2 model teratas, kriteria tertulis, penilaian akhir oleh user.
- Ekspresi: preset teks jadi jalur utama di UI; gambar ekspresi opsional dengan peringatan.
- Batas panjang prompt diperiksa pada prompt final; prompt user maks 2000.
- Aturan dedupe peran (nomor 6) dan penanganan rentang nomor gambar (potensi bug) masuk ke tes.
- Prompt tersimpan: teks user dulu, peran setelah pemisah `\n---\n`; Lightbox menampilkan bagian user.
- Rasio otomatis dari gambar sumber hanya bila spike menunjukkan perlu.

## Riwayat
- 2026-10-20: grill pertama, temuan 1 sampai 13.
