# 04 - Cost Estimate (Plan)

- Status: draft (menunggu persetujuan, belum digrill)
- Tanggal: 2026-10-19
- Asal: permintaan user "setiap pembuatan ada estimasi harga sebelum generate"; menggantikan langkah 0 plan 03 dan menutup bug pengaman biaya (grill 03 nomor 3).

## Tujuan
Sebelum setiap job berbayar (gambar ke video, extend, edit foto, tiru gerakan, dan fitur berikutnya), user melihat perkiraan biaya dan harus mengonfirmasi. Server menolak job yang melewati batas per job atau akan membuat total hari ini melewati batas harian.

## Ruang lingkup
- Termasuk: estimator biaya di backend, endpoint estimasi, konfirmasi di UI untuk semua tombol generate, batas per job, pengecekan "terpakai + estimasi" terhadap batas harian, pencatatan estimasi vs biaya nyata, kalibrasi dari riwayat.
- Tidak termasuk: penagihan/kuota per user (belum ada multi-user), prediksi biaya untuk penyedia di luar OpenRouter.

## Data harga yang tersedia (nyata, 2026-10-19)
- Video: `pricing_skus` di `GET /videos/models`. Ada sekitar 45 nama SKU berbeda dengan satuan yang tidak seragam, contoh:
  - sen per detik per resolusi: `cents_per_video_output_second_480p`, `cents_per_second_output_720p`
  - USD per detik: `duration_seconds_720p`, `duration_seconds_with_audio`, `image_to_video_duration_seconds_1080p`
  - per token video: `video_tokens`, `video_tokens_with_video_input` (token = lebar x tinggi x fps x durasi / 1024, 24 fps, menurut review Seedance 2.5)
  - tambahan: `cents_per_image_input`, `reference_images`, `minimum_cents_per_generation`, `cents_per_second_video_continuation_*`
- Gambar: `GET /images/models/{id}/endpoints` memberi baris `pricing` (`billable`, `unit` = image / megapixel / token, `cost_usd`). Untuk satuan token (mis. gpt-image-2), jumlah token keluaran tidak diketahui sebelum generate.
- Biaya nyata ada di `usage.cost` setiap respons (terbukti di plan 01 dan 02).
- Titik kalibrasi nyata: Grok Imagine 1.5 Lite 1 detik 480p + 1 gambar input = 2 sen + 1 sen = **$0,03 perkiraan, $0,03 nyata**. gpt-image-2 edit quality low: nyata $0,0151.

## Desain
- `pricing.py`: fungsi `estimate_video(model_info, duration, resolution, audio, n_image_inputs, video_input_seconds, mode)` dan `estimate_image(endpoint_pricing, n_inputs, n_outputs, resolution)` mengembalikan `{low, high, basis, confidence}`:
  - `confidence = "exact"` bila SKU per detik/per gambar cocok langsung dengan parameter.
  - `"formula"` bila dihitung dari token video (rumus piksel).
  - `"history"` bila satuan token tak bisa diprediksi: pakai median dan maksimum biaya nyata 20 job terakhir untuk model + parameter serupa.
  - `"unknown"` bila tidak ada SKU yang cocok dan tidak ada riwayat: wajib konfirmasi eksplisit dengan teks "biaya tidak diketahui", tidak boleh dikirim otomatis.
  - Pencocokan SKU berurutan dari yang paling spesifik (mode + resolusi + audio) ke yang umum; `minimum_cents_per_generation` diterapkan; SKU yang tak dikenal dicatat ke log agar parser bisa diperbarui.
- Endpoint `POST /api/estimate` dengan body yang sama seperti endpoint generate (tanpa efek samping).
- Setiap endpoint generate menghitung ulang estimasi di server (tidak percaya angka dari browser) dan menolak dengan 402 bila:
  - `estimasi.high > MAX_COST_PER_JOB_USD` (config, default $1), atau
  - `terpakai_hari_ini + biaya_job_aktif_yang_belum_selesai + estimasi.high > DAILY_BUDGET_USD`.
  - Permintaan harus membawa `confirmed_estimate` (nilai `high` yang dilihat user); bila estimasi server lebih tinggi dari itu, tolak dan minta konfirmasi ulang.
- Kolom baru `estimated_cost` di `clips` dan `images` (lewat migrasi bernomor, lihat grill 03 nomor 9). Halaman library menampilkan estimasi vs nyata.
- UI: setiap tombol generate menampilkan "Perkiraan $X sampai $Y" yang diperbarui saat parameter berubah; klik membuka dialog konfirmasi berisi rincian (dasar perhitungan, tingkat keyakinan, sisa anggaran hari ini).

## Langkah kerja
1. Parser `pricing_skus` + tes untuk setiap pola SKU yang ada di data nyata (snapshot `/videos/models` disimpan sebagai fixture tes).
2. Estimator gambar dari endpoint pricing + riwayat.
3. Migrasi DB + kolom `estimated_cost`.
4. Endpoint `/api/estimate` dan pengecekan di semua endpoint generate (termasuk extend), dengan `confirmed_estimate`.
5. UI: tampilan perkiraan + dialog konfirmasi di halaman Gambar ke Video, Extend, Edit Foto.
6. Tes: unit untuk parser, API untuk penolakan, satu uji nyata membandingkan estimasi dan biaya nyata (model murah).

## Kriteria selesai
- Tidak ada job berbayar yang bisa dikirim dari UI tanpa user melihat perkiraan dan mengonfirmasi.
- Server menolak job di atas batas per job dan job yang akan melewati batas harian, walau browser dilewati (tes API).
- Untuk model dengan SKU per detik, estimasi sama dengan biaya nyata (selisih ≤ 10%) pada uji nyata.
- Model yang tidak bisa diperkirakan ditandai "tidak diketahui", bukan diberi angka palsu.

## Pertanyaan terbuka
1. Batas per job default: $1? (Seedance 2.5 720p 10 detik sekitar $2,3 akan ditolak tanpa menaikkan batas.)
2. Konfirmasi di setiap job, atau hanya bila di atas ambang (mis. > $0,10)?

## Riwayat
- 2026-10-19: draft awal.
