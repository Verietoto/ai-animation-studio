# 21 - Panel komik (Grill)

- Tanggal: 2026-10-27
- Keputusan default (user menyetujui tanpa memilih): gaya `project` (ikut gaya visual proyek) dengan pilihan manga, komik Barat, webtoon; panel per proyek; rasio bawaan 4:3.

## Temuan dan mitigasi
1. **Estimasi berbeda dari generate** (jumlah gambar input). Mitigasi: satu fungsi `plan()` dipakai `/api/estimate` dan generate; `authorize()` memberi 409 bila biaya berubah.
2. **Model gambar tetap menggambar teks/balon** meski diminta tidak. Mitigasi: aturan "no text" di akhir prompt; balon overlay menutupi; generate ulang membuat take baru. Tidak bisa dijamin, dicatat.
3. **Model tidak mendukung rasio panel** (mis. Seedream tanpa 4:3). Mitigasi: pola `_aspect_option`: rasio hanya dikirim bila didukung, pratinjau memberi peringatan; kanvas memakai ukuran gambar asli, koordinat balon relatif 0..1 jadi tetap benar.
4. **Model tidak menerima sebanyak itu gambar referensi** (latar + 4 karakter = 5). Mitigasi: `_validate_image_params(model, options, n)` menolak 422 sebelum biaya keluar.
5. **Karakter, latar, atau gambar take dihapus**: JSON `character_ids` dan `image_id` bisa basi. Mitigasi: dibersihkan saat dibaca (karakter/latar yang hilang dibuang dari respons; `image_id` mati diganti take hidup terbaru atau null). Generate memakai data yang sudah dibersihkan.
6. **Kunci tidak reentrant**: `db._lock` tidak boleh dipanggil di dalam `db.transaction()`. Mitigasi: generate memakai `Studio._lock` (RLock) seperti `keyframe`/`location_image`, tanpa transaksi bersarang.
7. **Hapus proyek** meninggalkan panel yatim. Mitigasi: `DELETE FROM comic_panels WHERE workspace_id = ?` di penghapusan workspace + tes.
8. **Balon tidak valid** (koordinat di luar gambar, teks kosong/panjang, terlalu banyak). Mitigasi: Pydantic + validasi server: x,y,w,h,tail dalam 0..1, w,h > 0.02, teks ≤ 300, ≤ 20 balon, jenis dari daftar tetap.
9. **Unduh PNG**: canvas bisa "tainted" atau font belum termuat. Mitigasi: gambar dari origin yang sama (`/api/images/{id}/file`), `document.fonts.ready` sebelum menggambar; teks dibungkus dan dikecilkan otomatis bila tidak muat.
10. **Take otomatis menimpa pilihan** (kebalikan masalah video adegan 1). Diterima: take baru langsung dipakai, take lama tetap bisa dipilih; dijelaskan di UI.
11. **Model gambar tidak dipilih** di proyek. Mitigasi: body boleh membawa `model`; bila kosong dan proyek tidak punya `image_model`, 422 dengan pesan jelas.
