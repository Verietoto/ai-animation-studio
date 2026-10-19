# 03 - Motion Transfer: hasil spike (bagian dari implementasi 03)

Plan: `docs/plan/03-motion-transfer-plan.md` · Grill: `docs/grill/03-motion-transfer-grill.md`
Tanggal: 2026-10-19 · Skrip: `scripts/spike_motion.py` · Gambar bukti: `docs/spike/`
Total biaya spike: **$2,25** dari anggaran maksimum $3,50 (kunci uji: saldo $50).

## Bahan uji
- Orang referensi (AI, foto-realistik): pria berhoodie abu-abu, dibuat dengan `gpt-image-2` ($0,004).
- Karakter: wanita bob hitam, jaket kulit merah, jeans ($0,006), lalu **character sheet 4 gambar** lewat fitur Karakter di aplikasi ($0,06 total, konsisten di depan/samping/tiga perempat/seluruh badan: `docs/spike/03-character-sheet.png`).
- Video referensi: Grok Imagine lite, 5 detik, prompt urutan gerak khas ("melambai dua kali, berbalik, melompat, diam"): hasil nyata melambai, melambai, berdiri, membungkuk, melompat, diam, dengan audio. Biaya $0,11 (480p) dan $0,16 (720p).

## Hasil per jalur

| Jalur | Model | Hasil | Biaya |
|---|---|---|---|
| **B1 ganti subjek, prompt saja** | `black-forest-labs/flux-video-edit` | **Lolos gerakan**: urutan gerak, timing, kamera, latar identik dengan referensi; subjek berganti jadi wanita berjaket merah. **Identitas hanya perkiraan** (poni tidak sesuai karakter, sepatu berbeda). Audio asli terbawa (loudness identik: mean -32,5 dB, max -5,3 dB). Keluaran 736x384. | $0,15 (5 dtk) |
| **B1 + gambar karakter** | FLUX Video Edit | **Ditolak**: `model ... does not accept image input references` (gratis). FLUX hanya menerima video + prompt. | $0 |
| **B2 anchor frame + keyframe** | `runway/aleph-2` | **Lolos gerakan dan identitas**: gerak sama dengan referensi, wajah/rambut bob tanpa poni/jaket kulit merah/jeans/sepatu hitam sesuai character sheet. Keluaran 1932x1050, audio 5,0 dtk. Frame anchor dibuat dengan `gpt-image-2` dari frame pertama video + 2 gambar sheet ($0,06). | $1,40 + $0,06 |
| **A foto-realistik** | Seedance 2.0 mini (video referensi + gambar) | **Ditolak moderasi**: `InputVideoSensitiveContentDetected.PrivacyInformation` ("input video may contain real person"), walau orangnya buatan AI. | $0 |
| **A kartun** | Seedance 2.0 mini, video referensi kartun + gambar kartun karakter | **Diterima.** Identitas karakter dari gambar sangat terjaga (bob, jaket merah, jeans, sepatu bot). Gerakan **mirip secara umum tetapi tidak persis** (melambai, berdiri, membungkuk, lalu lari/melompat; durasi keluaran 4 dtk vs referensi 5 dtk). Keluaran 864x496 + audio. | $0,19 |

Perbandingan visual: `docs/spike/03-motion-flux-vs-aleph.png` (baris 1 referensi, 2 FLUX, 3 Aleph), `docs/spike/03-motion-seedance-cartoon.png`, `docs/spike/03-anchor-frame.png`.

## Temuan yang mengubah desain
1. **Kunci karakter yang benar-benar bekerja untuk orang foto-realistik = jalur B2** (anchor frame + Aleph `keyframes`). FLUX hanya prompt; Seedance menolak orang nyata.
2. **Seedance r2v hanya untuk subjek non-foto-realistik** (kartun/ilustrasi/objek). Persyaratan: video referensi ≥ 407.696 piksel (480p lebar = 854x480 lolos, 736x400 ditolak) dan harus `video_url` HTTPS publik.
3. **URL publik tanpa hosting untuk video hasil OpenRouter**: respons job menyertakan `urls` (URL bertanda tangan, kedaluwarsa sekitar 24 jam) yang muncul beberapa detik setelah status `completed`, dan bisa dipakai sebagai `video_url` referensi di job lain. Untuk video unggahan sendiri tetap perlu hosting (S3/R2).
4. **Format permintaan terbukti**: video referensi = `input_references: [{type:"video_url", video_url:{url}}]` (FLUX, Seedance, Aleph). Aleph: `provider.options.runway.keyframes = [{uri, seconds}]` (data URI diterima).
5. **Biaya nyata vs estimator (plan 04)**: FLUX 5 dtk: estimasi $0,15, nyata $0,15 (cocok). Seedance mini 4 dtk 480p dengan video referensi 5 dtk: nyata $0,1907, estimator dengan `video_input_seconds=5` memberi $0,1998 (selisih 5%, di atas nyata, aman). Tanpa memperhitungkan video input estimator hanya memberi $0,148 (kurang 22%), jadi jalur ini **wajib** memberi `video_input_seconds`. Aleph 5 dtk: estimasi $1,40 = nyata $1,40.
6. `urls` tidak selalu langsung ada saat status berubah `completed`; ambil ulang job sebelum dipakai.

## Kriteria lolos spike (grill 03) dan keputusannya
- Jalur B1 FLUX: gerakan lolos 1 dari 1 percobaan prompt saja (kriteria "2 dari 2" tidak dipenuhi karena biaya; identitas tidak lolos). Dipakai sebagai opsi murah/cepat dengan label "identitas perkiraan".
- Jalur B2 Aleph: gerakan dan identitas lolos 1 dari 1 (mahal, $0,28/detik); dipakai sebagai opsi "kunci karakter".
- Jalur A Seedance: tidak lolos untuk foto-realistik (ditolak); lolos terbatas untuk kartun (gerakan perkiraan). Dipakai hanya untuk karakter non-foto-realistik.
- Keterbatasan spike: 1 percobaan per jalur (acak), orang sintetis (bukan rekaman nyata), satu pola gerak, satu karakter.

## Riwayat
- 2026-10-19: spike dijalankan.
