# 20 - Model video HeyGen Video 1 (Implementasi)

- Tanggal: 2026-10-27

## Yang dibangun
- `workspaces.py`: `MODEL_CAPS` (label, audio_refs, previs, min_seconds, max_images) menjadi satu sumber; `V2_VIDEO_MODELS` diturunkan darinya dan kini memuat `heygen/heygen-video-1`. `RESOLUTIONS` + 768p, 2K. Validasi model/resolusi/rasio kini juga berlaku saat hanya model yang diganti (422, tidak diubah diam-diam). `settings()` mengirim `model_caps`.
- `seedance_request.build(max_images=)`: batas gambar per model.
- `storyboard_video.py`: batas durasi minimum dan peringatan per model, previs ditolak untuk model tanpa previs, audio referensi hanya bila `audio_refs`, `generate_audio` tidak dikirim bila model menyatakan false, estimasi menghitung jumlah gambar referensi.
- `pricing.py`: `reference_duration_seconds_{res}` dipilih bila ada gambar referensi; `reference_input_images` dikenakan per gambar (sudah ada).
- Frontend: dropdown model (nama dari katalog), ganti model memindahkan resolusi/rasio ke yang didukung, checkbox suara dinonaktifkan untuk model tanpa suara, catatan batas HeyGen, teks "Seedance" di langkah Video dibuat mengikuti model.

## Keputusan
- Spike berbayar dilewati (keputusan user); `@image_N` dipertahankan.
- Batas 4 gambar adalah tebakan konservatif.

## Hasil tes
- `make test`: 436 lulus (termasuk `test_heygen.py`: tarif dua mode, penolakan resolusi/rasio, request tanpa `generate_audio`, previs ditolak).
- `cd frontend && npm run build`: hijau.

## Belum terbukti
- Request referensi HeyGen sungguhan (format `@image_N`, batas gambar, audio) belum pernah dikirim ke OpenRouter.

## Diuji manual oleh user
1. Pengaturan proyek: pilih HeyGen Video 1; resolusi pindah ke 480p, checkbox suara nonaktif, catatan batas tampil.
2. Rasio 9:21 tidak tersedia di HeyGen; ganti kembali ke Seedance berfungsi.
3. Langkah 6: "Siapkan video…" menampilkan judul HeyGen, estimasi biaya memuat tarif referensi, dialog konfirmasi muncul sebelum kirim.
4. Kirim satu adegan 480p (biaya nyata) dan lihat apakah OpenRouter menerima referensi; laporkan galatnya bila ditolak.
