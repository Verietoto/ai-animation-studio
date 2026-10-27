# 07 - Workspace (Plan)

- Status: disetujui user ("go", 2026-10-20), sudah digrill, kode selesai termasuk revisi 1 hapus/pulihkan workspace (lihat `docs/implementation/07-workspaces-implementation.md`); uji frontend menunggu user
- Tanggal: 2026-10-20
- Asal: permintaan user "aku butuh plan untuk membuat workspace, jadi setiap design character dan lainnya per workspace, bisa juga ada fitur copy karakter dan foto yang udah di edit".

## Tujuan
Memisahkan pekerjaan per proyek: tiap **workspace** punya gambar, karakter, video, film (storyboard), dan referensi video sendiri. User bisa berpindah workspace, dan bisa **menyalin karakter** serta **gambar (termasuk hasil edit)** dari satu workspace ke workspace lain.

## Kondisi sekarang (dicek di kode)
- Satu ruang global: tabel `images`, `clips`, `characters` (+ `character_images`), `films`, `refs` (referensi video, plan 03) tanpa pemilik.
- Daftar API (`GET /api/images|clips|characters|films`) mengembalikan semuanya (dibatasi 200 terbaru).
- Batas biaya harian (`committed_today`, plan 04) menjumlahkan semua baris, termasuk yang dihapus (soft delete, plan 05 revisi 3).
- Frontend memanggil API lewat satu helper `call()` di `frontend/src/api.ts`.

## Ruang lingkup (termasuk yang TIDAK dikerjakan)
Termasuk:
- Entitas workspace: buat, ganti nama, arsipkan (sembunyikan). Workspace "Utama" dibuat otomatis dan berisi semua data lama.
- Semua aset (gambar, karakter, video, film, referensi video) milik tepat satu workspace; daftar dan operasi hanya melihat workspace aktif.
- Pemilih workspace di UI (topbar) + "Workspace baru".
- **Salin ke workspace lain**: gambar (asli, hasil edit, frame, sheet) dan karakter (beserta semua gambar sheet-nya).

Tidak termasuk:
- Salin video/klip dan film (bisa jadi plan lanjutan; video besar dan punya rantai extend).
- Pindah (move) aset antar workspace; hanya salin.
- Hapus workspace permanen (hanya arsip, agar catatan biaya tidak hilang).
- Multi-user, izin akses, anggaran per workspace (batas harian tetap global karena uangnya satu).
- Ekspor/impor workspace ke file.

## Desain / pendekatan

### Data (migrasi `user_version` 7)
- Tabel baru `workspaces(id, name, created_at, updated_at, archived_at)`.
- Kolom `workspace_id TEXT` di `images`, `clips`, `characters`, `films`, `refs`. Migrasi membuat workspace "Utama" dan mengisi semua baris lama dengannya; kolom wajib untuk baris baru (diisi service, bukan default DB, supaya lupa mengisi langsung ketahuan di tes).
- Kolom `origin_image_id TEXT` di `images`: asal salinan (lintas workspace). `parent_image_id` salinan dikosongkan agar jejak asal (Lightbox) tidak menunjuk ke workspace lain.
- `character_images` tidak berubah (mengikuti karakter); aturan: gambar karakter harus satu workspace dengan karakternya.

### Cakupan di backend
- Workspace aktif dikirim lewat header `X-Workspace-Id` oleh `call()`; dependency FastAPI `get_workspace` memvalidasi (ada dan tidak diarsip). Tanpa header → workspace "Utama" (klien lama, tes lama, skrip).
- Semua query daftar memfilter `workspace_id`. Semua `get_*` (`get_image`, `get_clip`, `get_character`, film, ref) menerima workspace dan mengembalikan 404 bila milik workspace lain, sehingga operasi lintas workspace tertutup di satu tempat: edit dengan referensi/pose dari workspace lain, extend klip lain, film berisi klip lain, karakter dengan gambar lain, semuanya 404/422.
- Poller job latar tetap global (tidak terikat request); job tahu workspace-nya dari baris klip.
- Biaya: `committed_today` tetap global (tidak difilter). Chip biaya di topbar tetap "hari ini, semua workspace".

### Salin ke workspace lain
- `POST /api/workspaces/{target_id}/copy` dengan body `{"image_ids": [...], "character_ids": [...]}` dari workspace aktif.
- Gambar: **file disalin** (byte baru di storage, id baru), baris baru di target dengan `origin_image_id` = id asal, `prompt`/`model`/`kind`/ukuran sama, **`cost` dan `estimated_cost` kosong** (salinan tidak dibayar ulang dan tidak boleh menggandakan biaya hari ini). Menyalin file (bukan berbagi path) membuat hapus di satu workspace tidak merusak workspace lain.
- Karakter: baris karakter baru (nama sama; bila nama sudah ada di target → "Nama (salinan)"), semua gambar sheet-nya disalin seperti di atas, `character_images` dibuat ulang dengan label sama.
- Satu permintaan atomik: gagal satu → tidak ada yang tersimpan, file yang sudah tersalin dihapus. Gambar yang sama dalam satu permintaan (dipilih langsung dan juga bagian karakter) disalin sekali.
- Respons: daftar id baru, untuk tombol "Buka di workspace X".

### Frontend
- **Pemilih workspace** di topbar (kiri, di samping judul halaman): dropdown nama + jumlah aset, "Workspace baru…" (input inline), "Ganti nama", "Arsipkan". Workspace aktif disimpan di `localStorage` (try/catch; fallback "Utama"). Ganti workspace memuat ulang gambar, klip, karakter, film; gambar terpilih, hasil edit, dan Lightbox ditutup.
- `call()` menambahkan header `X-Workspace-Id` ke semua request; `useClips`, `useCatalog` (katalog global, tidak berubah), dll. tidak perlu tahu.
- **Salin ke…**: tombol di Lightbox (gambar), di kartu karakter, dan mode pilih-banyak di Library (centang beberapa gambar/karakter → "Salin ke workspace…"). Dialog: pilih workspace tujuan (atau buat baru), ringkasan "3 gambar, 1 karakter (5 gambar)", konfirmasi, toast dengan aksi "Buka".
- Command palette: "Pindah workspace…", "Workspace baru".

## Langkah kerja
1. Grill plan ini (`docs/grill/07-workspaces-grill.md`).
2. Backend: migrasi v7, `get_workspace`, pemfilteran di semua daftar dan `get_*`, endpoint workspace (daftar, buat, ganti nama, arsip) dan salin.
3. Tes backend.
4. Frontend: header di `call()`, pemilih workspace, dialog salin, mode pilih-banyak di Library, aksi palette.
5. Dokumen implementation (uji frontend oleh user).

## Kriteria selesai
- Tes backend (`backend/tests/test_workspaces.py`):
  - migrasi v6 → v7: semua baris lama masuk "Utama", data tetap utuh;
  - isolasi: daftar hanya workspace aktif; `get`/edit/extend/film/karakter dengan id dari workspace lain → 404/422; tanpa header → "Utama";
  - workspace diarsip tidak bisa dipakai sebagai header (400/404) dan tidak muncul di daftar default;
  - salin gambar: id baru, file baru ada, `origin_image_id` benar, biaya kosong, `committed_today` tidak berubah, hapus asli tidak merusak salinan;
  - salin karakter: semua gambar sheet tersalin, label sama, nama "(salinan)" bila bentrok;
  - salin atomik: satu id tidak valid → tidak ada baris/file baru;
  - semua tes lama tetap lulus tanpa header (workspace "Utama").
- `make test` dan `npm run build` hijau.
- Uji frontend dilakukan user (daftar alur di dokumen implementation).

## Pertanyaan terbuka
- ~~Perlu salin video/film?~~ **Dijawab user 2026-10-20: tidak.** Hanya gambar dan karakter.
- ~~Ikut salin gambar asal hasil edit?~~ **Dijawab user 2026-10-20: tidak, cukup gambar itu saja**; asal dicatat di `origin_image_id`.

## Revisi 1 (2026-10-20): hapus workspace + pulihkan arsip
Permintaan user: "apa sudah bisa delete workspace?" → belum; setelah ditawarkan, user minta direvisi dan digrill ("ya revisi dulu terus grill"). Menggantikan "Hapus workspace permanen" di Ruang lingkup (Tidak termasuk) untuk bagian di bawah; sisanya tetap.

### Tujuan
Workspace yang sudah tidak dipakai bisa **dihapus** (aset dan filenya hilang, ruang disk kembali), dengan pengaman bertingkat; workspace yang **diarsip** bisa **dipulihkan**.

### Alur
1. **Arsipkan** (sudah ada) → workspace hilang dari daftar utama dan muncul di bagian **"Arsip"** di pemilih workspace.
2. Di bagian Arsip: **Pulihkan** (kembali aktif) atau **Hapus permanen…**.
3. Hapus permanen hanya untuk workspace yang **sudah diarsip**, bukan "Utama", dan bukan workspace aktif. Dialog menampilkan ringkasan isi ("12 gambar, 3 video, 2 karakter, 1 film akan dihapus") dan meminta user **mengetik nama workspace** untuk mengonfirmasi.

### Perilaku hapus (backend)
- `POST /api/workspaces/{id}/restore` dan `DELETE /api/workspaces/{id}` (respons: jumlah item yang dihapus).
- Ditolak 409 bila masih ada **job klip berjalan** atau **film sedang dirender** di workspace itu; ditolak 409 bila belum diarsip; 400 untuk "Utama" dan workspace aktif.
- **Catatan biaya tetap utuh**: gambar dan klip ditandai terhapus (`deleted_at`, seperti fitur hapus aset) dan filenya (termasuk hasil gabung rantai) dihapus dari disk, tetapi barisnya tetap, sehingga `committed_today` dan batas harian tidak berubah. Karakter (+ `character_images`), film (+ file render), dan referensi video dihapus sungguhan karena tidak membawa biaya.
- Workspace-nya sendiri menjadi **tombstone** (kolom `workspaces.deleted_at`, migrasi v8): tidak muncul di daftar mana pun dan tidak bisa dipakai/dipulihkan; namanya diganti "Nama (dihapus abc123)" agar nama aslinya bisa dipakai lagi dan keterangan "Disalin dari workspace …" pada salinan di workspace lain tetap bermakna.
- Semua perubahan basis data dalam **satu transaksi**; file dihapus **setelah commit** (gagal hapus file = file yatim, tidak merusak data).
- Header workspace yang sudah terhapus (mis. dari tab lain) → 404 `workspace_missing`, frontend kembali ke Utama (mekanisme yang sudah ada).

### Frontend
- Pemilih workspace: bagian "Arsip (n)" yang bisa dilipat; tiap baris punya **Pulihkan** dan **Hapus permanen…**; tombol hapus tidak berdekatan dengan tombol Pulihkan.
- Dialog hapus: ringkasan isi, kolom "ketik nama untuk konfirmasi", tombol merah nonaktif sampai cocok; galat 409 (job berjalan) ditampilkan apa adanya.

### Kriteria selesai (tambahan)
- Tes: pulihkan (arsip → aktif, nama tetap); hapus ditolak (belum diarsip, Utama, aktif, job berjalan, film dirender); hapus berhasil (file hilang dari disk, baris gambar/klip `deleted_at`, karakter/film/ref hilang, `committed_today` sama persis, nama bisa dipakai ulang, header workspace terhapus → 404 `workspace_missing`, semua endpoint workspace menolak id terhapus, salinan di workspace lain tetap utuh dengan `origin_workspace` berlabel "(dihapus …)"); kegagalan di tengah transaksi tidak menghapus file; migrasi v7 → v8; semua tes lama lulus.
- `make test` dan `npm run build` hijau; uji frontend oleh user (daftar alur di dokumen implementation).

## Riwayat
- 2026-10-20: revisi 1, hapus workspace + pulihkan arsip (permintaan user); digrill di grill 07 bagian "Grill revisi 1".
- 2026-10-20: draft pertama.
- 2026-10-20: pertanyaan terbuka dijawab user: video/film tidak disalin; hasil edit disalin tanpa rantai asalnya.
- 2026-10-20: setelah grill (`docs/grill/07-workspaces-grill.md`), bagian "Keputusan setelah grilling" di sana menimpa plan ini bila bertentangan. Ringkas: endpoint berkas (gambar/video/sketsa/film) tidak dicakup header karena `<img>`/`<video>` tidak bisa mengirim header; workspace jadi parameter eksplisit di service + tes lintas-workspace dari `app.routes`; respons membawa `X-Workspace-Id` dan `call()` memverifikasinya; `GET /api/jobs` lintas workspace untuk dock; `Database.transaction()` untuk salin atomik; subtree UI di-key per workspace; nama "(salinan N)"; indeks `(workspace_id, created_at)`.
