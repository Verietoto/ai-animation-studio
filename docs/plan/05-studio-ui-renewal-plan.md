# 05 - Studio UI Renewal (Plan)

- Status: disetujui user (2026-10-19), sudah digrill (lihat `docs/grill/05-studio-ui-renewal-grill.md`), revisi 2 (katalog model) menunggu persetujuan ulang sebelum implementasi
- Tanggal: 2026-10-19
- Asal: permintaan user "renew ui dan fungsionalitasnya menjadi jauh lebih bagus, yg sekarang jelek, kurang futuristik, kurang function".

## Tujuan
Mengganti UI tab + form polos (`frontend/src/`, sekitar 600 baris, `styles.css` 37 baris) dengan workspace bergaya studio profesional yang futuristik, dan menambah fungsi yang hilang: status job yang selalu terlihat, library aset yang enak dijelajah, dan cara menyusun klip menjadi film pendek.

Keputusan user (2026-10-19):
- Gaya **pro studio ala Runway/Pika**: sidebar ikon kiri, kanvas preview besar di tengah, panel inspector kanan, dock antrian job di bawah. Gelap, glass panel, aksen gradien ungu ke cyan, glow tipis.
- Fitur baru: antrian job live, library aset terpadu, storyboard/timeline film, prompt helper + command palette + shortcut.
- Dependency frontend boleh ditambah.

## Ruang lingkup (termasuk yang TIDAK dikerjakan)
Termasuk:
- Design system baru (token CSS, font, komponen dasar) dan shell layout.
- Port halaman yang ada: Gambar ke Video, Edit Foto, Karakter, Library.
- Fitur baru: QueueDock, Library terpadu + Lightbox + lineage, Storyboard (backend + UI), prompt helper, command palette, shortcut keyboard.

Tidak termasuk:
- UI "Tiru Gerakan" (plan 03); dibuat di plan 03 memakai desain baru ini.
- Hapus aset, multi-user, login.
- Editor timeline tingkat lanjut (trim, transisi, musik latar, teks). Storyboard hanya urutan + render gabung.
- Aturan di `.claude/CLAUDE.md` (Spaceship: i18n, `useFormat`, pnpm, Postgres) tidak berlaku; berasal dari proyek lain.

## Desain / pendekatan

### Dependency baru (frontend)
- `lucide-react` (ikon), `sonner` (toast), `cmdk` (command palette), `@dnd-kit/core` + `@dnd-kit/sortable` (drag urutan storyboard, bisa dipakai lewat keyboard).
- Tidak dipakai: Tailwind (token CSS cukup), framer-motion (transisi CSS cukup), react-router (state + `location.hash`). Ditambah bila nanti terbukti kurang.

### Shell & design system
- `styles.css` ditulis ulang: token di `:root` (surface 0/1/2, line, text, muted, gradien aksen `#8b5cf6` ke `#22d3ee`, ok/warn/bad, radius, shadow glow), font Inter + JetBrains Mono untuk angka/biaya (Google Fonts di `index.html`). Glass panel = `backdrop-filter: blur` + border semi-transparan. Fokus terlihat, `prefers-reduced-motion` dihormati.
- Grid layout: `sidebar (64px) | workspace | inspector (360px)` + queue dock di bawah (bisa diciutkan). Di layar < 1024px inspector menjadi drawer.
- `App.tsx` menjadi shell: `Sidebar`, area halaman, `QueueDock`, `CommandPalette`, `<Toaster/>`. Halaman aktif di `location.hash` (`#/create`, `#/edit`, `#/characters`, `#/library`, `#/storyboard`).
- Komponen bersama baru di `frontend/src/ui.tsx`: `Panel`, `Field`, `Button` (primary gradien / ghost), `Pill`, `Dropzone`, `Lightbox`, `EmptyState`. `useAsync`, `ImagePicker`, `ModelParams` di `components.tsx` direstyle, tidak ditulis ulang.
- Logika `estimate.tsx` (`useEstimate`, `useConfirmedRun`, `ConfirmDialog`) tidak diubah, hanya markup/kelas. Estimasi biaya tampil sebagai "cost chip" di bawah tombol generate.

### Halaman yang di-port
- **Create (Gambar ke Video)**: kanvas = gambar terpilih ukuran besar; strip aset di bawah kanvas plus Dropzone (drag-drop/paste); inspector = prompt, model, parameter, cost chip, tombol Generate. Setelah submit tetap di halaman; job muncul di QueueDock + toast.
- **Edit Foto**: kanvas before/after dengan slider pembanding; referensi tambahan dipilih dengan klik di strip aset (maks 4), menggantikan `<select multiple>`.
- **Karakter**: grid kartu karakter + sheet; form buat karakter di inspector.

### Fitur baru
1. **QueueDock** (`frontend/src/queue.tsx`): state klip pindah dari `Library` ke hook `useClips()` di App (polling 4 detik hanya bila ada job aktif, logika sama dengan `Library.tsx` sekarang). Dock menampilkan job aktif + 10 terakhir: thumbnail sumber, model, status, waktu berjalan (dari `created_at`), biaya. OpenRouter tidak memberi persentase, jadi tidak ada progress bar palsu; indikator indeterminate. Perubahan status memicu toast + `Notification` browser bila tab tidak fokus dan izin diberikan. Edit foto/sheet (sinkron) tampil sebagai item "berjalan" selama request. Backend: `created_at` dan `kind` ikut di `public_clip` bila belum.
2. **Library terpadu** (`pages/Library.tsx`): satu grid gambar + klip; filter Semua/Gambar/Video/Karakter, cari di prompt, urut terbaru. Klik membuka Lightbox (gambar penuh / player) dengan detail (prompt, model, biaya, ukuran) dan aksi: Edit, Jadikan video, Extend, Gabung rantai, Tambah ke storyboard, Unduh. Lineage (`parent_image_id`, `source_image_id`, `parent_clip_id`) tampil sebagai jejak yang bisa diklik. Kartu klip memutar video saat hover (muted). Alur extend `ClipCard` dipindah ke Lightbox.
3. **Storyboard** (`pages/Storyboard.tsx` + backend):
   - Tabel `films(id, title, clip_ids TEXT JSON, merged_path, created_at, updated_at)`, migrasi `user_version` 5 di `backend/app/db.py` (pola v2 sampai v4).
   - Endpoint: `GET/POST /api/films`, `GET/PUT/DELETE /api/films/{id}`, `POST /api/films/{id}/render`, `GET /api/films/{id}/file`.
   - `render_film` di `service.py`: semua klip harus `completed` dan punya file, lalu `media.merge_videos` (sama seperti `merge_chain`). Pesan jelas bila ffmpeg tidak ada.
   - UI: kiri daftar film; tengah player hasil render; bawah timeline horizontal kartu adegan (thumbnail, durasi, prompt) yang bisa di-drag urut, dihapus, dan ditambah dari panel library mini. Total durasi ditampilkan. Render tidak memanggil AI (gratis), jadi tanpa dialog biaya.
4. **Prompt helper + command palette**:
   - `frontend/src/prompts.ts`: preset statis (kamera: dolly in, orbit, pan, crane up, handheld; gaya: sinematik, anime, claymation, film noir; pencahayaan) sebagai chip yang menambah frasa ke prompt. Riwayat 20 prompt terakhir di `localStorage` (dibungkus try/catch).
   - `palette.tsx` (`cmdk`, ⌘K/Ctrl+K): pindah halaman, buka aset terakhir, buat film baru, fokus prompt, buka antrian.
   - Shortcut: `1` sampai `5` pindah halaman, `⌘↵` generate (selalu membuka dialog konfirmasi biaya, tidak pernah melewatinya), `/` fokus prompt, `Q` buka/tutup dock, `Esc` tutup lightbox/palette. Diabaikan saat fokus di input kecuali `⌘↵`/`Esc`.

### File
- Diubah: `frontend/src/App.tsx`, `styles.css`, `components.tsx`, `estimate.tsx` (markup), `pages/*.tsx`, `api.ts`, `frontend/index.html`, `frontend/package.json`; `backend/app/db.py`, `service.py`, `main.py`.
- Baru: `frontend/src/ui.tsx`, `queue.tsx`, `prompts.ts`, `palette.tsx`, `pages/Storyboard.tsx`; `backend/tests/test_films.py`.
- Dipakai ulang: `useAsync`, `useEstimate`, `useConfirmedRun`, `ConfirmDialog`, `money`; `media.merge_videos`, `Database.insert/update/_migrate`, pola `merge_chain`.

## Langkah kerja
Tiap fase berakhir dengan build hijau dan app yang bisa dipakai.
1. Dependency + token CSS + shell (Sidebar, hash routing, layout inspector) + `ui.tsx`; port 4 halaman lama.
2. `useClips` + QueueDock + toast/notifikasi; field backend tambahan.
3. Library terpadu + Lightbox + lineage + Dropzone.
4. Storyboard: backend (migrasi, endpoint, `render_film`, test), lalu UI.
5. Prompt helper, command palette, shortcut.
6. Polish: responsif < 1024px, reduced motion, empty state, fokus a11y.

## Kriteria selesai
- `make test` hijau, termasuk `backend/tests/test_films.py`: CRUD, urutan, render menolak klip belum selesai, render sukses (bila ffmpeg ada), migrasi v4 ke v5 pada DB lama.
- `cd frontend && npm run build` hijau.
- Uji end-to-end manual dengan `make dev` + `scripts/fake_openrouter.py` (tanpa biaya): upload drag-drop, generate video (dialog biaya muncul, juga lewat ⌘↵), job muncul di dock, toast saat selesai, buka di Library lightbox, extend, tambah 2+ klip ke storyboard, drag urut, render, putar hasil.
- Screenshot desktop dan lebar 390px tercatat di `docs/implementation/05-*`.
- Alur biaya/konfirmasi plan 04 tetap berjalan di semua halaman.

## Pertanyaan terbuka
- Apakah `media.merge_videos` menormalisasi klip beda resolusi/rasio/fps/audio dari model berbeda? Dicek di grill; bila tidak, render menolak dengan pesan jelas.
- Perlu tombol hapus film/adegan saja, atau juga hapus aset? Plan ini hanya hapus film dan lepas adegan.

## Revisi 2 (2026-10-19): katalog model + harga di setiap section
Permintaan user: "di setiap section (misal edit video, gambar) semua model yang tersedia di openrouter dan harganya di kasih list". Semua keputusan grill 05 nomor 1 sampai 10 diadopsi apa adanya.

### Tujuan
Di setiap tempat user memilih model, tampil daftar **semua** model OpenRouter untuk jenis itu (video atau gambar) beserta harganya, bisa dicari dan diurutkan, sehingga user bisa membandingkan sebelum memilih. Model yang tidak cocok untuk section itu tetap terlihat tetapi nonaktif dengan alasannya.

| Section | Katalog | Bisa dipilih bila |
|---|---|---|
| Create (Gambar ke Video) | video | `supported_frame_images` berisi `first_frame` |
| Extend (di Lightbox) | video | sama dengan Create |
| Edit Foto | gambar | menerima input gambar (`input_modalities` berisi `image`) |
| Karakter (sheet) | gambar | sama dengan Edit Foto |
| Tiru Gerakan (plan 03, nanti) | video | daftar model motion di config; dipakai ulang tanpa perubahan |

Model video tanpa `first_frame` (mis. `flux-video-edit`, `runway/aleph-2`, `flux-video-upscale`, `heygen/avatar-iv`) tampil dengan label kategori ("edit video", "upscale", "avatar") dan alasan nonaktif. Model gambar teks-saja tampil sebagai "hanya teks ke gambar".

### Backend
- `GET /api/catalog/video` dan `GET /api/catalog/image` di `main.py`, logika di `service.py` (`video_catalog`, `image_catalog`), perhitungan harga di `pricing.py` (`price_card_video`, `price_card_image`). Endpoint `/api/models/*` lama tetap (dipakai validasi dan estimasi).
- Bentuk satu baris katalog:
  - `id`, `name`, `provider` (awalan id), `description` (dipotong), `category` (`i2v`, `edit`, `upscale`, `avatar`, `image_edit`, `text_to_image`), `capabilities` (`first_frame`, `last_frame`, `audio`, durasi/resolusi/rasio yang didukung, jumlah referensi maks), `selectable_for` (daftar section), `disabled_reason`.
  - `price`: `{unit_label, rows: [{label, usd, confidence}], example: {label, low, high, confidence}, note}`.
    - Video: satu baris per resolusi yang didukung, harga per detik tanpa dan dengan audio (bila beda), dihitung dengan **`pricing.estimate_video` yang sudah ada** pada durasi 1 detik, ditambah contoh "5 detik, resolusi terendah". Model token (Seedance) bertanda `formula` dengan rasio 16:9; minimum per generasi dan biaya gambar input ditampilkan sebagai catatan. SKU yang tidak dikenal -> baris `unknown`, tidak ditebak.
    - Gambar: harga per satuan apa adanya dari `pricing` endpoint (per gambar / per megapiksel / per token), plus contoh "1 gambar, 1 referensi" dari **`pricing.estimate_image` yang sudah ada** (memakai riwayat biaya bila ada). Beberapa provider -> rentang min sampai maks.
  - `fetched_at` untuk seluruh katalog.
- Katalog gambar butuh `/images/models` **tanpa filter** (method baru `list_all_image_models` di `openrouter.py`; `list_image_models` lama tidak diubah) plus `/images/models/{id}/endpoints` per model: diambil paralel (`ThreadPoolExecutor`, maks 6), memakai `_endpoint_cache` yang sudah ada (5 menit). Gagal pada satu model -> harga model itu `unknown` dengan alasan, katalog tetap tampil.
- `?refresh=1` melewati cache (tombol "perbarui harga").

### Frontend
- Komponen `ModelPicker` di `components.tsx`, menggantikan `<select>` di `ModelParams` dan `<input list>` di Edit Foto/Karakter. Tampilan: tombol di inspector menunjukkan model terpilih + harga ringkas; klik membuka panel/drawer katalog: pencarian, filter (bisa dipilih saja / semua, provider, audio, last frame), urut (harga contoh termurah, nama, terbaru), kartu tiap model berisi tabel harga per resolusi, chip kemampuan, badge keyakinan harga (`pasti`, `rumus`, `batas atas`, `riwayat`, `tidak diketahui`, pakai teks `CONFIDENCE` di `estimate.tsx`), dan alasan bila nonaktif. "Diambil HH:MM · perbarui".
- Harga katalog adalah **harga daftar**; angka yang mengikat tetap cost chip + dialog konfirmasi (plan 04). Teks ini tertulis di panel.
- Hook `useCatalog(kind)` memakai `useAsync`, dimuat sekali per sesi lalu dibagi antar halaman (state di App), seperti daftar gambar.
- Command palette mendapat aksi "Bandingkan model video/gambar" yang membuka panel katalog.

### Langkah kerja (disisipkan)
- Fase 1b (setelah shell): backend katalog + `test_catalog.py`, lalu `ModelPicker` dipasang di Create, Edit Foto, Karakter. Extend memakainya di fase 3 (Lightbox).

### Kriteria selesai (tambahan)
- `backend/tests/test_catalog.py`: semua 30 model di fixture `video_models.json` menghasilkan kartu harga tanpa exception; nilai per detik dicek tangan untuk minimal 5 model dengan satuan berbeda (sen per detik, USD per detik, token, i2v vs t2v Kling, minimum Aleph); model tanpa `first_frame` nonaktif dengan alasan; katalog gambar tetap tampil bila satu `/endpoints` gagal; harga kartu sama dengan `POST /api/estimate` untuk parameter yang sama.
- Tiap section menampilkan seluruh model jenisnya, termasuk yang nonaktif, terbukti lewat screenshot.

## Riwayat
- 2026-10-19: draft pertama.
- 2026-10-19: plan disetujui user. Setelah grill (`docs/grill/05-studio-ui-renewal-grill.md`), bagian "Keputusan setelah grilling" di dokumen itu menimpa plan ini bila bertentangan. Ringkas: font self-host (`@fontsource-variable/*`, bukan Google Fonts); `created_at`/`kind` sudah ada di `public_clip` (langkah dihapus); `films` + kolom `render_status`/`render_error`/`rendered_ids` dan `clips.duration` di migrasi v5; render film asinkron (202 + polling, timeout, satu render per film); peringatan rasio aspek berbeda; `Storyboard` di-`React.lazy`; bukti `grep` tak ada pemanggilan berbayar di luar `useConfirmedRun`.
- 2026-10-20: revisi 3 (permintaan user: "kamu lupa tombol delete"): tombol hapus untuk gambar, klip, dan karakter (sebelumnya "hapus aset" ada di luar lingkup). Soft delete lewat kolom `deleted_at` (migrasi v6) agar catatan biaya dan batas harian tidak hilang; file di disk dihapus; `DELETE /api/images|clips|characters/{id}`; tombol Hapus dengan konfirmasi dua langkah di Lightbox dan kartu karakter. Aturan blokir dan alasannya di grill 05 bagian "Grill revisi 3".
- 2026-10-19: revisi 2, katalog model + harga di setiap section (bagian "Revisi 2"), digrill di grill 05 bagian "Grill revisi 2". Menunggu persetujuan ulang.
