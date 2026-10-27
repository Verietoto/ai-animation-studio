# 20 - Model video HeyGen Video 1 di Proyek dan Pemeran (Plan)

- Status: disetujui (2026-10-27)
- Tanggal: 2026-10-27

## Tujuan
Proyek Storyboard v2 bisa memilih `heygen/heygen-video-1` selain keluarga Seedance 2.0. Gambar karakter (pemeran) dan latar dikirim sebagai gambar referensi HeyGen. Biaya dihitung benar, dan fitur yang tidak didukung dinonaktifkan di UI, bukan gagal diam-diam.

## Data model (OpenRouter `/videos/models`, 2026-10-27)
- Resolusi 480p / 768p / 2K; durasi 5-15 dtk; rasio 21:9, 16:9, 4:3, 1:1, 3:4, 9:16.
- `supported_frame_images: ["first_frame"]` (tanpa frame akhir). `generate_audio: false`, seed: true. Passthrough: `prompt_enhancement`.
- SKU harga: `duration_seconds_{480p,768p,2k}` = 0.02 / 0.036 / 0.10 per dtk; **dengan referensi** `reference_duration_seconds_{480p,768p,2k}` = 0.07 / 0.10 / 0.18 per dtk **ditambah** `reference_input_images` = 0.04 per gambar.
- Contoh: 5 dtk, 480p, 3 gambar referensi = 5 x 0.07 + 3 x 0.04 = **$0.47** (tanpa referensi: $0.10). Dengan referensi HeyGen tidak lebih murah dari Seedance 480p (~$0.067/dtk); keunggulannya hanya pada mode tanpa referensi.

## Ruang lingkup
Dikerjakan:
1. `workspaces.py`: daftar model proyek menerima HeyGen (`V2_VIDEO_MODELS` jadi tabel kapabilitas per model: resolusi, durasi, rasio dari data model, plus flag `refs`, `last_frame`, `audio_refs`, `previs`, `at_image_syntax`).
2. `storyboard_video.py`: cabang request HeyGen: prompt adegan (tanpa blok REFERENCES audio/previs), gambar karakter/latar sebagai referensi (batas maksimal dari data model; bila tidak dinyatakan, dibatasi konservatif lalu dicatat), batas durasi 5-15 dtk (bukan 4-15).
3. `pricing.py`: pilih SKU `reference_duration_seconds_*` bila ada gambar referensi, dan tambahkan `reference_input_images`. Tes eksplisit untuk dua mode.
4. Frontend: dropdown model proyek menampilkan HeyGen; panel video menyembunyikan/menonaktifkan opsi tak didukung dengan alasan (frame akhir, previs, suara karakter, audio); resolusi proyek mengikuti daftar model; peringatan biaya referensi.
5. Mulai dari frame akhir adegan lain tetap jalan (frame awal didukung).

Tidak dikerjakan: model lain (Wan, Veo), `heygen/avatar-iv`, auto-segmen adegan > 15 dtk, TTS.

## Pendekatan
- Prompt: format SHOT/FORMAT Seedance tetap sebagai teks biasa, tetapi `@image_N` diganti nama biasa kecuali spike membuktikan HeyGen memahami penomoran gambar.
- Satu sumber kapabilitas per model (`MODEL_CAPS`) dipakai backend (validasi 422 yang jelas) dan dikirim ke frontend lewat settings proyek.
- Ganti model proyek dari Seedance ke HeyGen: pengaturan yang tidak valid (resolusi 720p/1080p/4K, rasio 9:21) ditolak dengan pesan, tidak diubah diam-diam.

## Langkah kerja
1. Grill plan ini (`docs/grill/20-...`).
2. Spike berbayar kecil (`scripts/spike_heygen.py`): 480p, 5 dtk, tanpa referensi (~$0.10), lalu dengan 1 gambar referensi (~$0.39). Memastikan bentuk request referensi, batas jumlah gambar, apakah audio ikut keluar, dan biaya sebenarnya. **Tidak dijalankan tanpa persetujuan eksplisit user.**
3. `MODEL_CAPS` + validasi pengaturan proyek + tes.
4. Cabang request HeyGen + pricing referensi + tes (OpenRouter palsu).
5. Frontend: dropdown, penonaktifan opsi, peringatan biaya. `npm run build`.
6. Dokumen implementasi; uji frontend dicatat sebagai "diuji manual oleh user".

## Kriteria selesai
- `make test` hijau, termasuk tes pricing dua mode dan penolakan pengaturan tak valid.
- `npm run build` hijau.
- Spike menghasilkan satu klip HeyGen nyata (jika disetujui); bila tidak dijalankan, dokumen implementasi menyatakan format referensi HeyGen belum terbukti.

## Pertanyaan terbuka
- Boleh menjalankan spike berbayar (maks ~$0.60 total)? Tanpa spike, jalur referensi hanya teruji dengan OpenRouter palsu.
- Nama gambar di prompt: nama biasa (usulan) atau `@image_N`?

## Riwayat
- 2026-10-27: draft awal.
- 2026-10-27: disetujui user. Keputusan: spike berbayar DILEWATI; penamaan referensi di prompt tetap `@image_N` (tidak diganti nama biasa), jadi format referensi HeyGen belum terbukti.
