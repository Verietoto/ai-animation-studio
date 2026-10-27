# 21 - Panel komik (Plan)

- Status: disetujui (2026-10-27)
- Tanggal: 2026-10-27

## Tujuan
Fitur komik tahap pertama: membuat **satu panel komik** dengan AI. Panel memakai karakter dan latar yang sudah ada di proyek (supaya wajah dan tempat konsisten dengan film), lalu diberi balon dialog, narasi, dan efek suara yang bisa diedit, dan bisa diunduh sebagai PNG.

## Ruang lingkup
Dikerjakan:
1. Data panel per proyek: judul, deskripsi adegan panel, karakter (maks 4), latar (opsional), ukuran shot dan sudut kamera, rasio panel, gaya komik, daftar teks (balon), gambar aktif dan daftar take.
2. Generate gambar panel dengan model gambar (estimasi biaya + konfirmasi wajib, seperti fitur lain).
3. Editor balon di atas gambar: tambah, geser, ubah ukuran, hapus; jenis balon bicara, pikiran, narasi (kotak), efek suara (SFX); ekor balon diarahkan ke pembicara.
4. Unduh panel jadi PNG (gambar + balon digabung di browser).
5. Take: tiap generate jadi take baru dan **langsung dipakai** sebagai gambar panel; take lama tetap bisa dipilih kembali (pelajaran dari keluhan take video adegan 1).

Tidak dikerjakan (tahap berikutnya): halaman komik berisi banyak panel dan tata letaknya, membuat panel dari naskah dengan AI, menyambung panel ke episode/adegan film, ekspor PDF/CBZ, penerjemahan balon.

## Desain / pendekatan

### Data (migrasi v20)
Tabel `comic_panels`: `id, workspace_id, title, description, character_ids (JSON, urut), location_id, shot (WS/MS/MCU/CU/ECU), angle (eye/low/high/overhead/dutch), aspect_ratio, comic_style, bubbles (JSON), image_id, created_at, updated_at`.
- `bubbles`: `[{id, kind: speech|thought|caption|sfx, character_id|null, text, x, y, w, h, tail_x, tail_y}]`, koordinat 0..1 relatif terhadap gambar supaya tetap benar bila resolusi berubah. Teks maks 300 karakter, maks 20 balon.
- Take = gambar library dengan `panel_id` (kolom baru di `images`), seperti `beat_id`. Hapus karakter/latar: referensi panel dilepas, panel tidak ikut terhapus.

### Generate (backend, `comic.py`)
- Pakai ulang pola `scenes.keyframe` dan `service._run_edit`: gambar latar sebagai gambar dasar, gambar karakter (character sheet) sebagai referensi tambahan. Tanpa gambar sama sekali: jalur teks ke gambar yang sudah ada (plan 08).
- Prompt dirakit di fungsi murni `comic_prompt.build()`: gaya komik + gaya visual proyek, deskripsi panel, karakter (nama, deskripsi, tampilan), latar, shot + sudut kamera, dan aturan tetap: **"no text, no lettering, no speech bubbles; leave clear empty space for dialogue"**. Teks balon tidak dikirim ke AI: model gambar sering salah mengeja, dan teks harus bisa diedit.
- Rasio panel divalidasi terhadap model gambar (`_validate_image_params`); model gambar bawaan = `workspaces.image_model`.
- Endpoint: `GET/POST /api/comic-panels`, `GET/PUT/DELETE /api/comic-panels/{id}`, `GET /api/comic-panels/{id}/preview` (prompt dan gambar input persis), `POST /api/comic-panels/{id}/generate`, estimasi kind `comic_panel`.

### Frontend
- Halaman baru **Komik** di sidebar: daftar panel di kiri, kanvas panel di tengah, inspector di kanan (deskripsi, karakter, latar, shot, sudut, rasio, gaya, tombol Generate dengan chip biaya).
- Balon digambar sebagai SVG di atas gambar (font komik dari Google Fonts, mis. "Comic Neue"), bisa digeser dan diubah ukuran dengan pointer; teks diedit di inspector. Simpan otomatis (debounce).
- Unduh PNG: gambar + SVG balon digambar ke `<canvas>` di browser; tidak ada pemrosesan server.

## Langkah kerja
1. Grill (`docs/grill/21-comic-panel-grill.md`).
2. Migrasi v20 + CRUD panel + validasi + tes.
3. `comic_prompt.build()` murni + tes; generate + estimasi + take otomatis + tes (OpenRouter palsu).
4. Frontend: halaman Komik, inspector, generate dengan konfirmasi biaya, take.
5. Editor balon + unduh PNG.
6. Dokumen implementasi; uji frontend "diuji manual oleh user".

## Kriteria selesai
- `make test` hijau (CRUD, validasi balon, prompt tanpa teks dialog, generate + 409 tanpa konfirmasi biaya, take baru dipakai otomatis, hapus karakter/latar melepas referensi, migrasi v19→v20).
- `npm run build` hijau.

## Pertanyaan terbuka
1. Gaya komik bawaan: manga hitam-putih, komik Barat berwarna, webtoon, atau ikut gaya visual proyek saja?
2. Panel disimpan per proyek (usulan) atau per episode?
3. Rasio panel bawaan: 4:3 (usulan), 1:1, atau 3:4 (webtoon tegak)?

## Riwayat
- 2026-10-27: draft awal.
- 2026-10-27: disetujui user ("y") tanpa memilih pertanyaan terbuka; dipakai default: gaya ikut proyek (+ manga/Barat/webtoon), panel per proyek, rasio 4:3.
- 2026-10-27 (implementasi): font balon memakai font sistem bergaya komik, bukan Google Fonts (canvas tidak perlu menunggu font web). Hapus panel mengembalikan `{ok: true}`, bukan 204, mengikuti pola hapus lain di `api.ts`.
