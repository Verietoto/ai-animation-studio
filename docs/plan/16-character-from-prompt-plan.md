# 16 - Karakter dari prompt, referensi opsional (Plan)

- Status: draft, menunggu persetujuan
- Tanggal: 2026-10-26

## Tujuan
Permintaan user: "aku mau bisa tanpa referensi, pakai referensi kalau dikasi".

Membuat karakter tidak lagi wajib membawa gambar. Bila user memberi referensi (unggah atau pilih dari library), referensi itulah gambar karakter, seperti sekarang. Bila tidak, AI membuat gambar karakter dari nama + deskripsi (teks ke gambar), lalu user memilih hasilnya sebagai karakter.

Sekaligus melengkapi langkah 1 alur episode (plan 15) supaya karakter dan latar bisa dibuat lengkap di sana, tanpa pindah halaman.

## Keadaan sekarang (dicek 2026-10-26)
- `Studio.create_character(name, description, source_image_id)` mewajibkan gambar sumber; halaman Karakter menonaktifkan tombol sampai gambar dipilih. Seluruh alur karakter (lembar tampilan, keyframe adegan, Kunci karakter) memakai gambar itu sebagai identitas wajah dan pakaian.
- Teks ke gambar sudah ada untuk latar: `Scenes.location_image` → `client.generate_image(model, prompt, **options)` → `_store_edit_results(…, kind="location")`, dengan estimasi `estimate_image_job(model, n_inputs=0)` dan alur konfirmasi biaya plan 04.
- `Img.kind` saat ini: upload, edit, frame, sheet, keyframe, location, anchor. Tidak ada pembatasan nilai di DB.
- Langkah 1 alur episode (plan 15): "Karakter baru…" hanya membuka halaman Karakter; "Latar baru" hanya meminta nama, tanpa deskripsi dan tanpa gambar.

## Ruang lingkup
Termasuk:
- **Backend:** `POST /api/characters/portrait`: membuat **satu** gambar potret karakter dari nama + deskripsi dengan model teks-ke-gambar yang dipilih, disimpan sebagai gambar `kind = "portrait"` di library. Satu panggilan per gambar (variasi = klik lagi), supaya tidak ada permintaan panjang dan biaya selalu terlihat. Estimasi `character_portrait` lewat `/api/estimate`; konfirmasi biaya wajib seperti biasa.
- Prompt potret (modul murni): tampak depan, seluruh badan, pose netral, latar polos abu terang, cahaya merata, satu karakter, tanpa teks. Bagian deskripsi dipotong sesuai batas prompt. Rasio potret (3:4 atau terdekat) dikirim bila model mendukung.
- **Halaman Karakter:** bagian "Gambar karakter" menjadi dua jalan:
  - "Pakai referensi": unggah / pilih dari library (perilaku sekarang).
  - "Tanpa referensi": tombol **Buat gambar dari deskripsi** (model, estimasi biaya, dialog konfirmasi). Hasil muncul di strip gambar dan langsung terpilih; tombol bisa diklik lagi untuk variasi lain. Lalu "Simpan karakter" seperti biasa.
  - Nama dan deskripsi tetap wajib (deskripsi dipakai di setiap prompt dan menjadi dasar potret).
- **Langkah 1 alur episode:** panel "Karakter baru" (nama, deskripsi, referensi opsional / buat dari deskripsi, simpan) memakai komponen yang sama dengan halaman Karakter, dan karakter baru langsung masuk episode. Kartu latar mendapat kolom deskripsi, tombol "Buat gambar dari deskripsi" (komponen `LocationImagePanel` yang ada), dan pratinjau gambar.

Tidak termasuk:
- "Deskripsikan dari gambar" (vision) untuk mengisi deskripsi otomatis dari referensi.
- Merapikan referensi menjadi pose netral dengan AI (tetap bisa lewat Edit Foto).
- Beberapa gambar sekaligus dalam satu klik, gaya visual khusus (anime, 3D, dll.) di luar yang ditulis user di deskripsi, ganti nama karakter.

## Desain / pendekatan
- `characterprompt.py` atau fungsi di `sceneprompt.py`: `portrait_prompt(name, description)` murni, bersama `Studio.portrait_plan(model, ws)` yang dipakai estimasi dan pembuatan (satu sumber, pola `location_plan`).
- `Studio.create_portrait(name, description, model, ws, confirmed_cost, accept_unknown_cost)`: validasi nama/deskripsi (tanpa `[ ]`, batas panjang), `authorize`, `generate_image`, `_store_edit_results(kind="portrait")`, mengembalikan gambar. Tidak membuat karakter; karakter dibuat lewat `POST /api/characters` yang sudah ada dengan `source_image_id` gambar terpilih.
- Frontend: komponen `CharacterCreator` (form + dua jalan gambar + simpan) di `frontend/src/characters/` dipakai oleh `Characters.tsx` dan `StepCast.tsx`. `Img.kind` mendapat "portrait".
- Gambar potret yang tidak dipilih tetap di library (bisa dihapus dari sana; ada hapus massal).

## Risiko awal (bahan grill)
- Konsistensi identitas: wajah hanya dari teks. Gambar terpilih menjadi acuan; lembar tampilan diturunkan dari sana lewat model edit (sudah ada).
- Moderasi / penolakan penyedia untuk deskripsi tertentu: pesan galat ramah (`friendlyError`) dan tidak ada biaya tercatat saat ditolak.
- Biaya tumbuh diam-diam karena klik berulang: setiap klik memunculkan dialog biaya sendiri; batas harian berlaku; jumlah potret yang belum dipakai ditampilkan.
- Deskripsi panjang melebihi batas prompt, atau berisi kata "foto/gambar" yang membingungkan model teks-ke-gambar.
- Gambar hasil bukan potret yang bersih (latar ramai, banyak orang, terpotong): perlu diuji di spike kecil sebelum prompt dianggap baik.
- Gaya (kartun vs foto-realistik) menentukan jalur video berikutnya (Seedance menolak foto-realistik): deskripsi sebaiknya menyebut gaya; UI memberi petunjuk.
- Dua komponen form (Karakter, Langkah 1) harus berbagi satu logika agar tidak menyimpang.

## Langkah kerja
1. Grill plan ini.
2. Spike berbayar kecil (butuh persetujuan batas biaya; usul ≤ $0.15): 3–4 deskripsi nyata (kartun dan foto-realistik) dengan Seedream dan satu model alternatif; menilai kebersihan potret, rasio, dan penolakan.
3. Backend: prompt, `portrait_plan`/`create_portrait`, endpoint, estimasi, test (validasi, biaya, lintas workspace, jawaban kosong, penolakan penyedia, `kind`).
4. Frontend: `CharacterCreator`, perubahan halaman Karakter, panel Karakter baru dan kartu latar di langkah 1.
5. Dokumen implementation 16 dan daftar uji manual untuk user.

## Kriteria selesai
- `make test` hijau dengan test baru; `npm run build` hijau.
- Karakter bisa dibuat tanpa referensi (potret dari deskripsi → pilih → simpan) dan dengan referensi (perilaku lama tidak berubah).
- Biaya potret selalu lewat dialog konfirmasi dan tercatat; penolakan penyedia tidak meninggalkan baris biaya palsu.
- Di langkah 1, karakter dan latar baru bisa dibuat lengkap (termasuk gambar) tanpa pindah halaman.

## Pertanyaan terbuka
1. Satu gambar per klik (variasi dengan klik lagi) cukup, atau mau 2–3 variasi sekaligus (lebih mahal, permintaan lebih lama)?
2. Saat referensi diberikan, apakah dipakai apa adanya sebagai gambar karakter (usul, perilaku sekarang), atau AI merapikan dulu ke pose netral dan latar polos?
3. Perbaikan langkah 1 (panel Karakter baru dan kartu latar lengkap) ikut di plan ini seperti usul saya sebelumnya, atau dipisah?
4. Boleh spike berbayar dengan batas $0.15 untuk menguji kualitas potret?

## Riwayat
- 2026-10-26: draft awal.
- 2026-10-26: user: "oke" atas pilihan bawaan (satu gambar per klik, referensi dipakai apa adanya, perbaikan langkah 1 ikut, spike ≤ $0.15), lalu "oke lanjut grill" dan "oke lanjut develop". Setelah grill (rincian di grill 16):
  - Endpoint hanya menerima `description` + `model`; nama tidak masuk prompt (model bisa menggambar teks dari nama).
  - Harga nyata dicek: Seedream 5 Flash $0.018/gambar; rasio 3:4 didukung hampir semua model.
  - Potret belum terpakai dihitung di klien; `CharacterCreator` menerima `selected` opsional; karakter baru dari Langkah 1 otomatis masuk episode.
  - Tidak ada idempotensi server untuk gambar; tombol dikunci di UI.
