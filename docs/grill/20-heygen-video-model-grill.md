# 20 - Model video HeyGen Video 1 (Grill)

- Tanggal: 2026-10-27

## Temuan dan mitigasi
1. **Format referensi HeyGen belum terbukti** (spike dilewati user): `input_references` dengan `@image_N` mungkin ditolak atau diabaikan. Mitigasi: penolakan penyedia sudah menjadi error 502/4xx yang jelas dan klip tidak dibuat; biaya dikonfirmasi sebelum kirim. Dicatat sebagai asumsi belum terbukti.
2. **Batas jumlah gambar tidak dinyatakan** di data model. Mitigasi: batas konservatif 4 (`MODEL_CAPS.max_images`), kelebihan gambar beat/karakter dibuang dengan peringatan, bukan galat.
3. **Estimasi bisa terlalu rendah**: SKU `reference_duration_seconds_*` lebih mahal dan sebelumnya tidak dipilih. Mitigasi: `pricing._per_second(referenced=...)` + tarif per gambar; tes dua mode. Server menghitung ulang dan `authorize()` memberi 409 bila beda.
4. **Ganti model diam-diam mengubah pengaturan** (resolusi 720p tidak ada di HeyGen, rasio 9:21). Mitigasi: server menolak 422 dengan pesan; UI memindahkan resolusi/rasio ke pilihan pertama yang didukung sebelum mengirim.
5. **Parameter `generate_audio`** mungkin ditolak model yang flag-nya false. Mitigasi: tidak dikirim bila `info.generate_audio is False`; checkbox suara dinonaktifkan dan ringkasan proyek menampilkan "tanpa suara".
6. **Previs/audio referensi/frame akhir tidak ada di HeyGen.** Mitigasi: previs 422 dengan pesan; audio referensi tidak dirakit (`audio_refs` false); frame akhir memang tidak pernah dipakai di v2.
7. **Durasi minimum 5 dtk** (Seedance 4). Mitigasi: dibulatkan dengan peringatan.
8. **Frame awal dari adegan lain** memakai `frame_images` tanpa referensi (aturan OpenRouter sama dengan Seedance, belum terbukti untuk HeyGen); tarif memakai SKU biasa.
9. **Regresi Seedance**: `build()` diberi parameter `max_images` berbawaan 9; `RESOLUTIONS` diperluas. `make test` harus tetap hijau.
