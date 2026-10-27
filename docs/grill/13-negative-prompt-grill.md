# 13 - Negative prompt di Gambar → Video (Grill)

Plan terkait: `docs/plan/13-negative-prompt-plan.md`
Tanggal: 2026-10-23. Sumber: dokumentasi OpenRouter (dibaca 2026-10-23), `GET /videos/models` dan `GET /models/{id}/endpoints` (gratis), serta `service.py` (`video_models`, `create_clip`, `_image_endpoints`), `openrouter.py`, `motion.py`.

Dokumentasi yang dibaca:
- https://openrouter.ai/docs/cookbook/video-generation/provider-specific-video-options
- https://openrouter.ai/docs/guides/overview/multimodal/video-generation
- https://openrouter.ai/docs/guides/community/vercel-ai-sdk
- https://openrouter.ai/docs/api/api-reference/video-generation/submit-a-video-generation-request

## Temuan riset
1. **Slug yang dipakai adalah penyedia endpoint, bukan pembuat model.** Hasil `GET /models/{id}/endpoints` (field `tag`):
   - Kling v3.0 Std, Kling Video O1, Wan 2.6, Wan 2.7 → `atlas-cloud`.
   - Veo 3.1 Lite → `google-vertex`.
   - Aleph 2 → `runway` (cocok dengan `motion.py`).

   Tebakan plan (`kwaivgi`, `google`, `alibaba`) akan **salah semua**.
2. **Kunci yang salah diabaikan diam-diam.** Skema `ProviderOptions` menyebut "Only options for the matched provider are forwarded; the rest are ignored. Unrecognized keys are silently dropped." Jadi tidak ada 400 yang memberi tahu kita bila slug atau bentuknya salah.
3. **Bentuk berbeda per penyedia di dokumentasi:**
   - Contoh `google-vertex` (Veo): `provider.options["google-vertex"].parameters.negativePrompt`, dengan lapisan `parameters`.
   - Contoh `atlas-cloud` (Wan 2.7): `provider.options["atlas-cloud"].negative_prompt`, langsung di bawah slug.
   - Skema tidak mewajibkan `parameters`, dan dokumentasinya tidak konsisten (contoh lain `google-vertex` di halaman API memakai bentuk datar untuk `output_config`).
4. Respons job tidak menyebut penyedia yang melayani, dan tidak menggemakan opsi yang terkirim.

## Lubang pada plan
1. Slug harus dibaca dari `GET /models/{id}/endpoints`, bukan diturunkan dari id model. `openrouter.py` belum punya method untuk endpoint model video (yang ada hanya `get_image_endpoints` untuk `/images/models/...`).
2. Bentuk payload tidak seragam. Plan menganggap `provider.options.<slug>.<param>` untuk semua.
3. "Slug terbukti lewat uji nyata" di kriteria selesai **tidak bisa dicapai dengan murah**: karena opsi yang salah diabaikan diam-diam dan hasil video acak, satu klip tidak membuktikan negative prompt terbaca. Perlu A/B berulang, idealnya dengan seed tetap; dukungan seed untuk model-model ini belum dicek.
4. Model bisa punya lebih dari satu penyedia di masa depan; sekarang semuanya satu.
5. `create_clip` dipanggil juga oleh `scenes.py` (Storyboard) dan `extend_clip`; parameter baru harus opsional agar pemanggil lama tidak berubah.

## Risiko
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| Bentuk payload salah, diabaikan diam-diam | User mengira negative prompt aktif | Sedang | Ikuti bentuk persis contoh resmi per slug: `google-vertex` → `parameters.negativePrompt`; selain itu → datar. UI menyebut bahwa efeknya tidak bisa diverifikasi aplikasi. |
| Slug berubah (penyedia baru/ganti) | Opsi tidak sampai | Rendah | Slug dibaca dari endpoint API (cache 5 menit, sama dengan katalog), bukan hardcode. Bila ada >1 penyedia, kirim opsi ke semua slug; hanya yang melayani yang meneruskan. |
| Endpoint API gagal saat submit | Klip gagal dibuat | Rendah | 502 dengan pesan jelas sebelum biaya keluar, sama seperti katalog gagal. |
| Kata di negative prompt memicu moderasi | Job gagal | Rendah | Error lewat `friendlyError` yang ada. |

## Edge case
- Negative prompt kosong atau spasi saja: dianggap tidak ada (tidak dikirim, tidak ditolak walau model tidak mendukung).
- Model tidak mendukung + negative prompt terisi: 400 sebelum estimasi/biaya.
- Lebih dari 2000 karakter: 422 dari Pydantic.
- Extend dari klip yang dibuat dengan negative prompt: tidak diwarisi otomatis; form Extend punya kolomnya sendiri (perilaku eksplisit).
- Idempotency: klip lama dikembalikan apa adanya; `params.negative_prompt` ikut tersimpan.

## Potensi bug
1. `provider` di payload `create_clip` belum pernah ada; tidak boleh menimpa field lain. Test memeriksa payload yang diterima FakeOpenRouter.
2. Nama parameter beda huruf (`negative_prompt` vs `negativePrompt`): diambil dari `allowed_passthrough_parameters`, bukan ditebak. Test untuk keduanya.
3. FakeOpenRouter belum punya model dengan `allowed_passthrough_parameters` maupun endpoint video; perlu ditambah.

## Asumsi yang belum terbukti
- Bentuk per slug mengikuti contoh dokumentasi; **efeknya di video belum terbukti**. Uji nyata satu klip tidak membuktikannya (lihat lubang 3).
- `provider.options.runway.keyframes` di `motion.py` (Aleph) memakai bentuk datar; tidak dicek di sini, di luar ruang lingkup.

## Keputusan setelah grilling (perubahan pada plan)
- Slug dari `GET /models/{id}/endpoints` (`tag`), method baru `get_video_endpoints` di `openrouter.py`, cache 5 menit di `service.py`.
- Bentuk: `google-vertex` → `{"parameters": {nama: nilai}}`; slug lain → `{nama: nilai}`. Satu-satunya hardcode, dengan komentar sumber dokumentasinya.
- Bila model punya beberapa penyedia, opsi dikirim untuk semua slug.
- Kriteria "slug terbukti lewat uji nyata" diganti: "slug terbukti dari endpoint API dan bentuk dari contoh dokumentasi resmi". Uji berbayar **tidak** dilakukan kecuali user minta (dan bila diminta, A/B dua klip termurah dengan prompt sama, dinilai mata user).
- UI menyebut bahwa negative prompt diteruskan ke penyedia dan efeknya tidak dijamin.

## Riwayat
- 2026-10-23: grill awal.
