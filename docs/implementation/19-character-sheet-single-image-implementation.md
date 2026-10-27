# Implementasi 19 — Lembar karakter 1 gambar, beberapa sudut

**Diubah**
- `backend/app/service.py`: `SHEET_VIEWS` (4 prompt) diganti `SHEET_PROMPT` tunggal: satu baris, 4 panel berdampingan (depan, tiga-perempat, samping, belakang), seluruh badan, latar abu polos, wajah/pakaian identik, tanpa teks/label/border panel. `generate_sheet` = 1 panggilan `_run_edit`, label `sheet`. `estimate_sheet(model, aspect_ratio, quality)` = 1 gambar. `_sheet_options`: rasio bawaan 16:9 bila user tidak memilih DAN model mendukungnya (`scenes._aspect_option`).
- `backend/app/main.py`: estimasi `character_sheet` memakai `estimate_sheet` baru.
- `frontend/src/pages/Characters.tsx`: teks tombol "(1 gambar, 4 sudut)".
- `backend/tests/test_characters.py`: tes lama (4 gambar) ditulis ulang; ditambah tes rasio lebar; tes batas per-job disesuaikan (batas tes 0,01 karena biaya lembar kini 0,02).

**Tidak berubah**: karakter lama dengan 4 gambar terpisah tetap valid; `has_sheet` (≥2 gambar) tetap benar; Storyboard v2 tetap memakai gambar sumber/tampilan.

**Temuan grill**: #1-2 prompt eksplisit, penilaian oleh user (tak ada validasi otomatis); #3 rasio hanya bila didukung; #5 tes ditulis ulang; #7 estimasi 1 gambar, konfirmasi basi tetap ditolak.

**Hasil tes (dijalankan)**: `make test` → backend 378 lulus (termasuk: satu panggilan ke penyedia, semua sudut ada di prompt, 409 tanpa konfirmasi, estimasi $0,02). `npm run build` hijau.

**Belum terbukti**: kualitas gambar nyata (apakah model menggambar 4 panel rapi, tanpa teks) belum diuji berbayar.

**Diuji manual oleh user**: Karakter → "Buat character sheet (1 gambar, 4 sudut)" → dialog biaya menunjukkan 1 gambar → hasil: satu gambar lebar berisi 4 sudut; muncul di library bertipe Sheet; badge "tanpa lembar tampilan" hilang di langkah Pemeran.
