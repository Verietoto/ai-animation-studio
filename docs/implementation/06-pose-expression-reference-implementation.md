# 06 - Referensi Pose & Ekspresi di Edit Foto (Implementation)

Plan: `docs/plan/06-pose-expression-reference-plan.md` (termasuk Revisi 1: section terpisah)
Grill: `docs/grill/06-pose-expression-reference-grill.md`
Spike: `docs/implementation/06-pose-expression-reference-spike.md` (biaya $0,3314)

Status: **kode selesai; `make test` 126 lulus dan `npm run build` hijau; uji frontend menunggu user** (aturan `CLAUDE.md`).

## Yang dibangun
- **`backend/app/editprompt.py`** (modul murni): `plan_inputs` (urutan: sumber, identitas/sheet, pose, ekspresi, referensi lain; dedupe; pemangkasan hanya sheet menurut prioritas front > three_quarter > side > full_body > source > custom; ditolak bila pose/ekspresi/referensi user sendiri melewati batas model), `build_prompt` (prompt berperan; nomor dari daftar final), `make_pose_sketch` (PIL, sketsa garis), `clean_text`.
- **`Studio.plan_edit`** = satu sumber kebenaran daftar gambar input. `edit_image` dan `POST /api/estimate` (`image_edit` dengan `source_image_id`) memakainya, jadi jumlah gambar di estimasi = jumlah yang dikirim (respons estimasi membawa `inputs`). Klien lama yang hanya mengirim `reference_count` tetap jalan.
- **API**: `EditIn` dan `EstimateIn` menerima `pose_image_id`, `pose_mode` (`sketch`|`original`, default `sketch`), `expression_image_id`, `pose_text`, `expression_text` (maks 200 karakter); `GET /api/images/{id}/sketch` (pratinjau byte yang sama dengan yang dikirim).
- **Prompt tersimpan**: teks user dulu, lalu `\n---\n` dan peran gambar; Lightbox menampilkan teks user dan melipat "Instruksi referensi"; Library memakai bagian user untuk caption dan pencarian.
- **UI Edit Foto**: section terpisah **Pose** (strip gambar + unggah, toggle sketsa/asli dengan pratinjau sketsa, preset, teks), **Ekspresi** (preset + teks sebagai jalur utama; gambar opsional dalam `<details>` dengan peringatan), **Referensi lain** (multi-pilih, maks sisa slot dari batas model, bukan angka tetap 4). Baris "N gambar input dikirim (batas model M)" di bagian Biaya. Satu gambar tidak muncul di dua section sekaligus.
- **Perbaikan bug**: kunci karakter tidak lagi membuang referensi user diam-diam (dulu `[:4]` setelah sheet).

## File yang diubah
Backend: baru `editprompt.py`; diubah `service.py` (`edit_image`, `plan_edit`, `_plan_urls`, `_run_edit`), `main.py` (`EditIn`, `EstimateIn`, estimasi, endpoint sketsa). Tes: baru `test_pose_expression.py`; diubah `conftest.py` (`ConfirmingClient` mengirim id seperti UI baru). Frontend: `pages/EditPage.tsx` (ditulis ulang), `components.tsx` (`paste` pada `AssetStrip`), `api.ts`, `prompts.ts` (`POSE_PRESETS`, `EXPRESSION_PRESETS`), `lightbox.tsx`, `pages/Library.tsx`, `styles.css`. Skrip: `scripts/spike_pose.py`; bukti `docs/spike/06-*.jpg`.

## Penyimpangan dari plan (dan alasannya)
- Batas panjang: yang dicek adalah prompt akhir (maks 4000), batas prompt user tetap 4000 (plan/grill: turun ke 2000). Alasan: menurunkan batas mengubah perilaku lama tanpa bukti kebutuhan; pesan galat jelas bila prompt akhir terlalu panjang.
- Strip pose/ekspresi/referensi **menyaring** gambar yang sudah dipakai peran lain, bukan menandainya di strip lain.
- Endpoint `GET /api/images/{id}/sketch` tidak ada di plan; ditambah untuk pratinjau sketsa yang persis sama dengan yang dikirim (tanpa menduplikasi algoritma di JavaScript).
- Aturan dedupe: referensi umum yang sama dengan gambar pose/ekspresi dibuang (grill 6); pose yang sama dengan salah satu gambar sheet dikirim dua kali (mentah sebagai identitas, sketsa sebagai pose) karena itu dua input berbeda.
- Rasio otomatis dari gambar sumber (grill 7) **tidak** dibuat: spike tidak menunjukkan kebutuhan.
- Pesan galat batas gambar memakai kata "maksimal" supaya tes lama (`test_edit_rejects_too_many_input_images`) tetap berlaku tanpa diubah.

## Dampak perilaku yang perlu diketahui
- Dengan kunci karakter, semua gambar sheet (sampai batas model) kini ikut terkirim; sebelumnya total referensi dipotong 4. Pada model berharga per-token ini menambah biaya input; estimasi dan dialog konfirmasi sudah menghitung jumlah yang benar.
- Kalimat kunci karakter lama ("Keep the character consistent…") diganti prompt berperan yang memuat nama dan deskripsi karakter.
- Edit tanpa karakter/pose/ekspresi: prompt dan perilaku tidak berubah.

## Temuan grill yang sudah ditangani
1 `plan_edit` bersama (tes `test_estimate_counts_same_inputs_as_generate`); 2 sketsa garis default + preset teks sebagai jalur ekspresi (UI); 3 kalimat peran gambar 1 mengizinkan pose berubah; 4 urutan payload dites (`test_payload_order_matches_prompt_numbers`, warna piksel per posisi); 5 panjang prompt akhir (`test_final_prompt_length_is_checked`); 6 dedupe (`test_edited_image_is_never_sent_twice...`); 8 hitungan input tampil di UI; 13 prompt tersimpan "teks user + `---` + peran". Potensi bug: rentang nomor ("Images 2-3" / "Image 2" / tanpa "2-1") dan prompt dibangun dari daftar final (dites).

## Pengujian (perintah dan hasil nyata)
- `make test` → **126 passed** (108 sebelumnya; tambahan 18 di `test_pose_expression.py`: urutan, dedupe, pemangkasan, penolakan sebelum provider dipanggil, regresi `[:4]`, prompt, sketsa, endpoint sketsa, validasi, panjang, estimasi = generate).
- `cd frontend && npm run build` → hijau.
- Spike nyata (API asli, $0,3314) sebelum implementasi: lihat dokumen spike.
- **Diuji manual oleh user (belum dilakukan)**:
  1. Edit Foto: pilih sumber, buka section **Pose**, pilih gambar pose, lihat pratinjau sketsa, ganti ke "Gambar asli", hapus; coba preset pose dan teks bebas.
  2. Section **Ekspresi**: preset senyum/tertawa; buka "Pakai gambar sebagai referensi ekspresi" dan pastikan peringatan tampil.
  3. **Referensi lain**: pilih beberapa; angka n/maks berubah saat pose/ekspresi gambar dipilih; ganti model dengan batas gambar kecil dan lihat maks menyusut.
  4. Kunci karakter + pose + ekspresi: baris "N gambar input dikirim", dialog biaya sama dengan angka estimasi, hasil mempertahankan wajah/baju karakter.
  5. Lightbox hasil: teks prompt bersih + "Instruksi referensi" terlipat; Library menampilkan caption tanpa teks teknis.
  6. Memilih gambar sumber yang sama dengan gambar pose: pose dilepas otomatis, tidak ada galat 400.
  7. Tempel (Cmd+V) gambar: hanya satu gambar baru, masuk ke sumber.

## Masalah tersisa
- Estimator: FLUX klein ditagih $0,009 vs "eksak" $0,008 (temuan spike); batas atas token gpt-image-2 5-7× biaya nyata. Belum diperbaiki.
- Penilaian wajah/identitas akhir ada di user (spike hanya pengamatan kasar).
- Tidak diuji: scene dengan beberapa orang, 5+ gambar input pada provider asli, pose yang butuh properti.
- Sketsa dihitung ulang tiap edit (murah); tidak di-cache.

## Riwayat
- 2026-10-20: implementasi selesai; menunggu uji manual user.
