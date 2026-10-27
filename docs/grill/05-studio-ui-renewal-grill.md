# 05 - Studio UI Renewal (Grill)

Plan terkait: `docs/plan/05-studio-ui-renewal-plan.md`

Keparahan: **T** tinggi, **S** sedang, **R** rendah. Temuan bertanda (kode) sudah dicek langsung di repo.

## Lubang pada plan
1. **(T) Rewrite UI tanpa test frontend bisa merusak pengaman biaya (plan 04).** Semua halaman memanggil `useConfirmedRun`; satu jalur baru (⌘↵, tombol di Lightbox, extend yang pindah ke Lightbox) yang memanggil `api.createClip`/`api.extend`/`api.editImage` langsung akan melewati dialog konfirmasi. Server menolak tanpa `confirmed_cost` (409), jadi dampaknya "job gagal diam-diam", bukan biaya bocor, tetapi tetap bug fatal bagi pengguna.
   - Mitigasi: semua pemanggilan berbayar hanya lewat `useConfirmedRun`; ⌘↵ memanggil `runner.start` yang sama dengan tombol. `grep` di akhir fase: tidak ada `api.createClip|extend|editImage|makeSheet` di luar callback `useConfirmedRun`. Dicatat sebagai uji di file implementation.
2. **(T) Plan mengira `merge_videos` "menormalisasi" semuanya; kenyataannya (kode `media.py:106`) hanya menyamakan ke resolusi klip pertama dengan letterbox (pad hitam), fps 24, dan audio senyap bila kosong.** Klip beda rasio (16:9 lalu 9:16) menghasilkan bar hitam besar tanpa peringatan. Setiap klip di-encode ulang (`libx264 veryfast`), jadi render film 10 klip bisa makan puluhan detik.
   - Mitigasi: `render_film` membaca `probe` tiap klip; bila rasio aspek berbeda (> 2%), UI menampilkan peringatan sebelum render ("klip 3 berbeda rasio, akan diberi bar hitam") dan user boleh lanjut. Render dijalankan sebagai tugas latar (nomor 3), bukan request sinkron.
3. **(T) Render sinkron di request HTTP.** `_run` memakai `subprocess.run` tanpa timeout; endpoint sinkron memegang satu thread, proxy/browser bisa timeout sebelum selesai, dan dua render bersamaan pada film sama saling menimpa.
   - Mitigasi: `POST /render` langsung membalas 202 dengan `render_status` (`idle|rendering|done|failed`) di tabel `films`; render jalan di thread latar (pola `Studio.start/_loop` yang sudah ada); satu render per film (409 bila sedang jalan); UI polling lewat hook yang sama dengan `useClips`. Timeout ffmpeg ditambahkan khusus jalur ini (mis. 10 menit) tanpa mengubah perilaku `merge_chain`.
4. **(S) Hasil render bisa basi.** User mengubah urutan/menambah adegan setelah render; `merged_path` lama tetap tampil seolah terbaru.
   - Mitigasi: kolom `rendered_ids` (JSON urutan saat render). UI menandai "sudah berubah sejak render terakhir" bila `rendered_ids != clip_ids`. File render lama dihapus saat render ulang berhasil (`merge_chain` tidak menghapus file lama, jadi file yatim menumpuk; film tidak boleh mewarisi kebiasaan itu).
5. **(S) Durasi klip tidak tersimpan.** `params.duration` bisa kosong ("default" model), jadi "total durasi" di timeline akan salah atau kosong.
   - Mitigasi: kolom `clips.duration` (migrasi v5 bersama `films`), diisi lewat `media.probe` saat `_download` sukses; klip lama diisi malas (probe saat pertama dibutuhkan lalu disimpan). UI menampilkan "?" bila belum ada, bukan angka tebakan.
6. **(S) Plan menyuruh "tambah `created_at` dan `kind` ke `public_clip`" (kode).** `public_clip` hanya membuang `path`/`merged_path`, jadi `created_at`, `kind`, `params`, `updated_at` sudah ikut. Langkah itu tidak perlu. Yang kurang adalah thumbnail: tidak ada endpoint poster untuk klip.
   - Mitigasi: `<video preload="metadata" muted>` dengan lazy mount (IntersectionObserver) di grid; bila terasa berat (> 40 klip), tambah `GET /api/clips/{id}/poster` (ffmpeg frame pertama, dicache di storage). Diputuskan di fase 3 berdasarkan pengukuran, dicatat di implementation.
7. **(S) List dibatasi 200 baris** (`LIMIT 200` untuk images dan clips). Library terpadu akan diam-diam memotong aset lama.
   - Mitigasi: UI menampilkan "menampilkan 200 terbaru" bila jumlah == 200; pagination di luar lingkup, dicatat sebagai batas yang diketahui.
8. **(S) Integritas `clip_ids` (JSON dalam satu kolom).** `PUT` bisa menyimpan id yang tidak ada atau klip `failed`. Klip yang sama boleh dipakai dua kali dalam film (sengaja), jadi duplikat bukan kesalahan.
   - Mitigasi: `PUT` memvalidasi semua id ada di `clips` (422), mengizinkan duplikat, batas 50 adegan. Render memvalidasi ulang status `completed` + file ada di disk (klip bisa `failed_download`; file bisa hilang manual).
9. **(S) Font dari Google Fonts.** Aplikasi lokal/offline; tanpa jaringan font jatuh ke system-ui dan layout bergeser; selain itu request ke pihak ketiga dari app yang menangani gambar pribadi.
   - Mitigasi: self-host lewat `@fontsource-variable/inter` dan `@fontsource-variable/jetbrains-mono` (impor di `main.tsx`), tanpa `<link>` eksternal.
10. **(R) Aturan repo yang tidak cocok.** `.claude/CLAUDE.md` (Spaceship) dan `.claude/rules/node.md` (CommonJS, ECC) bukan untuk repo ini; frontend ini TypeScript/ESM.
    - Mitigasi: diabaikan; yang berlaku `CLAUDE.md` root. Membersihkan file itu adalah pekerjaan terpisah.

## Risiko
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| Regresi alur biaya (nomor 1) | Tinggi | Sedang | Satu pintu `useConfirmedRun`, grep di akhir, uji manual tiap halaman |
| Render film lama/menggantung (nomor 3) | Sedang | Sedang | Thread latar, status, timeout, satu render per film |
| `backdrop-filter` + banyak `<video>` membuat UI patah-patah | Sedang | Sedang | Blur hanya di panel besar; video grid lazy; ukur di fase 3 |
| Bundle membesar (lucide, dnd-kit, cmdk) | Rendah | Tinggi | Impor ikon per nama, `npm run build` melaporkan ukuran; `Storyboard` dengan `React.lazy` |
| Notifikasi browser ditolak/diblok | Rendah | Tinggi | Toast tetap jalur utama; notifikasi hanya bonus |
| Dependency baru punya kerentanan/breaking | Rendah | Rendah | Versi terkunci di `package-lock.json`, `npm audit` dicatat |
| Migrasi v5 merusak DB lama | Tinggi | Rendah | Pola `_migrate` idempoten + tes membuka salinan DB skema v4 |

## Edge case
- Hash tidak dikenal (`#/foo`) atau kosong -> jatuh ke `#/create`; tombol back browser berpindah halaman.
- Gambar terpilih (`selected`) tidak ada di daftar (DB baru) -> kanvas menampilkan empty state, bukan gambar rusak.
- Upload bukan gambar / terlalu besar lewat Dropzone atau paste -> pesan error server tampil, Dropzone tidak macet di state "drag".
- Paste di input/textarea tidak boleh dicegat Dropzone.
- Shortcut `1-5` dan `/` tidak aktif saat fokus di input/select/textarea atau saat dialog/palette terbuka. ⌘↵ saat dialog biaya sudah terbuka tidak membukanya dua kali.
- Dua tab browser: polling dan notifikasi ganda (diterima). Riwayat prompt di `localStorage` saling menimpa (diterima).
- Status klip meloncat `submitted -> completed` di antara dua polling: toast tetap muncul (bandingkan status sebelumnya dari state, bukan dari event).
- Lightbox: fokus terkunci di dalam, `Esc` menutup, fokus kembali ke kartu asal; video berhenti saat ditutup.
- Storyboard kosong: Render nonaktif; satu adegan boleh dirender.
- Hapus film saat sedang render: ditolak 409.
- Layar 390px: inspector jadi drawer, timeline scroll horizontal, dock ciut jadi satu baris; tidak ada fungsi yang hanya bisa lewat hover (ketuk membuka Lightbox).
- `prefers-reduced-motion`: animasi dock, glow berdenyut, dan putar-otomatis hover dimatikan.

## Potensi bug
- `useClips` dipindah ke App: bila `Library` dan dock punya interval sendiri, polling dobel. Hanya satu interval, di hook.
- `App.tsx` sekarang me-refresh `health` saat ganti tab. Dengan hash routing tetap harus refresh saat halaman berganti **dan** setelah job selesai (biaya aktual masuk).
- `key.current = crypto.randomUUID()` (idempotency) di `Generate.tsx`: setelah form dipecah ke inspector, kunci tetap satu per percobaan, bukan per render.
- `ModelParams` memfilter model dengan `first_frame`; pemilih model baru tidak boleh menampilkan model lain.
- dnd-kit: id sortable harus unik; duplikat klip (nomor 8) butuh id adegan sendiri (`${clip_id}:${index}`).
- `crypto.randomUUID` hanya ada di konteks aman (https/localhost); akses via IP LAN error. Sudah begitu sekarang; dicatat, tidak dikerjakan.
- `Toaster` ter-mount dua kali di StrictMode dev tidak boleh menggandakan toast.

## Asumsi yang belum terbukti
- Video klip OpenRouter bisa diputar di `<video>` semua browser (h264/aac). Terbukti sebagian lewat fitur 01; dikonfirmasi lagi di uji manual.
- Render film 5-10 klip berdurasi 5 detik selesai dalam waktu wajar di mesin user. Belum diukur; diukur di fase 4 dan dicatat.
- `cmdk` dan `@dnd-kit` kompatibel dengan React 18.3 + Vite 5. Diverifikasi saat `npm install` + `npm run build` di fase 1.
- Layout tiga kolom terbaca di laptop 1280px (kanvas sekitar 850px). Dicek lewat screenshot.

## Keputusan setelah grilling (perubahan pada plan)
- Dependency tambahan: `@fontsource-variable/inter`, `@fontsource-variable/jetbrains-mono`; Google Fonts dihapus dari rencana `index.html`.
- Dihapus dari plan: "tambah `created_at`/`kind` ke `public_clip`" (sudah ada).
- `films` ditambah kolom `render_status`, `render_error`, `rendered_ids`; `clips` ditambah kolom `duration`; semuanya di migrasi `user_version` 5.
- `POST /api/films/{id}/render` asinkron (202 + polling), satu render per film, dengan timeout; `merge_videos` dipakai ulang tanpa diubah.
- Peringatan rasio aspek berbeda sebelum render.
- Thumbnail klip: mulai dari `<video preload="metadata">` lazy; endpoint poster hanya bila pengukuran menunjukkan perlu.
- Library: batas 200 ditampilkan eksplisit, tanpa pagination.
- `Storyboard` dimuat dengan `React.lazy`.
- Kriteria selesai ditambah: bukti `grep` tidak ada pemanggilan berbayar di luar `useConfirmedRun`; `test_films.py` mencakup render asinkron, `rendered_ids` basi, validasi `PUT`, dan migrasi dari DB v4.

## Grill revisi 2: katalog model + harga
Dicek di kode: `/videos/models` sudah memuat `pricing_skus` (30 model di fixture, satu request); harga gambar hanya ada per model di `/images/models/{id}/endpoints`; `list_image_models` memfilter model tanpa input gambar.

### Lubang
11. **(T) Harga katalog dikira angka tagihan.** Satuan tidak seragam (sen/detik, USD/detik, token video, token gambar, megapiksel); model token hanya bisa "rumus" atau "batas atas". Bila kartu menulis "$0,15" polos, user percaya itu pasti.
    - Mitigasi: setiap angka membawa badge keyakinan; kartu menulis "harga daftar, angka final di dialog konfirmasi"; harga dihitung oleh fungsi estimator yang sama (`estimate_video`/`estimate_image`), jadi kartu dan cost chip tidak bisa berbeda rumus. Tes: kartu == `/api/estimate` untuk parameter sama.
12. **(T) N+1 request untuk katalog gambar.** Satu `/endpoints` per model; puluhan model -> lambat, bisa kena rate limit, dan satu gagal tidak boleh menjatuhkan semuanya.
    - Mitigasi: paralel maks 6, timeout per request yang ada (60 detik) ditambah batas total; hasil di `_endpoint_cache` 5 menit (dipakai ulang oleh estimasi); gagal per model -> `unknown` + alasan. Katalog dimuat sekali per sesi di frontend; UI menampilkan skeleton saat memuat. Bila jumlah model > 60, harga dimuat malas (saat kartu terlihat) lewat `GET /api/catalog/image/{id}`; diputuskan saat implementasi dari jumlah nyata.
13. **(S) Estimator sekarang tidak punya "harga per detik per resolusi"**, hanya total job. Memanggil `estimate_video(duration=1)` per resolusi aman untuk tarif per detik, tetapi `minimum_cents_per_generation` (Aleph $0,56) membuat 1 detik tampak $0,56/detik.
    - Mitigasi: tarif per detik dihitung dengan `minimum` diabaikan (fungsi pembantu kecil di `pricing.py` yang memakai `_per_second`/`_token_rate`), minimum ditampilkan sebagai catatan terpisah; contoh 5 detik memakai `estimate_video` lengkap. Tes khusus Aleph.
14. **(S) Model gambar teks-saja tidak terlihat sekarang** (filter `input_modalities`). Permintaan "semua model" butuh daftar tanpa filter.
    - Mitigasi: method baru `list_all_image_models`; `list_image_models` lama tetap dipakai validasi, jadi model teks-saja tidak pernah bisa dikirim ke endpoint edit walau UI salah.
15. **(S) Banyak provider per model gambar dengan harga berbeda.** OpenRouter yang memilih provider; harga sebenarnya bisa yang mana pun.
    - Mitigasi: tampilkan rentang min sampai maks antar provider dan daftar provider di detail kartu; sama seperti `estimate_image` sekarang (low = min, high = max).
16. **(S) Urut "termurah" tidak adil antar satuan** (per detik vs per gambar vs token tanpa batas).
    - Mitigasi: urut memakai `example.high` (contoh 5 detik / 1 gambar) di dalam satu jenis katalog saja; model `unknown` selalu di akhir.
17. **(R) Daftar model berubah atau model hilang** setelah dipilih (cache 5 menit, sesi lama).
    - Mitigasi: model terpilih yang tidak ada di katalog tampil "tidak tersedia lagi", tombol generate nonaktif; validasi server tetap menolak.
18. **(R) Kategori video ditebak.** API tidak memberi kategori eksplisit; plan menebak dari `supported_frame_images`, `pricing_skus` (upscale), dan id/nama (`edit`, `avatar`).
    - Mitigasi: hanya `i2v` (punya `first_frame`) yang memengaruhi bisa-dipilih; kategori lain sekadar label, salah label tidak berbahaya. Kategori "lainnya" bila tidak cocok.

### Edge case (katalog)
- Model video tanpa `supported_resolutions` -> satu baris "semua resolusi".
- `pricing_skus` kosong -> kartu tampil dengan "harga tidak tersedia", tetap bisa dipilih bila i2v (dialog biaya akan meminta centang "biaya tidak diketahui").
- Model dengan `cents_per_megapixel_second_precise` (upscale) -> `unknown` (estimator memang menolak), label kategori upscale.
- Harga 0 -> "$0 (gratis)".
- Deskripsi model berisi markdown/link -> tampil sebagai teks biasa (React meng-escape), link tidak dirender.
- API key belum diatur -> katalog error 502 dengan pesan server; picker menampilkan pesan, tidak macet di loading.

### Keputusan
- Revisi 2 plan diadopsi dengan perubahan: tarif per detik tanpa minimum (nomor 13), harga gambar dimuat malas bila > 60 model (nomor 12), urut dalam satu jenis saja dengan `unknown` di akhir (nomor 16).
- Tambah kriteria selesai: tes Aleph minimum, tes kegagalan satu `/endpoints`, tes kesamaan kartu vs `/api/estimate`.

## Grill revisi 3: hapus gambar, klip, karakter
19. **(T) Hapus baris = hapus catatan biaya.** `committed_today` menjumlahkan `cost`/`estimated_cost` dari tabel `clips` dan `images`; menghapus baris menurunkan "terpakai hari ini" dan membuka celah batas harian (plan 04) padahal uangnya sudah keluar.
    - Mitigasi: soft delete (`deleted_at`), baris dan biaya tetap; `committed_today` tidak memfilter `deleted_at`. File video/gambar dihapus dari disk.
20. **(T) Rantai extend.** Menghapus klip induk yang punya lanjutan merusak `merge_chain` dan jejak asal.
    - Mitigasi: klip dengan lanjutan aktif ditolak 409 ("hapus lanjutannya dulu"); klip yang masih berjalan ditolak 409.
21. **(S) Klip yang dipakai film.** Id yang hilang membuat render film gagal.
    - Mitigasi: klip otomatis dilepas dari semua film (urutan lain tetap, film jadi "perlu render ulang"); bila ada film yang sedang dirender, penghapusan ditolak 409 sebelum ada perubahan apa pun.
22. **(S) Gambar yang dipakai karakter** (sumber atau sheet) tidak boleh hilang diam-diam.
    - Mitigasi: ditolak 409 menyebut nama karakter; user menghapus karakternya dulu. Gambar yang dipakai job berjalan juga ditolak. Gambar yang hanya jadi sumber klip selesai boleh dihapus (video sudah ada); thumbnail sumber di dock disembunyikan bila tidak termuat.
23. **(S) Permintaan ganda / ID tidak ada.** `get_image`/`get_clip` memfilter `deleted_at`, jadi hapus kedua kali 404 dan semua jalur lain (extend, edit, motion, karakter) menolak aset terhapus.
24. **(R) Salah klik.** Tombol Hapus memakai konfirmasi dua langkah di UI (bukan dialog bawaan browser). Tidak ada tempat sampah/undo; file sudah terhapus.
25. **(R) Karakter**: dihapus sungguhan (tanpa biaya); gambar-gambarnya tetap ada di library.

## Riwayat
- 2026-10-20: grill revisi 3 (hapus aset), temuan 19 sampai 25.
- 2026-10-19: grill pertama; plan 05 diperbarui lewat entri Riwayat.
- 2026-10-19: grill revisi 2 (katalog model + harga), temuan 11 sampai 18.
