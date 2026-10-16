# 02 - Image Edit (Grill)

Plan terkait: `docs/plan/02-image-edit-plan.md`

## Lubang pada plan
1. **(T) Rute API edit belum pasti**: plan menyebut Chat Completions/Responses dengan modality image atau rute images kompatibel OpenAI, tanpa memilih. Bentuk request/respons (gambar sebagai base64 di pesan, atau URL) belum diverifikasi.
   - Mitigasi: adapter punya satu antarmuka (`edit(image, prompt, refs, model) -> bytes`); implementasi awal pakai Chat Completions modality image (didukung semua model yang tercantum) dan dibungkus supaya mudah diganti. Diuji dengan mock; smoke test nyata menyusul.
2. **(S) Model dengan satuan harga berbeda** membuat estimasi biaya sebelum kirim tidak akurat. Mitigasi: tampilkan "perkiraan" hanya bila harga bisa dihitung, sisanya "biaya diketahui setelah selesai"; catat biaya aktual bila ada.
3. **(S) Konsistensi karakter antar edit** tidak dijamin; edit berantai menurunkan kualitas (generation loss) dan bisa mengubah wajah.
   - Mitigasi: selalu simpan dan bisa kembali ke gambar asli; edit baru dari versi mana pun; peringatan setelah beberapa edit berantai.
4. **(S) Resolusi/aspect ratio keluaran bisa beda dari masukan**, padahal video butuh rasio tertentu. Mitigasi: tampilkan ukuran hasil; di langkah "jadikan video" validasi/crop/pad sesuai model.

## Risiko
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| Moderasi menolak edit (wajah orang nyata, konten sensitif) | Sedang | Sedang | Tampilkan alasan penolakan asli; jangan retry otomatis berbayar |
| Biaya per edit tak terkendali pada model mahal (Gemini ~ $0,134) | Sedang | Sedang | Model default murah; model mahal butuh pilihan eksplisit; batas biaya harian bersama plan 01 |
| Edit gambar orang nyata untuk menipu (deepfake) | Tinggi | Sedang | Peringatan penggunaan di UI; metadata asal dan prompt disimpan |
| Gambar besar memperlambat/menggagalkan request | Sedang | Sedang | Batas ukuran, downscale otomatis sebelum kirim |

## Edge case
- Model membalas teks saja tanpa gambar (Gemini/GPT bisa): tandai gagal dengan teks balasan ditampilkan, tidak dihitung sebagai versi baru.
- Respons berisi lebih dari satu gambar: ambil semua sebagai varian atau yang pertama (diputuskan: simpan semua, tampilkan sebagai varian).
- Gambar sumber transparan (PNG alpha) atau animasi (GIF): normalisasi ke RGB PNG, tolak GIF animasi.
- Prompt kosong atau sangat panjang: validasi.
- Data URL base64 sangat besar di payload: batasi ukuran sebelum encode.
- Hasil berupa data URL base64: decode aman, batasi ukuran, validasi dengan Pillow sebelum simpan.

## Potensi bug
- Memakai gambar versi lama sebagai sumber karena state UI usang: selalu kirim `parent_image_id` eksplisit.
- Orientasi EXIF diabaikan sehingga hasil terputar.
- Ekstensi file dari klien dipercaya: tentukan tipe dari isi file.

## Asumsi yang belum terbukti
- `gpt-image-2` dan model lain di tabel plan menerima gambar input lewat jalur yang dipilih.
- Satuan biaya tersedia di respons.

## Keputusan setelah grilling
- Adapter tunggal dengan antarmuka stabil; Chat Completions modality image sebagai jalur awal.
- Pembatasan ukuran, normalisasi (EXIF, mode warna), simpan semua varian, bisa kembali ke asli.
- Model default murah; model mahal eksplisit.

## Riwayat
- 2026-10-16: draft awal.
