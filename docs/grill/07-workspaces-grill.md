# 07 - Workspace (Grill)

Plan terkait: `docs/plan/07-workspaces-plan.md`

Keparahan: **T** tinggi, **S** sedang, **R** rendah. Temuan bertanda (kode) sudah dicek di repo.

## Lubang pada plan
1. **(T) `<img src>`, `<video src>`, dan `<a download>` tidak bisa mengirim header (kode).** Plan menaruh workspace di header `X-Workspace-Id` lewat `call()`, tetapi gambar/video dimuat langsung oleh browser lewat `api.imageUrl`, `api.clipUrl`, `api.mergedUrl`, `api.filmUrl`, `api.sketchUrl`. Tanpa header, server menganggapnya workspace "Utama" → semua gambar/video di workspace lain 404 di UI.
   - Mitigasi: endpoint berkas yang hanya-baca (`/images/{id}/file`, `/images/{id}/sketch`, `/clips/{id}/file`, `/clips/{id}/merged`, `/films/{id}/file`) **tidak** dicakup header; aksesnya berdasarkan id UUID (aplikasi lokal satu user). Semua daftar dan semua operasi yang mengubah data tetap dicakup. Tes: berkas dari workspace lain tetap bisa dimuat; operasi atasnya tetap 404.
2. **(T) Satu query yang lupa difilter = kebocoran antar workspace (kode).** Query tersebar di `main.py` (daftar), `service.py` (`get_image`, `get_clip`, `get_character`, `character_images`, `delete_*`, `plan_edit`), `films.py` (validasi `clip_ids`, `_playable`, `detail`, `detach_clip`), `motion.py` (`refs`, `get_clip` sumber referensi).
   - Mitigasi: workspace dikirim sebagai **parameter eksplisit** ke fungsi service (bukan contextvar global): poller latar tidak punya request, dan parameter eksplisit terlihat di tes. Satu tes "lintas workspace" berparameter memanggil **setiap** endpoint yang menerima id dengan id milik workspace lain dan mengharapkan 404/422. Daftar endpoint di tes diambil dari `app.routes` sehingga endpoint baru yang lupa didaftarkan membuat tes gagal (kecuali yang ada di daftar pengecualian berkas, nomor 1).
3. **(T) Fallback "tanpa header → Utama" menyembunyikan bug frontend.** Request yang lupa header diam-diam menulis ke "Utama", bukan gagal.
   - Mitigasi: fallback dipertahankan untuk klien lama/tes/skrip, tetapi frontend hanya punya **satu** `fetch` (di `call()`); pemeriksaan `grep "fetch(" frontend/src` = 1 hasil dicatat di implementation. Server mengembalikan header `X-Workspace-Id` di setiap respons; `call()` membandingkannya dan melempar galat bila beda (bug terdeteksi saat dipakai, bukan diam-diam).
4. **(T) Job berjalan di workspace lain jadi tidak terlihat.** Dock memakai daftar klip workspace aktif; setelah pindah workspace, job berbayar yang masih jalan di workspace lama hilang dari dock dan toast selesainya tidak pernah muncul.
   - Mitigasi: endpoint ringan `GET /api/jobs` (tidak dicakup workspace): klip aktif + 10 terakhir dari **semua** workspace dengan nama workspace-nya. Dock memakai ini; item dari workspace lain diberi label dan diklik → pindah workspace lalu buka klip. Library tetap hanya workspace aktif.
5. **(S) Salin tidak bisa atomik dengan `Database` sekarang (kode).** `Database.execute/insert/update` melakukan commit di setiap panggilan; tidak ada transaksi.
   - Mitigasi: tambah `Database.transaction()` (context manager memakai lock yang sama, satu commit di akhir, rollback saat galat). Salin: file disalin dulu ke path baru, lalu semua baris dimasukkan dalam satu transaksi; bila gagal, transaksi dibatalkan dan file baru dihapus. Tes memaksa kegagalan di tengah (id terakhir tidak valid) dan memeriksa tidak ada baris/file baru.
6. **(S) Kolom wajib tidak bisa ditambahkan sebagai NOT NULL di SQLite tanpa default (kode: pola `ALTER TABLE ... ADD COLUMN`).** Baris baru dengan `workspace_id` kosong tidak akan tertolak DB.
   - Mitigasi: service selalu mengisi; tes penutup menjalankan alur utama (upload, edit, video, extend, karakter, sheet, film, motion ref) di workspace non-default lalu memeriksa tidak ada baris dengan `workspace_id IS NULL` di semua tabel.
7. **(S) Respons lama menimpa state setelah pindah workspace.** Request daftar dari workspace A yang selesai setelah user pindah ke B akan menampilkan data A di B.
   - Mitigasi: seluruh isi aplikasi di bawah topbar dirender ulang dengan `key={workspaceId}` sehingga semua hook dipasang ulang; `useAsync` sudah mengabaikan respons setelah unmount. Polling `useClips` ikut diganti.
8. **(S) Workspace aktif tersimpan di `localStorage` bisa sudah diarsip/tidak ada** (tab lain mengarsipkan, DB diganti).
   - Mitigasi: server mengembalikan 404 dengan kode jelas untuk workspace tidak dikenal/diarsip; `call()` menangkapnya sekali, kembali ke "Utama", memuat ulang, dan menampilkan toast. Workspace yang sedang aktif tidak bisa diarsip dari UI (pindah dulu); "Utama" tidak bisa diarsip.
9. **(S) Jejak asal salinan menunjuk ke workspace lain.** `origin_image_id` ada di workspace sumber; Lightbox yang mencoba membukanya akan 404.
   - Mitigasi: Lightbox menampilkan teks "Disalin dari workspace X" (nama diambil server saat membentuk respons gambar), bukan tautan. `parent_image_id` salinan dikosongkan (sudah di plan).
10. **(S) Nama bentrok berulang.** "Rina (salinan)" disalin lagi menjadi "Rina (salinan) (salinan)".
    - Mitigasi: "Nama (salinan 2)", "(salinan 3)", dst. berdasarkan nama yang sudah ada di target.
11. **(S) Menyalin ke workspace yang diarsip atau ke workspace yang sama.**
    - Mitigasi: target diarsip → 404; target == sumber → 400 ("pilih workspace lain"). Gambar yang sudah dihapus (soft delete) → 404.
12. **(S) Daftar per workspace butuh indeks.** Query daftar sekarang `ORDER BY created_at DESC LIMIT 200`; dengan filter `workspace_id` tanpa indeks, SQLite memindai seluruh tabel.
    - Mitigasi: indeks `(workspace_id, created_at)` di `images`, `clips`, `characters`, `films` dalam migrasi v7.
13. **(S) Biaya "hari ini" global vs perasaan per workspace.** User bisa mengira chip biaya hanya untuk workspace aktif.
    - Mitigasi: label chip "hari ini · semua workspace"; detail per workspace tidak dibuat (YAGNI).
14. **(R) Salin karakter tanpa sheet / sheet yang gambarnya sudah dihapus.** `character_images` bisa menunjuk gambar soft-deleted.
    - Mitigasi: gambar terhapus dilewati saat menyalin karakter; bila gambar sumber karakter sendiri terhapus, salin karakter ditolak dengan pesan jelas.
15. **(R) Ruang disk.** Salinan menggandakan file. Gambar PNG beberapa MB; diterima. Ringkasan dialog salin menampilkan jumlah gambar.
16. **(R) `refs` (plan 03, masih WIP).** Ikut diberi `workspace_id` di migrasi supaya plan 03 tidak perlu migrasi lagi; UI plan 03 belum ada.

## Edge case
- Workspace baru tanpa isi: semua halaman menampilkan empty state; katalog model dan riwayat prompt tetap global.
- Nama workspace kosong/hanya spasi atau > 60 karakter → 422; nama sama dengan workspace lain → 409, supaya pemilih tidak membingungkan.
- Pindah workspace saat dialog konfirmasi biaya terbuka: dialog ikut tertutup karena subtree dipasang ulang (job belum dikirim).
- Pindah workspace saat render film berjalan: render tetap jalan di server; status terlihat lagi saat kembali.
- Salin karakter + salah satu gambarnya dipilih juga: gambar disalin sekali.
- Salin gambar yang merupakan gambar sheet karakter tanpa menyalin karakternya: gambar tersalin sebagai gambar biasa (`kind` tetap `sheet`).
- Shortcut `1`-`5` tidak berubah; palette mendapat aksi "Pindah workspace…".

## Potensi bug
- `plan_edit` memvalidasi gambar pose/ekspresi/referensi dengan `get_image` tanpa workspace → bisa menerima gambar workspace lain. Harus lewat versi bercakupan.
- `Films.update` memvalidasi `clip_ids` dengan `SELECT id FROM clips WHERE ... id IN (...)` tanpa workspace.
- `delete_image` memeriksa pemakaian karakter lewat join `character_images` tanpa workspace (aman karena satu gambar hanya milik satu workspace, tetapi tetap dites).
- `idempotency_key` UNIQUE global: dua workspace tidak bisa memakai kunci sama, wajar (kunci acak).
- Tes lama memanggil endpoint tanpa header: harus tetap lulus (workspace "Utama").

## Asumsi yang belum terbukti
- Satu user lokal; keamanan berbasis UUID untuk endpoint berkas cukup (bila kelak multi-user, nomor 1 harus ditinjau ulang).
- Performa salin karakter dengan 5-6 gambar beberapa MB cukup cepat untuk request sinkron (< 1 detik di disk lokal). Diukur di tes dengan ukuran gambar realistis.

## Keputusan setelah grilling (perubahan pada plan)
- Endpoint berkas hanya-baca tidak dicakup workspace; semua daftar dan operasi lain dicakup.
- Workspace sebagai parameter eksplisit di service; tes lintas-workspace berparameter dari `app.routes`.
- Server mengembalikan `X-Workspace-Id`; `call()` memverifikasi dan menangani workspace yang hilang/diarsip (kembali ke "Utama").
- Tambah `GET /api/jobs` lintas workspace untuk dock.
- Tambah `Database.transaction()`; salin atomik termasuk pembersihan file.
- Tes "tidak ada `workspace_id` NULL" setelah alur utama.
- Subtree aplikasi di-key oleh workspace.
- Penamaan "(salinan N)", target sama/diarsip ditolak, gambar terhapus dilewati/ditolak.
- Indeks `(workspace_id, created_at)`; label chip biaya "semua workspace".
- Nama workspace unik (409), maks 60 karakter; "Utama" dan workspace aktif tidak bisa diarsip.

## Grill revisi 1: hapus workspace + pulihkan arsip
Dicek di kode: `committed_today` menjumlahkan baris `clips`/`images` tanpa filter `deleted_at` (sengaja); `refs` untuk "dari klip library" memakai **path file klip itu sendiri** (`motion._save_ref(path=clip path)`); `workspaces.name` bertanda `UNIQUE` di tabel (tidak bisa diubah tanpa membangun ulang tabel); hapus aset (plan 05 revisi 3) sudah memakai `deleted_at` + hapus file.

### Lubang
17. **(T) Hapus baris = hapus catatan biaya.** Menghapus workspace sungguhan akan menurunkan "terpakai hari ini" dan membuka celah batas harian, persis masalah hapus aset (grill 05 nomor 19).
    - Mitigasi: gambar dan klip hanya ditandai `deleted_at` (+ file dihapus); baris tetap. Tombstone workspace tetap ada karena baris-baris itu masih menunjuknya. Tes: `committed_today` sama persis sebelum/sesudah.
18. **(T) Penghapusan massal tak bisa dibatalkan, mudah salah klik.**
    - Mitigasi: hanya dari bagian Arsip (arsip dulu, bukan Utama, bukan aktif), dialog menyebut jumlah isi, dan **mengetik nama workspace** untuk membuka tombol. Pulihkan tersedia selama belum dihapus.
19. **(T) File dihapus sebelum transaksi berhasil = data hilang tanpa catatan.** Bila commit gagal, file sudah terlanjur hilang.
    - Mitigasi: urutan: transaksi DB dulu, **commit, baru unlink** (best-effort). Kegagalan unlink meninggalkan file yatim (tidak ada baris yang menunjuknya), tidak merusak data. Tes memaksa kegagalan di tengah transaksi dan memeriksa semua file masih ada.
20. **(S) Job berjalan / render film di workspace yang dihapus.** Poller akan menulis hasil ke klip yang sudah ditandai terhapus; render film menulis file ke film yang sudah dihapus.
    - Mitigasi: cek di bawah `Studio._lock` (kunci yang sama dengan `create_clip`): klip `submitted/in_progress` atau film `rendering` → 409 "tunggu selesai". Membuat job baru butuh gambar di workspace itu (semuanya sudah terhapus), jadi tak ada job baru yang bisa masuk setelah commit; jendela balapan unggah gambar baru saat penghapusan sangat sempit dan diterima (catat).
21. **(S) Berkas bersama (kode).** Referensi video "dari klip" memakai path klip; menghapus `ref.path` mentah-mentah menghapus file milik klip (dan sebaliknya menghapus klip lalu referensi yang sama).
    - Mitigasi: hapus berkas `refs` hanya bila `source_clip_id IS NULL` (unggahan sendiri); yang dari klip ikut hilang bersama klipnya. Hapus juga `merged_path` klip dan file render film.
22. **(S) Nama `UNIQUE` pada tombstone.** Nama lama akan terkunci selamanya dan user tak bisa membuat workspace dengan nama itu lagi.
    - Mitigasi: tombstone diganti nama "Nama (dihapus abc123)" dalam transaksi yang sama (id 6 karakter pertama). Daftar `origin_workspace` pada salinan lain menampilkan nama itu, bermakna bagi user.
23. **(S) Semua jalur harus menolak workspace terhapus.** `workspaces.get` (dipakai `get_ws`, salin, ganti nama, arsip), `list_all`, `jobs()` (join workspace), `copy` target, `restore`.
    - Mitigasi: `get` dan `list_all` memfilter `deleted_at IS NULL` di satu tempat; tes berparameter memanggil tiap endpoint workspace dengan id terhapus (404/409) dan `GET /api/workspaces?archived=true` tidak memuatnya; `jobs()` tidak menampilkan klip terhapus (sudah memfilter `deleted_at` klip).
24. **(S) Tab lain sedang memakai workspace itu.** Header lama → 404 `workspace_missing` → frontend kembali ke Utama (sudah ada, grill 8); tes memastikan kode galat sama untuk terhapus dan diarsip.
25. **(S) Sisa baris yatim di `character_images`/`films`.** Menghapus karakter tanpa `character_images` meninggalkan baris tak terpakai; gambar yang masih dipakai karakter biasanya ditolak oleh aturan hapus gambar.
    - Mitigasi: semua dalam satu transaksi: hapus `character_images` → `characters` → `films` → `refs` lebih dulu, baru tandai gambar/klip (penghapusan massal sengaja melewati aturan "gambar dipakai karakter" karena karakternya ikut hilang). Tes memeriksa tidak ada baris yatim.
26. **(S) Pulihkan.** Nama unik lintas semua workspace (termasuk arsip) sehingga tidak ada bentrok; yang bukan arsip → 409; tombstone/Utama → 404/400.
27. **(R) Salinan di workspace lain** menunjuk `origin_image_id` ke gambar yang kini terhapus: tidak memengaruhi salinan (file terpisah, sudah digandakan); keterangan asal memakai nama tombstone. Tes memeriksa salinan masih bisa dimuat.
28. **(R) Hitungan isi untuk dialog** (`counts`) menghitung baris tak terhapus saja; dialog dan respons hapus memakai angka itu supaya konsisten.
29. **(R) Kinerja:** ratusan file dihapus sinkron di request; diterima (lokal), tanpa batas waktu khusus.

### Edge case
- Hapus workspace kosong: sukses, jumlah 0.
- Dua permintaan hapus bersamaan: yang kedua 404 (sudah tombstone).
- Hapus lalu buat workspace dengan nama yang sama: berhasil, isinya kosong.
- Salin dari workspace aktif ke workspace yang kemudian dihapus: target terhapus → 404 `workspace_missing`.
- Pemulihan workspace yang berisi klip berjalan: tidak ada pembatasan.

### Keputusan setelah grilling (perubahan pada plan)
- Tombstone dengan kolom `workspaces.deleted_at` (migrasi v8) dan penggantian nama; tidak memindahkan baris.
- Hapus hanya setelah arsip, dengan konfirmasi mengetik nama; ditolak bila job/render berjalan (dicek di bawah kunci studio).
- Urutan: transaksi dulu, file dihapus setelah commit; berkas `refs` dari klip tidak di-unlink dua kali.
- Penambahan kriteria tes: file utuh bila transaksi gagal, tidak ada baris yatim, `committed_today` tidak berubah, nama dipakai ulang, semua endpoint menolak id terhapus.
- Lima asersi versi DB (7 → 8) di tes lama ikut diperbarui.

## Riwayat
- 2026-10-20: grill revisi 1 (hapus/pulihkan workspace), temuan 17 sampai 29.
- 2026-10-20: grill pertama, temuan 1 sampai 16.
