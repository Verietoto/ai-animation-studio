# 06 - Referensi Pose & Ekspresi di Edit Foto (Plan)

- Status: disetujui user ("go", 2026-10-20), sudah digrill dan di-spike, kode selesai (lihat `docs/implementation/06-pose-expression-reference-implementation.md`); uji frontend menunggu user
- Tanggal: 2026-10-20
- Asal: permintaan user "untuk edit gambar buat adjustment plan agar bisa menambahkan referensi pose dan ekspresi tanpa mengubah karakter".
- Terkait: plan 02 (edit foto), plan 05 (UI Studio, `ModelPicker`, `MultiAssetStrip`), kunci karakter (commit `012229d`).

## Tujuan
Di Edit Foto, user bisa memberi **referensi pose** dan **referensi ekspresi** (gambar atau preset teks) sehingga hasilnya mengikuti pose/ekspresi itu, sementara **identitas karakter** (wajah, rambut, pakaian, warna) tetap dari gambar sumber dan/atau karakter yang dikunci, bukan dari orang di gambar referensi.

## Kondisi sekarang (dicek di kode)
- `EditIn` hanya punya `reference_image_ids` (tanpa peran) + `character_id`. Model menerima gambar tanpa tahu mana yang identitas, mana yang pose.
- `edit_image` (`backend/app/service.py`): sheet karakter dimasukkan lebih dulu lalu `reference_ids[:4]`. Sheet bisa berisi 4-5 gambar (source, front, side, three_quarter, full_body), jadi **referensi user terpotong diam-diam** saat kunci karakter aktif. Ini bug yang harus ditutup oleh fitur ini.
- Prompt kunci karakter hanya menambah satu kalimat "Keep the character consistent with the reference images: …" tanpa menyebut nomor gambar.
- Batas 4 adalah angka aplikasi; batas model ada di `supported_parameters.input_references.max` (gpt-image-2: 16) dan sudah divalidasi `_validate_image_params`.

## Ruang lingkup (termasuk yang TIDAK dikerjakan)
Termasuk:
- Slot **Pose** dan **Ekspresi** di Edit Foto, masing-masing bisa diisi: (a) gambar dari library/unggahan, atau (b) preset teks (mis. "berdiri tangan di pinggang", "tersenyum lebar"), atau (c) teks bebas pendek.
- Prompt berperan per gambar (bahasa Inggris, bernomor sesuai urutan gambar yang benar-benar dikirim).
- Urutan dan pemangkasan referensi yang tidak lagi membuang referensi user; batas dari model, bukan angka tetap.
- Spike berbiaya kecil dengan API asli untuk memilih model default dan mengukur "kebocoran identitas" dari gambar pose/ekspresi.

Tidak termasuk:
- Ekstraksi kerangka pose (OpenPose/MediaPipe) atau crop wajah otomatis: butuh dependency ML berat. Dipertimbangkan lagi bila spike menunjukkan kebocoran identitas tinggi.
- Pose/ekspresi untuk Gambar→Video, Extend, Tiru Gerakan (plan 03), dan character sheet.
- Cek konsistensi otomatis dengan model vision (eksperimental di plan 03).

## Desain / pendekatan

### API
- `EditIn` ditambah: `pose_image_id`, `expression_image_id` (opsional, id gambar), `pose_text`, `expression_text` (opsional, maks 200 karakter; preset atau teks bebas). `reference_image_ids` tetap (referensi umum: gaya, properti) supaya klien lama tidak rusak.
- `POST /api/estimate` (`image_edit`) menghitung `reference_count` termasuk gambar pose/ekspresi dan sheet; frontend mengirim angka yang sama, server tetap menghitung ulang saat generate (plan 04).

### Urutan gambar dan pemangkasan
Urutan input yang dikirim ke model (nomor ini dipakai di prompt):
1. Gambar sumber (scene yang diedit).
2. Gambar identitas karakter (sheet), bila kunci karakter aktif.
3. Referensi pose.
4. Referensi ekspresi.
5. Referensi umum dari user.

Batas = `input_references.max` model (dikurangi 1 untuk gambar sumber; fallback 4 bila model tidak mengumumkan). Bila lewat batas, yang dipangkas **hanya sheet karakter**, dengan prioritas front > three_quarter > side > full_body > source. Pose, ekspresi, dan referensi user tidak pernah dipangkas diam-diam: bila tetap lewat batas, request ditolak dengan pesan jelas sebelum memanggil provider.

### Prompt berperan
Fungsi murni `build_edit_prompt(user_prompt, roles, character)` di modul baru `backend/app/editprompt.py`, contoh hasil:
```
Image 1 is the scene to edit.
Images 2-3 show the character's identity (Rina: short black bob, red jacket). Keep face, hair, skin tone, body shape, outfit and colors exactly as in these images and image 1.
Image 4 is a POSE reference only: copy the body pose, limb positions and gesture. Ignore the person's identity, face, clothing, colors and style in image 4.
Image 5 is an EXPRESSION reference only: copy the facial expression. Ignore everything else in image 5.
Pose: hands on hips. Expression: big open smile.
User request: <prompt user>
Do not change the character's identity.
```
Tanpa kunci karakter, identitas diambil dari gambar 1. Teks pose/ekspresi tanpa gambar hanya menambah baris "Pose:"/"Expression:".

### Frontend (Edit Foto)
- Section baru **Pose & ekspresi** di inspector: dua slot berdampingan. Tiap slot menampilkan thumbnail terpilih atau teks, tombol pilih dari strip aset (bisa unggah/seret/tempel seperti strip lain), chip preset, input teks pendek, dan tombol hapus.
- Preset di `frontend/src/prompts.ts` (berdampingan dengan preset kamera/gaya): pose (berdiri santai, tangan di pinggang, duduk, berlari, melambai, menunjuk, tangan bersilang) dan ekspresi (netral, senyum, tertawa, sedih, marah, terkejut, mengedip).
- Catatan di UI: "Gambar pose/ekspresi bisa ikut membawa wajah atau baju orang di gambar itu; pakai kunci karakter untuk hasil paling konsisten."
- Hitungan referensi di estimasi = sheet + pose + ekspresi + referensi umum; strip referensi umum menampilkan sisa slot sesuai batas model.

### Data
Tidak ada perubahan skema. Prompt final (dengan peran) sudah tersimpan di `images.prompt`, sehingga Lightbox menampilkan bagaimana gambar dibuat.

## Langkah kerja
1. Grill plan ini (`docs/grill/06-pose-expression-reference-grill.md`).
2. **Spike** dengan API asli (butuh persetujuan biaya, perkiraan ≤ $1): 1 foto karakter + kunci karakter, 3 model gambar yang menerima input gambar (mis. gpt-image-2, model Gemini image, Seedream), masing-masing: pose via gambar orang lain, ekspresi via gambar orang lain, pose + ekspresi via teks. Hasil dan penilaian (pose diikuti? identitas bocor?) dicatat di `docs/implementation/06-pose-expression-reference-spike.md` dengan gambar bukti. Model default dan teks peringatan ditentukan dari sini.
3. Backend: `editprompt.py` + urutan/pemangkasan + field baru di `EditIn` dan `/api/estimate`; perbaiki bug pemangkasan.
4. Frontend: slot Pose & Ekspresi, preset, hitungan referensi.
5. Dokumen implementation.

## Kriteria selesai
- Tes backend (`backend/tests/test_pose_expression.py`):
  - urutan URL yang dikirim ke provider sama dengan nomor gambar di prompt (sumber=1, sheet, pose, ekspresi, umum);
  - kunci karakter + referensi user tidak lagi membuang referensi user (regresi bug `[:4]`);
  - batas dari `input_references.max`; hanya sheet yang dipangkas, urutan prioritas sesuai plan; lewat batas → 400 sebelum provider dipanggil;
  - pose/ekspresi berupa teks saja tidak menambah gambar; teks > 200 karakter ditolak;
  - id gambar pose/ekspresi yang tidak ada atau sudah dihapus → 404;
  - estimasi `image_edit` menghitung gambar pose/ekspresi/sheet sama seperti saat generate.
- `make test` dan `npm run build` hijau.
- Spike tercatat dengan hasil nyata dan biaya nyata.
- Uji frontend dilakukan user (sesuai `CLAUDE.md`); daftar alur di dokumen implementation.

## Pertanyaan terbuka
- Bila spike menunjukkan identitas sering bocor dari gambar pose, apakah perlu ekstraksi kerangka pose (dependency ML, mis. MediaPipe) sebagai plan lanjutan?
- Perlu juga di character sheet (mis. "buat pose X untuk karakter ini" lalu simpan ke karakter)? Saat ini di luar lingkup.

## Revisi 1 (2026-10-20): struktur UI "Referensi" di Edit Foto
Permintaan user: "harusnya referensi tambahan ada section khusus pose dan ekspresi". Menggantikan sub-bagian "Frontend (Edit Foto)" di atas bila bertentangan.

Bagian inspector "Referensi tambahan (n/4)" yang sekarang (satu strip campur) diganti kelompok **Referensi** berisi tiga section terpisah, masing-masing dengan judul, penjelasan satu kalimat, dan hitungan slotnya sendiri:

| Section | Isi | Peran di prompt | Default |
|---|---|---|---|
| **Pose** | satu gambar (strip aset + unggah/seret/tempel) **atau** preset pose **atau** teks; toggle "Sketsa garis (disarankan)" / "Gambar asli"; pratinjau sketsa yang akan dikirim | POSE saja, abaikan identitas | sketsa garis |
| **Ekspresi** | preset ekspresi (chip) **atau** teks; gambar opsional dengan peringatan bocor | EXPRESSION saja | preset teks |
| **Referensi lain** | strip multi-pilih seperti sekarang (gaya, properti, latar), maks sesuai sisa slot | referensi umum | kosong |

- Gambar yang sudah dipilih di satu section ditandai di strip section lain (tidak bisa jadi dua peran lewat klik; aturan dedupe server tetap berlaku, grill nomor 6).
- Di atas ketiganya satu baris ringkasan: "N gambar input dikirim (sumber + sheet X + pose + ekspresi + lain)" dan sisa slot dari batas model; dipakai juga oleh `EstimateLine`.
- Kunci karakter tetap di bagian "Model & opsi"; teks bantu di section Pose/Ekspresi: "identitas tetap dari gambar sumber dan karakter terkunci".
- Section tanpa isi tidak mengirim apa pun (tidak menambah gambar maupun baris prompt).
- Lightbox menampilkan peran yang dipakai (mis. "Pose: gambar · sketsa", "Ekspresi: senyum lebar") dari bagian setelah `---` pada prompt tersimpan.

Perubahan kriteria selesai: kecuali yang sudah ada, tes `plan_inputs` mencakup kombinasi section kosong/terisi (pose saja, ekspresi saja, keduanya, plus referensi lain) dan uji frontend dicantumkan di dokumen implementation untuk dicoba user.

## Riwayat
- 2026-10-20: revisi 1, struktur UI: section Pose, Ekspresi, dan Referensi lain terpisah (permintaan user).
- 2026-10-20: draft pertama.
- 2026-10-20: spike dijalankan dengan batas biaya $0,50 dari user (terpakai $0,3314); hasil di `docs/implementation/06-pose-expression-reference-spike.md`. Usulan penyesuaian plan dari hasil spike (menunggu persetujuan user): sketsa garis jadi default slot pose; ekspresi lewat preset teks sebagai jalur utama; tidak perlu ekstraksi kerangka pose ML; rasio otomatis tidak diperlukan; model yang disorot Seedream 5.0 flash dan gpt-image-2 low.
- 2026-10-20: setelah grill (`docs/grill/06-pose-expression-reference-grill.md`), bagian "Keputusan setelah grilling" di sana menimpa plan ini bila bertentangan. Ringkas: `plan_inputs` bersama untuk edit + estimasi (`EstimateIn` menerima id, bukan hitungan); kalimat peran gambar 1 mengizinkan pose berubah; spike menambah A/B sketsa garis vs pose mentah, 2 run, penilaian akhir oleh user; ekspresi lewat preset teks sebagai jalur utama; batas panjang dicek pada prompt final (prompt user maks 2000); aturan dedupe peran; prompt tersimpan "teks user + `---` + peran".
