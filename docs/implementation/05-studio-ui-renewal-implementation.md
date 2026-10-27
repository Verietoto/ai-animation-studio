# 05 - Studio UI Renewal (Implementation)

Plan: `docs/plan/05-studio-ui-renewal-plan.md`
Grill: `docs/grill/05-studio-ui-renewal-grill.md`

Status: **kode selesai, build dan tes backend hijau; uji frontend menunggu user** (aturan baru di `CLAUDE.md`: pengujian frontend dikerjakan user).

## Yang dibangun
- **Design system + shell** (fase 1): token CSS, font self-host (Inter, JetBrains Mono), sidebar ikon, topbar dengan chip biaya hari ini, layout kanvas + inspector (drawer di bawah 1024px), routing lewat `location.hash` (`#/create`, `#/edit`, `#/characters`, `#/library`, `#/storyboard`). Empat halaman lama dipindah ke layout baru; strip aset dengan drag-drop, tempel (paste), dan unggah; pembanding sebelum/sesudah dengan slider; referensi edit foto dipilih dengan klik (maks 4).
- **Katalog model + harga** (fase 1b, revisi 2): `GET /api/catalog/video|image`, kartu harga dari estimator yang sama dengan `/api/estimate`, `ModelPicker` + panel katalog (cari, filter provider, urut termurah, "hanya yang bisa dipilih", perbarui harga). Dipasang di Gambar→Video, Extend, Edit Foto, Character sheet. Model yang tak cocok tampil nonaktif dengan alasan.
- **Antrian job live** (fase 2): `useClips` (satu-satunya polling, 4 dtk bila ada job aktif), `QueueDock` (job aktif + 10 terakhir, waktu berjalan, biaya), toast `sonner`, notifikasi browser saat tab tersembunyi, tugas sinkron (edit foto, character sheet) tampil lewat `useTrack`. Halaman Create tidak lagi pindah ke Library setelah submit.
- **Library terpadu + Lightbox** (fase 3): satu grid gambar + video + karakter, filter, cari, video dimuat malas dan diputar saat hover, Lightbox dengan jejak asal, Edit / Jadikan video / Extend / Gabung rantai / Ke storyboard / Unduh, fokus terkunci dan kembali ke kartu asal.
- **Storyboard** (fase 4): backend `films` (CRUD, render asinkron di thread latar, status, timeout, deteksi basi, peringatan rasio aspek, pemulihan render terputus), UI daftar film + player + timeline yang bisa diurut (dnd-kit, pointer dan keyboard) + kolam klip. `Storyboard` dimuat dengan `React.lazy` (chunk 55 kB terpisah).
- **Prompt helper + palette + shortcut** (fase 5): preset kamera/gaya/cahaya, riwayat 20 prompt (`localStorage`, try/catch), command palette `cmdk` (⌘K), shortcut `1`-`5`, `/`, `Q`, `⌘↵`.
- **Polish** (fase 6): `prefers-reduced-motion`, dock dan sidebar di layar sempit, empty state.

## File yang diubah
- Backend: `backend/app/db.py` (tabel `films`, migrasi v5: `clips.duration`), `media.py` (parameter `timeout` opsional), `service.py` (`films`, `video_catalog`, `image_catalog`, durasi saat unduh, `recover`), `main.py` (endpoint katalog + films), `openrouter.py` (`list_all_image_models`), `pricing.py` (`video_price_card`, `image_price_card`); baru `films.py`.
- Tes: baru `test_catalog.py`, `test_films.py`; diubah `test_characters.py`, `test_cost_guard.py` (ekspektasi versi DB terbaru 4 → 5).
- Frontend: ditulis ulang `App.tsx`, `styles.css`, `components.tsx`, semua `pages/*`; diubah `api.ts`, `estimate.tsx` (hanya markup + `Portal`), `main.tsx`, `package.json`; baru `ui.tsx`, `catalog.tsx`, `queue.tsx`, `lightbox.tsx`, `prompts.ts`, `prompthelper.tsx`, `palette.tsx`, `pages/Storyboard.tsx`.
- Dokumen/aturan: `CLAUDE.md` (larangan uji frontend oleh agent), plan dan grill 05 (revisi lewat Riwayat).
- Dependency baru: `lucide-react`, `sonner`, `cmdk`, `@dnd-kit/core|sortable|utilities`, `@fontsource-variable/inter|jetbrains-mono`.

## Penyimpangan dari plan (dan alasannya)
- `media.merge_videos` mendapat parameter `timeout` opsional (plan: dipakai tanpa diubah). Perlu agar render film tidak menggantung; perilaku `merge_chain` tidak berubah (default `None`).
- Modal (konfirmasi biaya, katalog) di-render lewat `Portal` ke `document.body`: `backdrop-filter` pada inspector mengurung `position: fixed`. Logika `useConfirmedRun`/`ConfirmDialog` tidak berubah.
- Pemilih model Edit Foto dan Character sheet kini hanya model yang bisa dipilih dari katalog; sebelumnya boleh mengetik id model bebas. Server tetap memvalidasi.
- Endpoint poster klip tidak dibuat; kartu memakai `<video preload="metadata">` yang dimuat malas (keputusan grill: ukur dulu). Belum diukur dengan banyak klip.
- Pemuatan malas harga katalog gambar (bila > 60 model) tidak dibuat: jumlah model nyata belum diketahui. Katalog gambar mengambil semua `/endpoints` paralel (maks 6) dengan cache 5 menit.
- Aksi "Ke storyboard" di Lightbox menambah ke film terbaru (membuat "Film baru" bila belum ada), bukan membuka pemilih film.
- `chars` (daftar karakter) dimuat di `App` dan disegarkan tiap ganti halaman, supaya Library dan Lightbox tidak memuat sendiri-sendiri.

## Temuan grill yang sudah ditangani
- 1 pengaman biaya: bukti grep, semua pemanggilan `api.createClip|extend|editImage|makeSheet` hanya di dalam callback `useConfirmedRun` (`Generate.tsx:25`, `EditPage.tsx:62`, `lightbox.tsx:63`, `Characters.tsx:66`); ⌘↵ hanya menekan tombol generate dan diabaikan bila ada dialog terbuka.
- 2 dan 4 rasio aspek + hasil render basi: `warnings` di `GET /api/films/{id}`, kolom `rendered_ids`, `stale`, file render lama dihapus (tes `test_aspect_ratio_mismatch_is_warned`, `test_stale_after_edit_and_old_render_file_removed`).
- 3 render asinkron: 202 + polling, satu render per film, timeout 600 dtk per perintah ffmpeg, render terputus ditandai gagal saat startup (tes `test_render_is_async...`, `test_failed_render...`, `test_interrupted_render...`).
- 5 durasi klip: `clips.duration` diisi saat unduh dan malas untuk klip lama (`test_clip_duration_saved_on_download`).
- 6 `created_at`/`kind` sudah ada di `public_clip`; tidak ditambah.
- 7 batas 200: Library menampilkan catatan bila jumlah mencapai 200.
- 8 integritas `clip_ids`: validasi id, maks 50, duplikat boleh, render memeriksa ulang status/file (tes `test_crud_order_and_validation`, `test_render_rejects_empty_and_unfinished`).
- 9 font self-host: `@fontsource-variable/*`, tanpa Google Fonts.
- 11-18 katalog: harga dari estimator yang sama (tes kesamaan kartu vs `/api/estimate`), minimum per generasi sebagai catatan (tes Aleph), kegagalan satu `/endpoints` tidak menjatuhkan katalog, model teks-saja tampil nonaktif, kategori hanya label.
- Edge case: hash tak dikenal jatuh ke `#/create`; gambar terpilih yang hilang dianggap kosong; paste di input teks tidak dicegat; shortcut diabaikan saat mengetik atau saat dialog terbuka; status klip yang loncat tetap memunculkan toast (dibandingkan dengan status sebelumnya).

## Pengujian (perintah dan hasil nyata)
- `make test` → **100 passed** (77 passed sebelum pekerjaan ini setelah `ffmpeg` dipasang; tambahan: 12 `test_catalog`, 11 `test_films`). Dua tes lama diubah hanya pada angka versi DB.
- `cd frontend && npm run build` (tsc + vite) → hijau; chunk utama 295 kB (gzip 93 kB), `Storyboard` 55 kB terpisah.
- `ffmpeg` tidak terpasang di mesin ini pada awal pekerjaan (42 tes error); dipasang `brew install ffmpeg` dengan persetujuan user.
- Pengamatan agent di browser **sebelum** user meminta berhenti (bukan pengujian resmi): fase 1-4 dijalankan dengan fake OpenRouter dan data sementara di luar repo: shell, picker katalog, dialog konfirmasi biaya ($0,12) → klip selesai, dock + toast, Library + Lightbox (jejak asal, Esc, fokus kembali), Storyboard (2 adegan, render, urut lewat keyboard tersimpan dan film ditandai perlu render ulang). Dua bug ditemukan dan diperbaiki saat itu (tombol "Pengaturan" muncul di desktop; modal terkurung `backdrop-filter`). Prompt helper, ⌘K, shortcut, tampilan 390px, dan drag dengan mouse **belum pernah dijalankan**.
- **Diuji manual oleh user (belum dilakukan)**, alur yang perlu dicoba:
  1. Upload lewat tombol +, seret file, dan tempel dari clipboard; pilih model dari katalog; dialog biaya muncul juga lewat ⌘↵; setuju → job muncul di dock, toast saat selesai, cek biaya hari ini.
  2. Edit Foto: referensi klik (maks 4), hasil dengan slider sebelum/sesudah, "Jadikan video".
  3. Karakter: buat karakter, character sheet (tampil di dock selama berjalan).
  4. Library: filter/cari, hover memutar video, Lightbox + jejak asal, Extend, Gabung rantai, Ke storyboard, Unduh.
  5. Storyboard: urut dengan mouse (belum teruji), render, tanda "perlu render ulang", peringatan rasio berbeda, hapus film.
  6. Palette ⌘K, shortcut `1`-`5`, `/`, `Q`, riwayat prompt, chip preset.
  7. Lebar 390px dan `prefers-reduced-motion`.
  8. Katalog dengan API key asli: jumlah model gambar nyata dan waktu muat; harga dibandingkan dengan halaman OpenRouter.

## Masalah tersisa
- `npm audit`: 2 temuan (esbuild/vite 5, hanya server dev), sudah ada sebelum pekerjaan ini; perbaikannya butuh vite 8 (breaking), tidak dikerjakan.
- Tidak ada test frontend otomatis (sesuai plan: tanpa framework uji).
- Notifikasi dan toast dobel bila aplikasi dibuka di dua jendela (diterima di grill).
- Katalog gambar bisa lambat dengan banyak model (belum diukur dengan API asli).
- Tiru Gerakan (plan 03) belum punya UI; bisa memakai `ModelPicker`/`Stage` baru.
- File di `.claude/` yang tidak terkait (agent yang dihapus di working tree, aturan proyek lain) tidak disentuh.

## Revisi 3: hapus gambar, klip, karakter (2026-10-20)
Permintaan user: "kamu lupa tombol delete". Plan/grill 05 direvisi lewat Riwayat (grill temuan 19-25).
- **Backend:** `DELETE /api/images/{id}`, `/api/clips/{id}`, `/api/characters/{id}`; migrasi v6 menambah `deleted_at` pada `images` dan `clips` (soft delete: baris dan catatan biaya tetap, file di disk dihapus). `get_image`/`get_clip` dan daftar memfilter `deleted_at`, sehingga extend/edit/motion/karakter menolak aset terhapus. Aturan tolak 409: klip masih diproses, klip punya lanjutan extend, gambar dipakai karakter atau job berjalan, klip ada di film yang sedang dirender (dicek sebelum perubahan apa pun). Klip yang dihapus otomatis dilepas dari semua film.
- **Frontend:** tombol Hapus dengan konfirmasi dua langkah di Lightbox (gambar dan video) dan di kartu karakter; thumbnail sumber di dock disembunyikan bila gambarnya sudah dihapus.
- **Tes:** `test_delete.py` (8 tes: biaya tetap tercatat setelah hapus, file terhapus, blokir karakter/job/lanjutan/film rendering, pelepasan dari film, migrasi v5→v6). `make test` → **108 passed**; `npm run build` hijau. Tiga tes versi DB diperbarui ke 6.
- **Diuji manual oleh user:** Hapus gambar dan video dari Lightbox (konfirmasi dua langkah, pesan galat 409 tampil), hapus karakter, klip hilang dari film di Storyboard, biaya hari ini tidak turun setelah hapus.
- Tidak ada tempat sampah/undo; tidak ada hapus massal.

## Riwayat
- 2026-10-20: revisi 3, hapus gambar/klip/karakter.
- 2026-10-20: implementasi fase 1-6 selesai; menunggu uji manual user.
