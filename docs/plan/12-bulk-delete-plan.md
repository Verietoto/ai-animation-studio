# 12 - Hapus banyak sekaligus di Library (Plan)

- Status: draft, menunggu persetujuan
- Tanggal: 2026-10-21

## Tujuan
Permintaan user: "btw aku butuh tambahan untuk bulk delete".

Sekarang gambar, video, dan karakter hanya bisa dihapus satu per satu (Lightbox atau kartu karakter). User ingin memilih banyak item lalu menghapusnya sekaligus.

## Keadaan sekarang
- Penghapusan satuan sudah ada dan jadi sumber aturan: `DELETE /api/images/{id}`, `/api/clips/{id}`, `/api/characters/{id}` memanggil `Studio.delete_image`, `delete_clip`, `delete_character`.
  - Hapus lunak: baris tetap ada dengan `deleted_at`, berkas di disk dihapus. Biaya yang sudah keluar tetap terhitung di anggaran harian.
  - Aturan penolakan (409):
    - gambar dipakai karakter, latar, atau tampilan, atau dipakai job yang masih berjalan;
    - klip masih diproses, punya lanjutan (extend), atau film yang memakainya sedang dirender.
  - Menghapus gambar juga mengosongkan keyframe adegan yang memakainya.
- Library punya mode "Pilih untuk salin" (pilih banyak gambar dan karakter lalu salin ke workspace lain). Video tidak bisa dipilih di mode itu.

## Ruang lingkup
Termasuk:
- Endpoint `POST /api/bulk-delete` dengan `{image_ids, clip_ids, character_ids}` (maks 200 id total). Tiap item diproses sendiri-sendiri; hasilnya `{deleted: {...jumlah}, failed: [{type, id, reason}]}`. Gagal sebagian tidak membatalkan yang lain.
- Urutan yang benar di server supaya satu pilihan bisa membereskan rantai: klip dari yang terdalam (`chain_depth` terbesar) ke yang terangkat, lalu karakter, lalu gambar. Jadi memilih sebuah rantai extend beserta semua klipnya berhasil, dan memilih karakter beserta gambarnya juga berhasil.
- Library: mode pilih yang sama dengan "Pilih untuk salin", ditambah:
  - video ikut bisa dipilih;
  - tombol "Pilih semua yang terlihat" (mengikuti filter dan pencarian);
  - bar aksi dengan "Salin ke workspace…" (hanya memakai gambar dan karakter terpilih) dan **"Hapus (N)"**.
- Dialog konfirmasi: rincian jumlah per jenis, peringatan bahwa berkas dihapus dari disk dan tidak bisa dikembalikan, dan bahwa biaya yang sudah keluar tetap terhitung. Setelah selesai: toast ringkasan, dan item yang gagal ditampilkan beserta alasannya.

Tidak termasuk (usul untuk tahap berikutnya bila perlu):
- Hapus banyak adegan di Storyboard, latar, atau tampilan; semuanya punya UI sendiri.
- Tong sampah/undo. Hapus tetap permanen untuk berkas.
- Menghapus workspace (sudah ada).

## Desain
- Endpoint memakai `delete_*` yang ada, dengan `ws` dari header. Id workspace lain menghasilkan item gagal "tidak ditemukan", bukan 404 untuk seluruh permintaan. Tidak ada jalur hapus baru, jadi aturan penolakan tidak bisa menyimpang dari yang satuan.
- Satu kunci `Studio._lock` per item (bukan per batch) supaya generate lain tidak tertahan lama.
- Frontend: `Library.tsx` memakai satu state pilihan (sudah ada: `picked`) dan `bulkDelete` di `api.ts`. Setelah selesai, muat ulang gambar dan klip.
- Gambar yang terpilih tapi dipakai item lain yang tidak terpilih ditampilkan gagal dengan pesan aslinya (mis. "dipakai karakter X").

## Risiko awal (bahan grill)
- Salah klik menghapus banyak berkas yang tidak bisa dikembalikan. Mitigasi: dialog konfirmasi dengan rincian, dan tombol Hapus tidak aktif saat pilihan kosong.
- Gagal sebagian harus jelas, bukan diam-diam. Mitigasi: daftar gagal dengan alasan.
- Klip dalam rantai extend: urutan penghapusan salah menghasilkan gagal berantai. Mitigasi: urut dari yang terdalam.
- Batas ukuran batch dan waktu (tiap hapus menyentuh disk dan DB).
- Pilihan yang masih menyimpan id item yang sudah terhapus atau pindah workspace.

## Langkah kerja
1. Grill plan ini.
2. Backend: `Studio.bulk_delete`, endpoint, test (urutan rantai, karakter+gambar, gagal sebagian, klip berjalan ditolak, lintas workspace, batas 200, id ganda, daftar kosong).
3. Frontend: mode pilih diperluas, bar aksi, dialog, ringkasan hasil.
4. Dokumen implementation 12 dan daftar uji manual untuk user.

## Kriteria selesai
- `make test` hijau dengan test baru; build frontend hijau.
- Memilih rantai extend utuh atau karakter beserta gambarnya terhapus sekali jalan; item yang tidak boleh dihapus dilaporkan dengan alasan; yang lain tetap terhapus.

## Pertanyaan terbuka
1. Cukup di Library (gambar, video, karakter), atau kamu juga butuh di tempat lain, mis. adegan di Storyboard, latar, atau job di antrian?
2. Setuju hapus tetap permanen untuk berkas (tanpa tong sampah)?

## Riwayat
- 2026-10-21: draft awal.
- 2026-10-21: setelah grill (belum ada persetujuan atas dua pertanyaan terbuka):
  - 404 pada item dihitung `skipped` ("sudah tidak ada"), bukan gagal.
  - Daftar kosong 400; id ganda dibuang; maksimum 200 id.
  - Dialog menampilkan jumlah yang tersembunyi filter, dan pilihan dibersihkan dari id yang sudah tidak ada.
  - Test isolasi workspace khusus, karena sweep hanya mencakup id di path.
  - Rincian di grill 12.
