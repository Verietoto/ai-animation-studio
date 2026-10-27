# 16 - Karakter dari prompt, referensi opsional (Grill)

Plan terkait: `docs/plan/16-character-from-prompt-plan.md`
Tanggal: 2026-10-26. Sumber: `service.py` (`create_character`, `_validate_image_params`, `_store_edit_results`), `scenes.py` (`location_image`, `_aspect_option`), `lightbox.tsx`, `components.tsx` (`AssetStrip`), `Characters.tsx`, `StepCast.tsx`; katalog nyata `GET /images/models` + endpoint harga (gratis, 61 model).

User menjawab "oke" atas pilihan bawaan plan (satu gambar per klik, referensi dipakai apa adanya, perbaikan langkah 1 ikut, spike ≤ $0.15) lalu "oke lanjut develop".

## Temuan
1. **Harga nyata:** Seedream 5 Flash (bawaan) **$0.018/gambar**; Qwen Image 3 $0.03; Flux 2 Pro $0.03; Recraft v4 $0.04. Klaim "$0.02–0.04" di jawaban saya sebelumnya benar untuk model-model ini. Beberapa model memakai harga berbasis token (angka `3e-05` per satuan di katalog), jadi estimasi harus tetap dari mesin estimasi yang ada, bukan tabel ini.
2. **Rasio 3:4 didukung hampir semua model** (Seedream, GPT-Image, Gemini, Flux, Qwen); `meta/muse-image` tidak mengirim daftar rasio. `Scenes._aspect_option` sudah mengirim rasio hanya bila ada di daftar; dipakai ulang.
3. **`_validate_image_params` memakai `image_models()` yang membuang model teks-saja** (hanya `recraft-v4.1-flash` dari 61). Memilih model itu memberi galat 400 yang jelas. Perilaku sama dengan gambar latar; diterima, tidak diubah.
4. **Nama karakter sebaiknya tidak masuk prompt.** Model teks-ke-gambar kadang menggambar teks/label dari nama. Prompt potret hanya memakai deskripsi; `POST /api/characters/portrait` tidak menerima nama.
5. **`lightbox.tsx` memetakan label dari `Img.kind`** (objek berkunci); menambah "portrait" ke union tanpa menambah label gagal di tsc. Label "Potret" ditambah.
6. **`_store_edit_results` melempar 422 bila model tidak mengembalikan gambar** dan tidak menulis baris biaya; sama untuk penolakan penyedia (galat 400/502 dari `generate_image`). Tidak ada biaya palsu tercatat.
7. **Tidak ada idempotensi untuk gambar** (tabel `images` tak punya kunci idempotensi): dua klik cepat membuat dua gambar berbayar. Mitigasi di UI: tombol dikunci selama dialog/permintaan berjalan; tiap klik tetap lewat dialog konfirmasi.
8. **Pembuatan gambar menahan `Studio._lock` selama panggilan model** (±10–30 dtk), sama dengan gambar latar dan keyframe. Pola lama, diterima.

## Lubang pada plan
1. "Jumlah potret yang belum dipakai ditampilkan": potret yang belum dipakai = gambar `kind = portrait` yang bukan `source_image_id` karakter mana pun; dihitung di klien dari daftar gambar dan karakter (tanpa endpoint baru).
2. `CharacterCreator` dipakai di dua tempat dengan sumber `selected` berbeda (halaman Karakter berbagi pilihan gambar dengan halaman lain; Langkah 1 berdiri sendiri). Komponen menerima `selected/setSelected` opsional dan memakai state sendiri bila tidak diberikan.
3. Karakter baru dari Langkah 1 harus masuk episode: setelah `POST /api/characters`, panggil `PUT /films/{id}/cast` dengan daftar lama + id baru. Bila nama bentrok dengan karakter lain di episode, galat 422 dari server ditampilkan dan karakter tetap ada di workspace (tidak masuk episode).
4. Deskripsi karakter lama yang berbunyi "seperti di foto" tidak berpengaruh pada potret (teks-ke-gambar), tetapi tetap bisa mengganggu FLUX Video Edit (temuan plan 09). Potret hanya memakai kolom deskripsi apa adanya; tidak ada penyaringan kata.

## Risiko
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| Klik ganda → dua gambar berbayar | Biaya dobel kecil ($0.018) | Sedang | Tombol dikunci selama berjalan; dialog konfirmasi per klik. |
| Potret tidak bersih (latar ramai, terpotong, banyak orang) | Karakter jelek jadi acuan | Sedang | Prompt eksplisit; user memilih dari hasil dan bisa klik lagi; spike menilai prompt. |
| Penolakan moderasi penyedia | Galat | Sedang | `friendlyError` yang ada; tidak ada baris biaya. |
| Gaya tidak disebut → hasil foto-realistik → video Seedance ditolak | Kejutan di alur video | Sedang | Petunjuk di bawah kolom deskripsi: tulis gayanya (kartun/anime/3D/realistis). |
| Gambar potret menumpuk di library | Kekacauan | Sedang | Hitungan "N potret belum dipakai" + hapus massal yang sudah ada. |
| Nama/deskripsi memuat `[ ]` | Mention rusak | Rendah | `create_character` sudah menolak `[ ]` pada nama; deskripsi tidak dipakai di mention. |

## Edge case
- Deskripsi kosong atau spasi saja: 422 sebelum biaya; tombol buat nonaktif.
- Deskripsi > 2000: 422 (sama batas karakter). Di prompt dipotong 800 karakter agar prompt akhir pendek.
- Model tidak dikenal / teks-saja: 400 dari `_validate_image_params` sebelum biaya.
- Workspace lain: gambar disimpan di workspace permintaan; karakter dari gambar workspace lain tetap 404 lewat `create_character` yang ada.
- Pilih gambar potret lalu ganti ke referensi unggahan: pilihan terakhir yang dipakai; potret tetap di library.

## Potensi bug
1. Union `Img.kind` di `api.ts` dipakai di `lightbox.tsx`; label wajib ditambah (tsc akan menangkap).
2. `EstimateIn` perlu field `description`; tanpa itu estimasi `character_portrait` tidak bisa memvalidasi deskripsi.
3. Estimasi memakai `n_inputs=0, n_outputs=1` agar sama dengan pembuatan (satu sumber lewat `portrait_plan`).

## Asumsi yang belum terbukti
- Prompt potret menghasilkan gambar bersih dan konsisten untuk deskripsi kartun maupun foto-realistik. Diuji spike (≤ $0.15).
- Satu potret cukup sebagai acuan wajah untuk lembar tampilan. Dinilai user lewat pemakaian.

## Keputusan setelah grilling (perubahan pada plan)
- Endpoint hanya menerima `description` dan `model` (+ konfirmasi biaya); nama tidak dikirim ke model.
- Prompt memotong deskripsi 800 karakter; rasio 3:4 bila didukung.
- Hitungan potret belum terpakai dihitung di klien.
- `CharacterCreator` menerima `selected/setSelected` opsional.
- Karakter baru dari Langkah 1 otomatis dimasukkan ke episode.
- Tombol dikunci selama permintaan; tidak ada idempotensi server (dicatat).
- Spike berbayar (≤ $0.15) dijalankan setelah backend siap, dengan Seedream 5 Flash saja bila hasil sudah baik; model kedua hanya bila hasil pertama jelek.

## Riwayat
- 2026-10-26: grill awal.
