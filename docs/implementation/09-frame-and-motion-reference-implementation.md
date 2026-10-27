# 09 - Frame akhir + Tiru Gerakan di UI (Implementation)

Plan: `docs/plan/09-frame-and-motion-reference-plan.md` · Grill: `docs/grill/09-frame-and-motion-reference-grill.md`
Tanggal: 2026-10-21 · Status: selesai kecuali verifikasi nyata (spike berbayar belum dijalankan; menunggu anggaran dari user) dan uji frontend oleh user.

## Yang dibangun
### Backend
- `service.py` `create_clip(…, last_image_id=None)`:
  - Bila model tidak punya `last_frame`, request ditolak 400 sebelum biaya keluar.
  - `frame_images` berisi `first_frame` + `last_frame`.
  - `last_image_id` disimpan di `params`, bukan sebagai field payload.
- `main.py`:
  - `ClipIn.last_image_id`.
  - `public_clip` mengeluarkan `last_image_id` turunan dari `params`.
  - `/api/health` mendapat `public_media` (S3 terpasang atau tidak).
  - Estimasi `motion_anchor` mewajibkan `character_id` dan menghitung input dari `Motion.anchor_sheet`.
- `motion.py`:
  - `anchor_sheet()` jadi satu sumber untuk estimasi dan `make_anchor`.
  - `create` meneruskan `ws` ke estimate.
  - `_public_url` dipanggil di luar `st._lock`; objek publik dihapus bila authorize gagal.

### Frontend
- `api.ts`:
  - Tipe `Reference`, `MotionMode`, `Clip.last_image_id`, `Health.public_media`, dan kind estimasi `motion`/`motion_anchor`.
  - Method `references`, `referenceFromClip`, `uploadReference`, `referenceUrl`, `makeAnchor`, `motion`.
  - `friendlyError()` dipakai di satu-satunya `fetch`, sehingga semua error request ikut terpetakan.
- `pages/Generate.tsx`:
  - Bagian "Frame akhir (opsional)" hanya muncul bila model mendukung `last_frame`; pilihan dikosongkan saat model diganti.
  - Pratinjau kecil frame akhir di kanvas.
  - Peringatan bila rasio berbeda > 10%.
- `pages/Motion.tsx` (baru): halaman "Tiru Gerakan".
  - Referensi dari klip library, dengan tanda "mungkin kedaluwarsa" untuk klip > 20 jam. Unggah video hanya aktif bila `public_media`.
  - Tiga kartu mode dengan label dan harga dari spike 03.
  - Pilih karakter atau gambar subjek.
  - Anchor frame (langkah 1, dialog biaya sendiri) untuk "Kunci karakter".
  - Parameter Seedance untuk mode kartun.
  - Template prompt per mode.
  - Estimasi + konfirmasi lewat `useEstimate`/`useConfirmedRun`.
- `App.tsx`: halaman ke-6 `#/motion` (ikon Footprints, shortcut `6`).
- `lightbox.tsx`:
  - Fakta "Frame akhir" (thumbnail yang bisa diklik).
  - Label jejak asal "Tiru gerakan" / "Anchor".
  - `clip.error` lewat `friendlyError`.
- `queue.tsx`: toast gagal lewat `friendlyError`.
- `styles.css`: `.last-frame`, `.motion-pair`, `.ref-pick`, `.mode-card(s)`.

## Temuan grill yang ditangani
| Grill | Penanganan |
|---|---|
| Bug 1: estimate tanpa `ws` di `Motion.create` | Diperbaiki. Test `test_flux_edit_from_clip_in_second_workspace`. |
| Bug 2: `sleep` di dalam lock | `_public_url` dipindah sebelum lock. Tidak ada test waktu (dicatat). |
| Bug 3: `n_inputs` anchor selalu 3 | `anchor_sheet()` + estimasi `1 + len(sheet)`. Test `test_anchor_estimate_matches_generate_for_character_without_sheet`. |
| Lubang 3: moderasi saat polling | `friendlyError` dipakai juga untuk `clip.error` (Lightbox, toast). |
| Edge: frame akhir dari workspace lain | 404 tanpa submit. Test `test_last_frame_from_other_workspace_is_404`. |

**Bug baru yang ditemukan saat test (tidak ada di grill):** `POST /api/motion` meneruskan `reference_id` dari body ke `Motion.create(ref_id=…)`. Akibatnya `TypeError`/500 di setiap panggilan; endpoint ini tidak pernah bisa dipakai sejak plan 03. Diperbaiki di `main.py`.

## Menyimpang dari plan
- Halaman Tiru Gerakan ditaruh di urutan ke-6, bukan di dekat "Gambar → Video", supaya shortcut `1`–`5` yang sudah ada tidak bergeser.
- Daftar `/api/references` lama tidak ditampilkan. Setiap klik klip membuat referensi baru (gratis). Daftar referensi lama bisa ditambahkan bila nanti terasa perlu.

## Hasil tes
- `make test`: **192 passed** (sebelumnya 181).
  - 11 test baru di `backend/tests/test_motion.py`: frame akhir (kirim, model tak mendukung, lintas workspace), `health.public_media`, `flux_edit` di workspace kedua, wajib konfirmasi, unggahan tanpa S3 → 501, anchor tanpa sheet + `anchor_edit` (anchor wajib, keyframe Runway terkirim), mode `reference` menolak klip kecil, moderasi → 422 tanpa klip tercatat, referensi lintas workspace → 404.
  - `conftest.py`: FakeOpenRouter mendapat model FLUX Video Edit + Aleph 2, `urls` di respons job, dan `video_submit_error`.
- `cd frontend && npm run build`: hijau.
- Spike nyata: **belum dijalankan** (menunggu anggaran eksplisit dari user, grill 09).

## Uji frontend: diuji manual oleh user
Restart backend dulu (`make be` / `make dev`), karena ada field dan endpoint yang berubah.
1. Gambar → Video, model Seedance/Kling/Veo: muncul bagian "Frame akhir". Ganti ke Grok: bagian itu hilang dan pilihan terhapus.
2. Pilih frame akhir: thumbnail "frame akhir" muncul di pojok kanvas. Gambar dengan rasio berbeda memunculkan peringatan.
3. Buat video dengan frame akhir (berbayar, dialog biaya muncul). Di Lightbox klip itu ada "Frame akhir" yang bisa diklik.
4. Tiru Gerakan: klik klip library, lalu video referensi tampil dengan durasi/ukuran. Klip > 20 jam bertanda "mungkin kedaluwarsa".
5. Tombol "Unggah video" nonaktif dengan penjelasan S3 (bila S3 tidak dipasang).
6. Ganti mode: template prompt ikut berganti, kecuali prompt sudah diubah.
7. "Ganti subjek": estimasi muncul ($0,03 × durasi referensi), lalu buat video. Job masuk antrian dan Library dengan label "Tiru gerakan".
8. "Kunci karakter": tanpa karakter, tombol nonaktif. Buat anchor frame (dialog biaya), anchor tampil di kanvas kanan, lalu buat video (Aleph). Referensi > ±3 dtk diblokir batas $1.
9. "Animasikan gambar": parameter Seedance tampil. Klip referensi kecil (< 854×480) memberi pesan "terlalu kecil" di estimasi.
10. Error moderasi (mis. Seedream di Edit Foto) tampil dalam bahasa Indonesia dengan saran, plus pesan asli.

## Revisi 1: subjek FLUX bisa diedit (2026-10-21)
Laporan user: "Ganti subjek" terus ditolak FLUX dengan 422 (`This endpoint only edits the supplied MP4 video; it cannot use media as a reference …`). Data aslinya: prompt terkirim berakhir `The new subject: Seperti di foto`. Deskripsi baku karakter ditempel server ke prompt (`Motion.create`), jadi mengedit kotak prompt tidak membantu, dan halaman Karakter tidak punya edit deskripsi. Uji berbayar (plan 10): jalur tunnel dan format video terbukti sehat; prompt yang sama dengan video 1 dtk yang tadinya berhasil ditolak 422.
- Backend: `MotionIn.subject_text` (maks 1000); pada `flux_edit` ia menggantikan deskripsi baku karakter, tanpa itu perilaku lama. Test `test_flux_subject_text_replaces_character_description`.
- Frontend: kolom "Subjek baru, dalam kata-kata" di mode "Ganti subjek" (terisi dari deskripsi karakter, boleh diedit) dengan peringatan bila menyebut foto/gambar.
- `make test`: 214 passed; build frontend hijau.
- Belum terbukti: bahwa kata "foto" saja pemicunya (bukan kalimat templat). Diuji user lewat UI.

## Riwayat
- 2026-10-21: implementasi awal.
- 2026-10-21: revisi 1, kolom subjek FLUX yang bisa diedit setelah laporan 422.
