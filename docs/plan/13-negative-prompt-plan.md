# 13 - Negative prompt di Gambar → Video (Plan)

- Status: draft, menunggu persetujuan
- Tanggal: 2026-10-23

## Tujuan
Permintaan user: "btw di section image to video, apakah bisa ada negative prompt?" lalu "ya" untuk dibuatkan plan.

User bisa menulis hal yang tidak diinginkan (mis. "teks, watermark, tangan cacat, blur") untuk model yang mendukungnya, tanpa menulis "tanpa X" di prompt biasa.

## Keadaan sekarang (dicek 2026-10-23)
- Katalog `GET /videos/models` (30 model) memberi `allowed_passthrough_parameters` per model. Yang memuat negative prompt:
  - `negative_prompt`: Kling v3.0 Pro/Std, Kling Video O1, Wan 2.6, Wan 2.7.
  - `negativePrompt`: Veo 3.1, Veo 3.1 Fast, Veo 3.1 Lite.
  - Tidak ada: Seedance, Hailuo, Grok, Wan 3.0, HappyHorse, Aleph, Gen-4.5, FLUX, HeyGen.
- Aplikasi belum membaca `allowed_passthrough_parameters`: `video_catalog()` di `service.py` tidak mengeluarkannya, dan `create_clip` hanya mengirim `duration`, `resolution`, `aspect_ratio`, `generate_audio`, `frame_images`.
- Satu-satunya pemakaian passthrough sekarang: `motion.py` mengirim `provider.options.runway.keyframes` untuk Aleph.

## Ruang lingkup
Termasuk:
- Gambar → Video (`POST /api/clips`) dan Extend (`POST /api/clips/{id}/extend`, karena memakai `create_clip` yang sama).
- Backend:
  - `video_catalog()` menambah `capabilities.negative_prompt` = nama parameter (`"negative_prompt"` / `"negativePrompt"`) atau `null`, diturunkan dari `allowed_passthrough_parameters`, tanpa daftar model hardcode.
  - `ClipIn` / `ExtendIn`: `negative_prompt: str | None` (maks 2000).
  - `create_clip(…, negative_prompt=None)`: bila model tidak mendukung → 400 sebelum biaya keluar. Bila didukung, dikirim di `provider.options.<slug>.<nama parameter>`. Disimpan di `params["negative_prompt"]` untuk jejak (Lightbox), tidak sebagai field payload.
- Frontend:
  - `Generate.tsx`: kolom "Negative prompt (opsional)" hanya muncul bila model mendukung; dikosongkan saat model diganti ke yang tidak mendukung (pola sama dengan "Frame akhir").
  - Form Extend di Lightbox: kolom yang sama, dengan aturan yang sama.
  - Lightbox: tampilkan negative prompt yang dipakai.
  - Beberapa chip cepat ("teks", "watermark", "blur", "tangan cacat", "wajah berubah") yang menambah frasa, memakai pola chip prompt helper yang ada.

Tidak termasuk:
- Storyboard / generate adegan (`scenes.py`), Tiru Gerakan, Edit Foto. Bisa ditambah nanti dengan fungsi yang sama.
- `cfg_scale` Kling dan parameter passthrough lain.
- Meniru negative prompt untuk model yang tidak mendukung (menulis "tanpa X" ke prompt): tidak andal, dan menyembunyikan perilaku.

## Desain / pendekatan
- Satu helper `_passthrough(model, name) -> str | None` di `service.py` membaca katalog yang sudah di-cache (`video_models()`), dipakai validasi dan katalog.
- Slug provider di `provider.options`: **belum diketahui pasti** untuk Kling, Veo, Wan (Aleph terbukti `runway`). Tebakan awal dari id model (`kwaivgi`, `google`, `alibaba`) belum tentu benar. Diselidiki di grill lewat dokumentasi OpenRouter; bila tetap tidak pasti, satu uji nyata termurah dengan batas biaya yang disetujui user.
- Estimasi biaya tidak berubah (harga tidak bergantung pada negative prompt).
- Idempotency: `negative_prompt` ikut tersimpan di baris klip, jadi pengiriman ulang dengan kunci sama tetap mengembalikan klip lama.

## Risiko awal (bahan grill)
- Slug salah → provider diam-diam mengabaikan parameter, user mengira negative prompt aktif. Ini risiko utama.
- `allowed_passthrough_parameters` berubah di katalog → kolom hilang/muncul; harus mengikuti katalog, bukan hardcode.
- Moderasi: kata-kata di negative prompt ikut diperiksa provider; error tetap lewat `friendlyError`.

## Langkah kerja
1. Grill plan ini (termasuk riset slug provider).
2. Backend: helper, katalog, `ClipIn`/`ExtendIn`, `create_clip`, test (dikirim dengan nama dan slug benar, ditolak untuk model tanpa dukungan, tersimpan di params, katalog mengeluarkan kemampuan).
3. Frontend: kolom di Generate dan Extend, chip, tampilan di Lightbox.
4. Dokumen implementation 13 dan daftar uji manual untuk user.

## Kriteria selesai
- `make test` hijau dengan test baru; `npm run build` hijau.
- Slug provider terbukti (dokumentasi atau uji nyata), bukan tebakan.
- Kolom hanya muncul untuk model yang mendukung, dan nilainya terkirim dengan nama parameter yang benar.

## Pertanyaan terbuka
1. Perlu juga di Storyboard (generate adegan), atau cukup Gambar → Video dan Extend dulu?
2. Bila slug tidak bisa dipastikan dari dokumentasi, boleh satu uji nyata dengan model termurah yang mendukung (perkiraan ≤ $0.15, batas diusulkan $0.20)?

## Riwayat
- 2026-10-23: draft awal.
- 2026-10-23: disetujui user ("go"); setelah grill:
  - Slug dari `GET /models/{id}/endpoints` (`atlas-cloud` untuk Kling/Wan, `google-vertex` untuk Veo), bukan dari id model.
  - Bentuk: `google-vertex` memakai lapisan `parameters`, slug lain datar (sesuai contoh resmi).
  - Uji berbayar tidak dilakukan; kriteria selesai diganti menjadi bukti dari endpoint API + dokumentasi. Pertanyaan terbuka 2 gugur.
  - Pertanyaan terbuka 1 belum dijawab; default: Storyboard tidak termasuk.
  - Rincian di grill 13.
