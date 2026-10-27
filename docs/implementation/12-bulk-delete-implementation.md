# 12 - Hapus banyak sekaligus di Library (Implementation)

Plan: `docs/plan/12-bulk-delete-plan.md` · Grill: `docs/grill/12-bulk-delete-grill.md`
Tanggal: 2026-10-21 · Status: backend selesai dan teruji; UI selesai dibangun (build hijau), menunggu uji manual oleh user.

Dua pertanyaan terbuka plan belum dijawab eksplisit; user menjawab "ya" atas usulan saya (cakupan hanya Library: gambar, video, karakter; berkas dihapus permanen tanpa tong sampah).

## Yang dibangun
### Backend
- `service.py` `Studio.bulk_delete(image_ids, clip_ids, character_ids, ws)`:
  - Id ganda dibuang; semua daftar kosong → `ServiceError` 400.
  - Klip diurutkan `chain_depth` terbesar dulu, lalu karakter, lalu gambar. Tiap item lewat `delete_clip` / `delete_character` / `delete_image` yang sudah ada, jadi aturan penolakan tidak bisa menyimpang. Kunci `_lock` per item.
  - Respons `{deleted: {images, clips, characters}, skipped, failed: [{type, id, reason}]}`. 404 (sudah terhapus atau milik workspace lain) dihitung `skipped`; penolakan lain (409) masuk `failed` dengan pesan aslinya.
- `main.py`: `BulkDeleteIn` (maks 200 id total → 422) dan `POST /api/bulk-delete`.

### Frontend
- `api.ts`: `bulkDelete`.
- `pages/Library.tsx`:
  - Mode pilih berganti nama "Pilih banyak"; video kini bisa dipilih.
  - Bar aksi: "Pilih semua yang terlihat" (hanya menambah yang lolos filter/pencarian), "Kosongkan", "Salin (N)…" (hanya gambar dan karakter), "Hapus (N)".
  - Bar menampilkan jumlah terpilih yang tersembunyi filter.
  - `BulkDeleteDialog`: rincian per jenis, peringatan item tersembunyi, dan akibat (berkas hilang dari disk, biaya tetap terhitung, keyframe adegan kosong, gambar karakter yang tidak ikut dipilih tetap ada). Hasil lewat toast; yang gagal ditampilkan alasannya.
  - Pilihan dibersihkan otomatis dari id yang sudah tidak ada setelah muat ulang.
- `App.tsx`: prop `reload` untuk Library (muat ulang klip, gambar, biaya, dan karakter).
- `styles.css`: `.pickbar` boleh membungkus baris.

## Temuan grill yang ditangani
| Grill | Penanganan |
|---|---|
| Menghapus item tersembunyi filter | Jumlah tersembunyi di bar dan dialog; "pilih semua" hanya yang terlihat. |
| Permintaan diulang | 404 → `skipped`. Test `test_repeat_request_counts_as_skipped_and_duplicates_are_dropped`. |
| Sweep workspace tidak mencakup body | Test khusus `test_other_workspace_ids_are_skipped_and_untouched`. |
| Karakter vs gambarnya | Urutan karakter sebelum gambar; test `test_character_and_its_image_in_one_request`. |
| Pesan akibat akurat | Teks dialog. |
| Rantai extend | Test rantai tiga tingkat dan induk tanpa anak terpilih. |
| Klip disabled di mode pilih | `disabled` dihapus. |

## Menyimpang dari plan
- Label tombol mode pilih berganti dari "Pilih untuk salin" menjadi "Pilih banyak", karena kini dipakai untuk dua aksi.
- Waktu 200 penghapusan nyata tidak diukur; di test, 200 id yang tidak ada hanya melewati jalur 404. Penghapusan 200 berkas besar belum diukur.

## Hasil tes
- `make test`: **221 passed** (214 sebelumnya + 7 baru di `backend/tests/test_bulk_delete.py`: rantai utuh, induk tanpa anak, klip berjalan, karakter+gambar, ulang/ganda, kosong dan batas 200, lintas workspace).
- `cd frontend && npm run build`: hijau.

## Uji frontend: diuji manual oleh user
Restart backend dulu (`make be` / `make dev`) karena ada endpoint baru.
1. Library → "Pilih banyak": gambar, video, dan karakter semuanya bisa dipilih.
2. "Pilih semua yang terlihat" dengan filter "Video": hanya video yang terpilih. Ganti filter ke "Gambar": bar menampilkan "(N tersembunyi)".
3. Hapus dengan item tersembunyi: dialog menampilkan peringatan jumlah tersembunyi.
4. Pilih beberapa gambar + video, Hapus: dialog rinci, konfirmasi, toast "N item dihapus", item hilang dari grid, biaya hari ini tidak turun.
5. Pilih satu rantai extend utuh: terhapus semua. Pilih hanya induknya: toast gagal dengan alasan "punya lanjutan".
6. Pilih gambar milik karakter tanpa memilih karakternya: gagal dengan alasan; pilih keduanya: berhasil.
7. Video yang masih diproses: ditolak, sisanya tetap terhapus.
8. "Salin (N)…" menghitung hanya gambar dan karakter; video tidak ikut.

## Riwayat
- 2026-10-21: implementasi awal.
