# 02 - Image Edit (Implementation)

Plan: `docs/plan/02-image-edit-plan.md`
Grill: `docs/grill/02-image-edit-grill.md`

## Yang dibangun
- `POST /api/images/{id}/edit` (prompt, model, hingga 4 gambar referensi) → versi baru `kind=edit` dengan `parent_image_id`.
- Adapter tunggal `OpenRouterClient.edit_image` lewat `POST /api/v1/images` dengan `input_references` (awalnya Chat Completions; diganti 2026-10-19 setelah uji nyata).
- Halaman "Edit Foto": pilih/unggah gambar, prompt, model (daftar dari `/models?output_modalities=image`, bisa diketik), referensi tambahan, tampilan sebelum/sesudah, "Edit lagi dari ini", "Jadikan video".

## File yang diubah
`backend/app/{openrouter,service,main}.py`, `frontend/src/pages/EditPage.tsx`, `frontend/src/components.tsx`.

## Penyimpangan dari plan
- Tabel `images` dipakai bersama gambar upload dan frame hasil extend (kolom `kind`).
- Model default di UI `openai/gpt-image-2` (bisa diganti); tidak ada daftar rekomendasi bawaan di UI.

## Temuan grill yang sudah ditangani
| Temuan | Penanganan | Bukti |
|---|---|---|
| Balasan teks tanpa gambar | Error 422 dengan teks balasan; tidak membuat versi baru | `test_edit_text_only_reply_is_error_not_new_version` |
| Hasil data URL berbahaya/besar | Batas ukuran + validasi Pillow sebelum simpan | kode `from_data_url`, `normalize_image` |
| Gambar asli hilang | Setiap edit versi baru; asli tetap | `test_edit_image` |
| Beberapa gambar di respons | Semua disimpan sebagai varian | kode (belum ada tes khusus) |
| Hasil edit jadi input video | Tanpa upload ulang | `test_edit_image` (membuat klip dari hasil edit) |
| Model hanya-teks di daftar | Disaring | `test_image_models_filters_text_only` |

Belum: peringatan edit berantai hanya berupa teks statis (tidak menghitung jumlah edit); validasi/crop rasio saat "jadikan video" belum ada; biaya model mahal tidak butuh konfirmasi eksplisit selain batas harian.

## Pengujian
Termasuk dalam 21 tes backend dan uji UI end-to-end di `01-video-studio-implementation.md`. Edit nyata ke OpenRouter belum diuji (`scripts/smoke_openrouter.py --edit openai/gpt-image-2`).

## Uji nyata (2026-10-19)
`scripts/smoke_openrouter.py --edit openai/gpt-image-2` dengan key sungguhan: **berhasil** setelah mengganti rute. Percobaan pertama lewat `/chat/completions` ditolak (404: model gambar harus lewat `/images`), jadi asumsi awal salah dan sudah dikoreksi. Hasil: 1 gambar kembali, `usage.cost` = $0,0151 (quality=low, gambar masukan 512x512). Biaya nyata ~2,5x perkiraan awal di plan ($0,006), jadi angka itu perlu dibaca sebagai batas bawah.
Daftar model: `GET /images/models` (60 model menerima input gambar).

## Masalah tersisa
Penyaringan hasil dengan lebih dari satu gambar (`n>1`) dan model selain gpt-image-2 belum diuji nyata.

## Revisi 2026-10-19: resolusi, rasio, kualitas
- Backend: `EditIn` menerima `resolution`, `aspect_ratio`, `quality`; `Studio._validate_image_params` memeriksa terhadap `supported_parameters` model (parameter tak didukung, nilai enum di luar daftar, jumlah gambar input melebihi `input_references.max`) dan menolak 400 sebelum memanggil provider. Daftar model gambar di-cache 5 menit (`Studio.image_models`).
- Frontend: Edit Foto menampilkan dropdown Resolusi/Rasio/Kualitas hanya bila model mendukungnya.
- Tes: 27 lulus (+4: opsi diteruskan ke provider, opsi tak didukung ditolak tanpa panggilan, terlalu banyak gambar input, model tak dikenal).
- **Uji nyata:** `openai/gpt-image-2` lewat aplikasi: `resolution=2K` ditolak lokal (model tak punya parameter itu); `aspect_ratio=16:9` + `quality=low` diterima, hasil **1536x864**, biaya **$0,0119**.
- Belum: estimasi biaya yang ikut berubah menurut resolusi/rasio (plan 04); `n>1`.

## Riwayat
- 2026-10-16: iterasi 1.
- 2026-10-19: revisi resolusi/rasio/kualitas (lihat di atas).
- 2026-10-19: daftar model gambar diverifikasi nyata (public); edit nyata via `/chat/completions` masih menunggu key.
