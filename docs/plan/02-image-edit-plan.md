# 02 - Image Edit (Plan)

- Status: draft (menunggu persetujuan, belum digrill)
- Tanggal: 2026-10-16

## Tujuan
Mengedit foto dengan prompt di dalam studio (ubah latar, pakaian, gaya, tambah atau hapus objek, perbaiki karakter), dan memakai hasilnya langsung sebagai input image-to-video (plan 01) atau sebagai gambar objek untuk copy gerakan.

## Ruang lingkup
- Termasuk: upload gambar + prompt, beberapa gambar referensi (mis. wajah karakter untuk konsistensi), riwayat versi edit, bandingkan sebelum/sesudah, kirim hasil ke halaman Generate video.
- Tidak termasuk sekarang: masking manual/kuas, inpainting berbasis area yang digambar user, editor layer.

## Riset model OpenRouter (per 2026-10-16, cek ulang saat implementasi)
- Model yang bisa edit adalah yang punya `image` di input modalities dan `input_references` di `supported_parameters`. Daftar live: `/api/v1/models?output_modalities=image`.
- Edit bisa dilakukan lewat Chat Completions / Responses dengan modality image, atau rute images yang kompatibel OpenAI. Rute yang dipakai diputuskan saat implementasi setelah dicek di dokumentasi resmi.
- Satuan harga berbeda per model (per token, per megapiksel, per gambar), jadi harga harus diukur dari biaya nyata per job.

| Peran | Model | Alasan |
|---|---|---|
| Default (murah, edit akurat) | `openai/gpt-image-2` | Termurah di uji OpenRouter (sekitar $0,006 sampai $0,0135 per gambar), edit referensi benar |
| Edit sulit / kualitas tinggi | `sourceful/riverflow-v2.5-pro` | Sekitar $0,064 per gambar |
| Edit + penjelasan teks | `google/gemini-3-pro-image` | Sekitar $0,134 per gambar, bisa membalas teks dan gambar |
| Alternatif resolusi tinggi | `bytedance-seed/seedream-4.5`, `black-forest-labs/flux.2-pro` | Seedream 1K/2K/4K; biaya belum diukur |

Harga dari uji OpenRouter 11 September 2026; bisa berubah.

## Desain
- Memakai backend, penyimpanan, dan adapter model yang sama dengan plan 01.
- Tabel `images` (id, project_id, parent_image_id untuk rantai versi, prompt, model, biaya, path).
- Halaman Edit: gambar sumber, prompt, gambar referensi opsional, pilih model, hasil sebagai versi baru. Tombol "Jadikan video" mengirim gambar ke halaman Generate.

## Langkah kerja
1. Adapter image-edit (list model, kirim edit, simpan hasil).
2. Tabel dan riwayat versi.
3. UI Edit + sebelum/sesudah.
4. Integrasi ke halaman Generate video.
5. Tes dengan mock + satu uji nyata per model default.

## Kriteria selesai
- Gambar + prompt menghasilkan versi baru yang tersimpan dan bisa dibandingkan.
- Versi mana pun bisa dipakai sebagai input image-to-video tanpa upload ulang.
- Biaya per edit tercatat.

## Urutan terhadap plan 01
Usul: dibangun setelah image-to-video dasar (01 langkah 1 sampai 3) karena memakai fondasi yang sama, sebelum fitur copy gerakan.

## Pertanyaan terbuka
- Perlu masking/inpainting manual nanti?
- Format output dan resolusi default?

## Sumber
- [Image Generation Models Compared](https://openrouter.ai/blog/insights/image-generation-models-compared/)
- [Image Generation docs](https://openrouter.ai/docs/guides/overview/multimodal/image-generation)
- [Image Generation Models: Choosing One](https://openrouter.ai/blog/tutorials/image-generation-models/)
- [Image model collection](https://openrouter.ai/collections/image-models)

## Riwayat
- 2026-10-16: draft awal.
