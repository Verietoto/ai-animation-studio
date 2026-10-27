# 09 - Frame akhir + Tiru Gerakan di UI (Grill)

Plan terkait: `docs/plan/09-frame-and-motion-reference-plan.md`
Tanggal: 2026-10-21. Temuan berasal dari membaca kode `backend/app/motion.py`, `service.py`, `main.py`, dan fixture `video_models.json`. Belum ada yang dijalankan.

## Lubang pada plan
1. **Plan menganggap backend plan 03 siap pakai, padahal belum pernah dites.** Membaca kodenya saja sudah menemukan bug (lihat "Potensi bug" 1–3). Langkah 2 (test `motion.py`) harus dikerjakan **sebelum** UI, bukan bersamaan.
2. **Keputusan user belum lengkap.** User menjawab "ya" pada plan, tanpa menjawab tiga pertanyaan terbuka. Default yang dipakai:
   - Referensi hanya dari library. Tombol unggah nonaktif tanpa S3.
   - Batas $1 per job tidak diubah.
   - Spike berbayar **tidak** dijalankan sebelum user menyebut anggaran secara eksplisit.
3. **Pesan moderasi di frontend hanya menangkap error saat submit.** Job video bisa juga gagal belakangan saat polling, dengan pesan moderasi yang disimpan di `clips.error`. Pemetaan pesan harus dipakai di dua tempat: error request (toast/inline) dan `clip.error` (QueueDock/Lightbox). Satu fungsi `friendlyError()` di `api.ts`, dipanggil dari keduanya.

## Risiko (dampak, kemungkinan, mitigasi)
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| URL klip OpenRouter kedaluwarsa (±24 jam) | Job gagal setelah user mengisi semuanya | Tinggi untuk klip lama | Picker library menandai klip > 20 jam "mungkin kedaluwarsa". `from-clip` sendiri gratis; error 400 dari `_public_url` diberi teks jelas. Tidak ada biaya keluar karena submit gagal sebelum job dibuat. |
| Aleph mahal ($0,28/dtk, min $0,56) | Biaya besar per klik | Sedang | Dialog konfirmasi wajib (sudah lewat `useConfirmedRun`). Estimasi `blocked` memblokir di atas $1. UI menampilkan alasan blokir dan saran memotong referensi ≤ 3 dtk. |
| Seedance menolak orang foto-realistik | Klik sia-sia | Tinggi untuk foto | Label mode "kartun/ilustrasi". Pesan 422 yang sudah ada (`MODERATION_HINT`) ditampilkan apa adanya. Penolakan saat submit tidak ditagih (spike 03). |
| Frame akhir mengubah perilaku/harga model | Estimasi salah atau hasil aneh | Belum diketahui | Spike satu job (setelah anggaran disetujui). Sampai itu, label UI "eksperimental". |
| Veo 3.1 dengan frame awal+akhir mungkin hanya menerima durasi tertentu | 400 dari provider | Sedang | Error provider diteruskan; tidak ditebak di kode. Dicatat bila spike menemukannya. |

## Edge case
- Frame awal dan frame akhir adalah gambar yang sama: diizinkan (loop). Tidak diblokir.
- Model diganti ke model tanpa `last_frame` setelah frame akhir dipilih: frontend mengosongkan pilihan. Backend tetap menolak (400) bila dikirim.
- Gambar frame akhir dihapus (soft delete) setelah klip dibuat: jejak asal di Lightbox melewatinya (`imgMap.get` → undefined), seperti sumber yang dihapus sekarang.
- Gambar frame akhir dari workspace lain: `get_image(…, ws)` → 404. Ditambahkan ke sweep test lintas workspace? Tidak perlu, karena id ini ada di body, bukan path. Satu test khusus.
- Klip sumber referensi adalah klip `motion` atau `extend`: `urls` milik job itu sendiri, jadi tetap bekerja.
- Referensi diminta dari klip yang belum selesai: 409 (sudah ada).
- Klip referensi < 407.696 piksel untuk mode `reference`: ditolak sebelum biaya (sudah ada di `_check_ref`).

## Potensi bug (dari membaca kode)
1. **`Motion.create` memanggil `self.estimate(...)` tanpa `ws`** (`motion.py:222`). `estimate` lalu memanggil `get_ref(ref_id, DEFAULT_WS)`. Di workspace selain `main`, setiap generate tiru gerakan gagal 404 "referensi tidak ditemukan" setelah semua validasi lolos. **Pasti bug.** Fix: teruskan `ws=ws`, dan tambahkan test di workspace non-default.
2. **`_public_url` menunggu sampai 5×2 dtk di dalam `with st._lock`.** Selama itu semua generate lain (gambar, video, adegan) ikut tertahan. Fix: ambil URL **sebelum** masuk lock. URL ini tidak bergantung pada anggaran, dan objek S3 tetap dihapus bila authorize gagal.
3. **Estimasi `motion_anchor` selalu `n_inputs=3`**, padahal `make_anchor` mengirim frame + 1 atau 2 gambar sheet. Untuk karakter tanpa sheet (hanya source), jumlahnya 2 input. Biaya server ≠ biaya yang dikonfirmasi UI, sehingga `authorize` → 409 "estimasi berubah" dan user tidak pernah bisa membuat anchor. Fix: satu fungsi `anchor_inputs(character_id)` dipakai oleh estimate dan `make_anchor`. Pola ini sama dengan `keyframe_plan` di plan 08. `EstimateIn` sudah punya `character_id`.
4. `make_anchor` membuat gambar `kind="frame"` dulu, lalu menghapusnya dengan `DELETE` keras bila edit gagal. Bila edit berhasil, gambar frame itu tetap ada di library sebagai sampah. Diterima: gambar itu adalah "jejak asal" anchor (parent). Hanya dicatat.
5. `idempotency_key` di `Motion.create` dicari tanpa filter workspace. Key berupa UUID dari frontend, jadi risiko tabrakan diabaikan. Hanya dicatat.
6. `public_clip` mengeluarkan `params` sebagai string JSON. Agar Lightbox bisa menampilkan frame akhir, `public_clip` menambah field `last_image_id` turunan, sehingga frontend tidak perlu mem-parse JSON.

## Asumsi yang belum terbukti
- OpenRouter menerima dua elemen `frame_images` (`first_frame` + `last_frame`) dalam satu request, dan harganya sama. Dasarnya hanya dokumentasi dan `supported_frame_images`; belum diuji nyata.
- `urls` tersedia untuk klip yang dibuat aplikasi ini sebelum plan 03, yaitu dari job lama. Ini hanya terbukti untuk job saat spike.
- FakeOpenRouter di `conftest.py` belum punya respons `urls` untuk `get_video_job`. Perlu ditambah untuk test.

## Keputusan setelah grilling (perubahan pada plan)
- Urutan kerja:
  1. Perbaiki bug 1–3 + test `motion.py`.
  2. Backend frame akhir.
  3. `health.public_media`.
  4. Frontend A.
  5. Frontend B.
  6. `friendlyError()`.
- Spike berbayar menunggu anggaran eksplisit dari user. Tanpa spike, fitur ditandai "selesai kecuali verifikasi nyata", dan user bisa mengujinya sendiri lewat UI dengan dialog biaya.
- `public_clip` + `last_image_id` turunan.
- `anchor_inputs()` sebagai satu sumber kebenaran untuk estimasi dan anchor.

## Riwayat
- 2026-10-21: grill awal.
