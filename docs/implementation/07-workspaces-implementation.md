# 07 - Workspace (Implementation)

Plan: `docs/plan/07-workspaces-plan.md`
Grill: `docs/grill/07-workspaces-grill.md`

Status: **kode selesai; `make test` 141 lulus dan `npm run build` hijau; uji frontend menunggu user** (aturan `CLAUDE.md`).

## Yang dibangun
- **Data (migrasi v7, `db.py`)**: tabel `workspaces(id, name UNIQUE, created_at, updated_at, archived_at)`; kolom `workspace_id` di `images`, `clips`, `characters`, `films`, `refs`; `images.origin_image_id`; indeks `(workspace_id, created_at)`. Workspace **"Utama" (id `main`)** dibuat otomatis dan menampung semua data lama. `Database.transaction()` (+ `_Tx`) untuk beberapa penulisan sebagai satu unit.
- **Pencakupan di backend**: setiap fungsi service/films/motion yang membaca atau menulis aset menerima `ws` eksplisit (`get_image`, `get_clip`, `get_character`, `_save_image`, `create_clip`, `extend_clip`, `merge_chain`, `edit_image`/`plan_edit`, karakter, sheet, hapus, film, referensi video, anchor/motion). `get_*` memakai default `DEFAULT_WS` (bukan "tanpa batas") supaya pemanggil yang lupa `ws` gagal 404, bukan membocorkan data; `None` hanya untuk poller latar dan berkas.
- **API**: dependency `get_ws` membaca header `X-Workspace-Id` (tanpa header = Utama), memvalidasi (hilang/diarsip → 404 `code: workspace_missing`), dan menggemakan id di header respons. Endpoint baru: `GET/POST /api/workspaces`, `PUT /api/workspaces/{id}` (ganti nama), `POST /api/workspaces/{id}/archive`, `POST /api/workspaces/{target}/copy`, `GET /api/jobs` (lintas workspace). Daftar gambar membawa `origin_workspace` untuk salinan.
- **Salin (`workspaces.py`)**: gambar dan karakter (beserta gambar sheet) dari workspace aktif ke tujuan. File digandakan (id dan path baru), `cost`/`estimated_cost` salinan dikosongkan (biaya hari ini tidak naik), `parent_image_id` dikosongkan, `origin_image_id` mencatat asal, nama karakter bentrok jadi "(salinan)", "(salinan 2)", dst. Atomik lewat `transaction()` dengan pembersihan file bila gagal; gambar terhapus dilewati; karakter dengan gambar sumber terhapus ditolak 409; tujuan sama/diarsip ditolak.
- **Frontend**: `api.ts` mengirim `X-Workspace-Id` di satu-satunya `fetch` dan memverifikasi gema di respons sukses; `workspaces.tsx` (context, pemilih workspace di topbar dengan buat/ganti nama/arsip, dialog "Salin ke workspace…"); `App` memegang workspace aktif dan memasang ulang `AppInner` dengan `key` tiap pindah; dock antrian memakai `/api/jobs` (job workspace lain berlabel nama workspace, klik = pindah workspace lalu buka klip); toast selesai untuk job workspace lain diberi awalan `[Nama]`; tombol salin di Lightbox (gambar), kartu karakter, dan mode "Pilih untuk salin" di Library; Lightbox menampilkan "Disalin dari workspace X"; command palette: "Workspace baru…" dan "Pindah ke workspace: …"; chip biaya berlabel "semua workspace".

## File yang diubah
Backend: baru `workspaces.py`; diubah `db.py`, `service.py`, `films.py`, `motion.py`, `main.py`. Tes: baru `test_workspaces.py`; diubah `conftest.py` (`ConfirmingClient` meneruskan header ke estimasi), 4 asersi versi DB (6 → 7) di `test_characters.py`, `test_cost_guard.py`, `test_delete.py`, `test_films.py`. Frontend: baru `workspaces.tsx`; diubah `api.ts`, `App.tsx`, `queue.tsx`, `lightbox.tsx`, `pages/Library.tsx`, `pages/Characters.tsx`, `styles.css`.

## Penyimpangan dari plan (dan alasannya)
- Aksi arsip ada, tetapi **tidak ada tombol "pulihkan"** (plan hanya menyebut arsip). Data tetap di database; endpoint pulihkan bisa ditambah kapan saja.
- Cek kesamaan header (`X-Workspace-Id`) hanya pada respons sukses; respons galat tidak membawa header, dan `workspace_missing` ditangani lewat kode galat.
- Keamanan berkas hanya-baca (`/file`, `/merged`, `/sketch`) tetap berdasarkan id acak, tanpa batas workspace (keputusan grill 1).
- Pencarian `idempotency_key` klip/motion tidak dicakup workspace (kunci acak per percobaan).
- Estimasi non-`image_edit` (video, sheet) tidak butuh workspace dan tetap global; `image_edit` berbasis id dan `motion` memakainya.
- Mode "pilih untuk salin" hanya untuk gambar dan karakter (video dikecualikan sesuai keputusan user).

## Temuan grill yang sudah ditangani
1 berkas tanpa header (tes `test_cross_workspace_operations_are_rejected`: berkas B bisa dimuat dari Utama, operasinya 404); 2 query terlewat: tes `test_every_id_route_rejects_foreign_ids` menyapu **semua** route berparameter id dari `app.routes` (≥ 15 route, tiap metode) dengan id milik workspace lain dan menuntut status ≥ 400; 3 satu `fetch` (`grep "fetch(" frontend/src` = 1 hasil) + gema header diverifikasi; 4 `GET /api/jobs` (tes `test_jobs_lists_running_clips_from_every_workspace`); 5 `Database.transaction()` + tes rollback dan salin atomik (kegagalan penyimpanan file di tengah → tidak ada baris/file baru); 6 tes `test_new_rows_always_get_a_workspace_and_main_stays_untouched` (alur utama di workspace B, tanpa `workspace_id` NULL dan tanpa baris bocor ke Utama); 7 `key={wsId}` pada `AppInner`; 8 `onMissing` kembali ke Utama dengan toast; 9 "Disalin dari workspace X" lewat `origin_workspace`; 10 penamaan "(salinan N)" (tes tiga kali salin + salin balik); 11 tujuan sama/diarsip/terhapus; 12 indeks; 13 label chip; 14 gambar terhapus dilewati/ditolak (tes); 16 `refs` ikut punya `workspace_id`. Migrasi v6 → v7 dites pada DB berisi data lama.

## Pengujian (perintah dan hasil nyata)
- `make test` → **141 passed** (126 sebelumnya; 15 baru di `test_workspaces.py`; empat tes versi DB diperbarui ke 7; semua tes lama lulus tanpa header = workspace Utama).
- `cd frontend && npm run build` → hijau; `grep -rn "fetch(" frontend/src` → satu hasil (`api.ts`).
- **Diuji manual oleh user (belum dilakukan)**:
  1. Topbar: buka pemilih workspace, buat "Proyek A", ganti nama, pindah; semua halaman (Gambar→Video, Edit Foto, Karakter, Library, Storyboard) kosong di workspace baru dan penuh kembali di Utama.
  2. Unggah gambar di Proyek A, pindah ke Utama: gambar itu tidak muncul; kembali: muncul. Gambar/video tetap tampil (berkas tanpa header).
  3. Buat video di Proyek A lalu pindah ke Utama saat masih berjalan: dock tetap menampilkan job dengan label "Proyek A", toast selesai berawalan `[Proyek A]`; klik job = pindah ke Proyek A dan membuka klipnya.
  4. Library: "Pilih untuk salin", centang beberapa gambar dan satu karakter → "Salin ke workspace…" → pilih tujuan (atau buat baru) → toast "Buka"; di tujuan, gambar punya keterangan "Disalin dari workspace Utama" dan biaya hari ini tidak berubah; karakter tampil dengan sheet-nya dan bisa dipakai di Edit Foto.
  5. Salin ulang karakter yang sama: nama menjadi "Nama (salinan)", lalu "(salinan 2)".
  6. Lightbox gambar: "Salin ke workspace…"; kartu karakter: "Salin ke workspace…".
  7. Arsipkan workspace (bukan Utama, bukan yang aktif) dari pemilih: hilang dari daftar; buka dua tab, arsipkan workspace aktif di tab lain, lalu aksi di tab pertama → toast dan kembali ke Utama.
  8. Command palette (⌘K): "Workspace baru…" dan "Pindah ke workspace: …".
  9. Layar sempit (390px): pemilih workspace dan menu tidak terpotong.

## Masalah tersisa
- Tidak ada UI untuk memulihkan workspace yang diarsip.
- Tidak ada salin video/film (keputusan user); tidak ada pindah (move) aset.
- Workspace yang diarsip tetap menyimpan file di disk.
- Pindah workspace menutup semua dialog dan menghapus tugas sinkron yang tampil di dock (permintaan tetap berjalan di server).
- `GET /api/jobs` membatasi 10 job terbaru ditambah yang aktif; toast untuk job yang selesai lalu tergeser keluar dari daftar di antara dua polling bisa terlewat (sangat jarang).
- Salin bersifat sinkron; salinan sangat besar (ratusan gambar) belum diukur.

## Revisi 1: hapus workspace + pulihkan arsip (2026-10-20)
Permintaan user setelah bertanya apakah workspace bisa dihapus. Plan/grill direvisi lewat Riwayat (grill revisi 1, temuan 17-29). Menutup dua butir "Masalah tersisa" di atas (tidak ada pulihkan, arsip menyimpan file).
- **Backend**: migrasi v8 (`workspaces.deleted_at`); `POST /api/workspaces/{id}/restore`; `DELETE /api/workspaces/{id}`. Hapus hanya untuk workspace yang sudah diarsip, bukan Utama, bukan yang aktif (header); ditolak 409 bila ada job video berjalan atau film dirender (dicek di bawah `Studio._lock`). Dalam satu transaksi: karakter (+ `character_images`), film, dan referensi video dihapus sungguhan; gambar dan klip hanya ditandai `deleted_at` (barisnya tetap, jadi `committed_today` tidak berubah); workspace menjadi tombstone bernama "Nama (dihapus abc123)" sehingga nama aslinya bisa dipakai lagi. File (gambar, klip, hasil gabung, render film, unggahan referensi) dihapus **setelah commit**; referensi "dari klip" tidak dihapus dua kali karena memakai file klip. `workspaces.get`/`list_all` menyaring tombstone di satu tempat, jadi semua endpoint workspace menolak id terhapus (404 `workspace_missing`).
- **Frontend**: pemilih workspace punya bagian "Arsip (n)" yang bisa dilipat dengan **Pulihkan** dan **Hapus…** (tombol hapus dijauhkan dari Pulihkan); dialog hapus menampilkan isi (gambar, video, karakter, film), memperingatkan tidak bisa dibatalkan dan bahwa catatan biaya tetap, dan tombol merah baru aktif setelah nama workspace diketik persis.
- **Tes**: baru `test_workspace_delete.py` (6 tes): pulihkan, aturan penolakan (belum diarsip, Utama, job berjalan, film dirender), hapus penuh (file hilang dari disk, tak ada baris yatim, `committed_today` sama persis, tombstone dan nama bisa dipakai ulang, semua endpoint menolak id terhapus, salinan di workspace lain utuh dengan `origin_workspace` berlabel "(dihapus …)"), transaksi gagal (trigger memaksa galat: semua file dan baris tetap ada), workspace kosong, migrasi v7 → v8. Lima asersi versi DB diperbarui ke 8. `make test` → **147 passed**; `npm run build` hijau; `fetch(` di frontend tetap satu.
- **Diuji manual oleh user (belum dilakukan)**: (1) arsipkan workspace lalu buka "Arsip" di pemilih → Pulihkan mengembalikannya ke daftar; (2) Hapus… pada workspace berisi aset: dialog menyebut jumlah isi, tombol merah mati sampai nama diketik persis; (3) setelah dihapus: file di folder `data/` berkurang, "biaya hari ini" tidak turun, nama yang sama bisa dibuat lagi, salinan yang pernah dibuat ke workspace lain tetap tampil dan menyebut "dihapus"; (4) hapus saat ada video masih diproses di workspace itu → pesan 409; (5) di dua tab: hapus workspace yang sedang dibuka di tab lain → tab itu kembali ke Utama dengan toast.
- Tersisa: penghapusan ratusan file berjalan sinkron di request; jendela balapan sangat sempit untuk unggahan baru tepat saat penghapusan (diterima, grill 20).

## Riwayat
- 2026-10-20: revisi 1, hapus workspace + pulihkan arsip.
- 2026-10-20: implementasi selesai; menunggu uji manual user.
