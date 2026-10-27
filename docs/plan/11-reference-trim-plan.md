# 11 - Trim video referensi (Plan)

- Status: disetujui, diimplementasi (lihat implementation 11)
- Tanggal: 2026-10-21

## Tujuan
Permintaan user: "untuk video referensi yang dipakai harus ada fitur trim menyesuaikan panjang video yang akan di buat".

User memilih bagian video referensi (awal dan akhir) supaya panjangnya pas dengan video yang akan dibuat, dan supaya biayanya mengikuti.

## Keadaan sekarang
- Unggahan dipotong otomatis dari detik 0 ke `MAX_REFERENCE_SECONDS` (10 dtk) oleh `media.prepare_reference_video`. User tidak bisa memilih bagian lain.
- Referensi dari klip library dipakai apa adanya. Bila klip > 10 dtk, `Motion._check_ref` menolaknya dengan pesan "unggah ulang agar dipotong otomatis", padahal unggah ulang butuh hosting publik.
- Biaya mengikuti panjang referensi: FLUX Edit dan Aleph = tarif/dtk × panjang video sumber (`video_input_seconds`); Seedance membayar durasi keluaran + panjang video input.
- Panjang keluaran: mode `flux_edit` dan `anchor_edit` = panjang referensi. Mode `reference` (Seedance) = durasi yang dipilih user, tidak harus sama dengan referensi.
- Video referensi yang berasal dari klip library memakai URL bertanda tangan OpenRouter milik klip itu. Video hasil potong adalah berkas baru, jadi harus disajikan lewat hosting publik (tunnel atau S3).

## Ruang lingkup
Termasuk:
- Endpoint `POST /api/references/{id}/trim` dengan `{start, end}` (detik) yang menghasilkan referensi baru dari bagian itu. Referensi asal tidak berubah.
- Panel trim di halaman Tiru Gerakan: penggeser awal dan akhir di atas pratinjau yang berputar hanya di rentang terpilih, panjang hasil, perkiraan biaya yang ikut berubah, dan tombol "Potong".
- Di mode "Animasikan gambar": tombol "Samakan dengan durasi video (N dtk)" yang mengatur rentang sesuai durasi yang dipilih.
- Unggahan tidak lagi otomatis dipotong dari detik 0 bila lebih panjang dari batas; videonya disimpan utuh (dinormalisasi) sampai batas unggah, lalu user memilih rentangnya. Batas panjang berlaku pada hasil potong, bukan pada sumber.

Tidak termasuk:
- Pemotongan frame-akurat berbasis timeline dengan thumbnail per frame. Cukup penggeser dan pratinjau.
- Menggabungkan beberapa bagian atau mengubah kecepatan.
- Menghapus berkas referensi lama dari disk (sama seperti sekarang).

## Desain
- `media.prepare_reference_video(src, out, max_seconds, start=0.0)` ditambah `-ss start` sebelum `-i`, dan `-t` sesuai panjang. Normalisasi (h264, aac, skala piksel) tetap sama sehingga hasil potong lolos syarat Seedance (≥ 407.696 piksel).
- `Motion.trim(ref_id, start, end, ws)`:
  1. Validasi: `0 <= start < end <= duration_sumber`, panjang `>= 1` dtk dan `<= MAX_REFERENCE_SECONDS`.
  2. Sumber berkas: `ref["path"]` untuk unggahan; untuk referensi dari klip, berkas klip (lewat `get_clip(source_clip_id)`).
  3. Hasil: berkas baru + baris `refs` baru dengan `source_clip_id = NULL`, supaya disajikan lewat hosting publik, bukan URL klip.
  4. Bila hosting publik tidak ada (`NoPublicMedia`) dan sumbernya klip library: ditolak 501 dengan penjelasan sebelum memproses.
- Unggahan: simpan utuh sampai `MAX_VIDEO_UPLOAD_MB` (200 MB) dan durasi sumber dibatasi `MAX_SOURCE_SECONDS` (bawaan 120 dtk) supaya trim tidak jadi alasan unggahan besar. `Reference.source_duration` ikut dikembalikan.
- `_check_ref` tetap menolak referensi yang lebih panjang dari batas, tetapi pesannya menyuruh memotong dengan panel trim.
- Frontend: komponen `TrimPanel` di `pages/Motion.tsx`; dua `<input type=range>` (awal, akhir) dengan langkah 0,1 dtk; pemutaran di-loop dalam rentang lewat `timeupdate`; setelah "Potong", referensi aktif diganti dengan yang baru dan estimasi dihitung ulang otomatis (id berubah).

## Risiko awal (bahan grill)
- **Hasil potong butuh hosting publik**, jadi pengguna tanpa tunnel/S3 tidak bisa memotong klip library. Harus jelas di UI.
- Setiap "Potong" membuat berkas baru yang tidak pernah dihapus (sama seperti referensi sekarang). Disk bertambah; perlu batas jumlah atau pembersihan.
- Pemotongan dengan `-ss` sebelum `-i` bisa meleset di keyframe; karena di-encode ulang, akurasi cukup, tapi perlu dites.
- Video tanpa audio, rotasi, atau fps variabel.
- Pengguna memotong lalu mengganti mode atau durasi: rentang yang dipilih bisa tidak cocok lagi dengan durasi Seedance.

## Langkah kerja
1. Grill plan ini.
2. `media`, `Motion.trim`, endpoint, penyesuaian unggahan, dan test (rentang valid dan tidak valid, panjang hasil sesuai, lintas workspace 404, klip library tanpa hosting → 501, biaya estimasi turun setelah dipotong).
3. Frontend: `TrimPanel` + tombol "Samakan dengan durasi".
4. Dokumen implementation 11. Uji frontend dilakukan manual oleh user.

## Kriteria selesai
- `make test` hijau dengan test baru; build frontend hijau.
- Hasil potong berdurasi sesuai pilihan (selisih ≤ 0,2 dtk) dan estimasi biaya turun sebanding.
- Daftar alur uji manual untuk user ada di implementation 11.

## Pertanyaan terbuka
1. Batas sumber unggahan 120 dtk (lalu dipotong ke ≤ 10 dtk) cukup, atau perlu lebih panjang?
2. Setuju trim klip library hanya aktif bila hosting publik tersedia (tunnel/S3)?

## Riwayat
- 2026-10-21: draft awal.
- 2026-10-21: user menyetujui ("ok") kedua pertanyaan terbuka. Setelah grill: sumber trim selalu `ref["path"]`, `health.max_reference_seconds` ditambah. Diimplementasi; uji frontend menunggu user.
