# 10 - Unggah video referensi lewat tunnel sementara (Implementation)

Plan: `docs/plan/10-tunnel-public-media-plan.md` · Grill: `docs/grill/10-tunnel-public-media-grill.md`
Tanggal: 2026-10-21 · Status: kode dan tunnel terbukti bekerja; **pengunduhan oleh penyedia model belum terbukti** (lihat "Uji berbayar").

## Yang dibangun
- `backend/app/publicmedia.py`:
  - `TunnelPublicMedia` (antarmuka sama dengan `S3PublicMedia`: `publish`, `delete`, `cleanup`, plus `close`).
  - Server berkas `ThreadingHTTPServer` di `127.0.0.1` port acak. Hanya melayani token terdaftar (32 hex) lewat GET/HEAD, dengan Range (206/416). Log request dimatikan karena URL berisi token.
  - `start_cloudflared()` menjalankan quick tunnel, mengurai URL `*.trycloudflare.com` (bukan `api.`), dan terus menguras stderr.
  - `wait_reachable()` menunggu sampai URL publik bisa dijangkau sebelum `publish` selesai.
  - Tunnel berhenti sendiri setelah 5 menit tanpa berkas aktif dan saat aplikasi berhenti.
  - Token hidup `max(PUBLIC_URL_TTL_SECONDS, 7200)` detik dan dihapus oleh `delete(key)` saat job selesai.
- `backend/app/config.py`: `public_tunnel` dari `PUBLIC_TUNNEL`.
- `backend/app/main.py`: pemilihan S3 → tunnel (bila `PUBLIC_TUNNEL=cloudflared` dan `cloudflared` ada di PATH) → `NoPublicMedia`; `close()` dipanggil di shutdown.
- `.env.example`: contoh `PUBLIC_TUNNEL=cloudflared`.
- `frontend/src/pages/Motion.tsx`: penjelasan tombol unggah menyebut tunnel dan S3.
- `scripts/spike_tunnel.py`: skrip uji berbayar dengan batas keras $0,20 dan DATA_DIR sementara.

## Temuan grill yang ditangani
TTL, `close()`, satu lock, pembaca stderr, regex tanpa `api.`, batas waktu tunggu, dan Range ketat semuanya diimplementasikan dan dites. Lihat `backend/tests/test_tunnel.py`.

## Temuan baru saat uji nyata
URL quick tunnel baru bisa dijangkau sekitar 15 detik setelah cloudflared melaporkannya (lima percobaan pertama gagal DNS). Tanpa penantian, penyedia yang mengunduh segera setelah submit bisa gagal. Ditangani oleh `wait_reachable()` (+1 test).

## Revisi 1: pengecekan "siap" tidak lagi lewat DNS lokal
Laporan user: `tunnel naik tetapi URL publiknya belum bisa dijangkau (DNS)` setelah 45 dtk. Diukur di komputer user: DNS publik 1.1.1.1 mengenali host baru dalam 1,1 dtk, tetapi resolver lokal (8.8.8.8) baru setelah **75,5 dtk**, karena jawaban NXDOMAIN pertama ikut di-cache. Pengecekan lokal juga menjadi penyebab (bukan sekadar korban) dan bukan sudut pandang penyedia.
- `wait_reachable()` untuk alamat https memakai DoH Cloudflare (`_doh_ips`) lalu sambung langsung ke IP dengan SNI (`_answers_https`); tidak ada query DNS lokal. Bila DoH diblokir jaringan: jeda ±10 dtk lalu lanjut. Batas 90 dtk.
- Bila belum siap, tunnel **tetap hidup** dan percobaan berikutnya memeriksa ulang tanpa memulai tunnel baru.
- Hasil nyata: `publish` selesai dalam 7,1 dtk; GET Range lewat IP → `206 Partial Content`; tidak ada proses cloudflared tersisa.
- Tes: 213 passed (+2: probe tak menyentuh DNS lokal, tunnel tetap hidup saat belum siap).

## Hasil tes
- `make test`: **203 passed** (181 → 192 di plan 09 → 203). 12 test baru di `backend/tests/test_tunnel.py`: token unik dan hanya berkas terdaftar (path `..`, ganda, token salah → 404), Range 200/206/416 dan `parse_range`, `delete` dan kedaluwarsa, berkas hilang → 404, satu tunnel untuk banyak publish, kegagalan tunnel → `PublicMediaError`, tunnel berhenti saat idle dan menyala lagi, `close()`, pemilihan di `create_app`, `wait_reachable`.
- `cd frontend && npm run build`: hijau.
- **Uji gratis dengan tunnel sungguhan** (berkas uji buatan ffmpeg): tunnel naik 5,1 dtk; GET dari internet 200 dan identik byte-per-byte (10.438 byte); Range `bytes=0-99` → 206 dengan `Content-Range: bytes 0-99/10438`; setelah `delete` → 404; tidak ada proses `cloudflared` tersisa.

## Uji berbayar (anggaran disetujui user: ±$0,15)
`scripts/spike_tunnel.py`: unggah video uji 3 dtk 854×480 (testsrc2 + nada), estimasi **$0,09** (FLUX Video Edit), submit lewat `/api/motion`.
- Submit: **200 diterima** penyedia dalam 13,9 dtk (termasuk tunnel naik). Tidak ada penolakan terhadap URL `trycloudflare.com`.
- Setelah batas tunggu skrip (±7,5 menit) job masih `in_progress`; pengecekan ulang langsung ke OpenRouter menunjukkan status `pending`, belum ada `urls`.
- Skrip lalu selesai dan menutup tunnel. Bila penyedia belum mengunduh video saat itu, job akan gagal.
- **Kesimpulan jujur: belum terbukti bahwa penyedia mengunduh video lewat tunnel.** Yang terbukti hanya bahwa URL diterima di submit. Penyebab job lama antre tidak diketahui.
- Biaya terpakai: belum diketahui (job belum selesai; maksimum $0,09).

## Uji pembanding dan diagnosis error 422 (anggaran disetujui user: $0,20)
Laporan user: job `flux_edit` dengan video unggahan gagal `HTTP 422 … This endpoint only edits the supplied MP4 video; it cannot use media as a reference …` (job diterima, ditolak belakangan oleh penyedia; biaya kosong).
- `scripts/spike_tunnel_compare.py`: video sumber 2 dtk dibuat di OpenRouter ($0,04), lalu **berkas yang sama** dikirim ke FLUX Video Edit lewat (A) URL bertanda tangan OpenRouter dan (B) tunnel. **A dan B sama-sama `completed`, masing-masing $0,06.** Jadi penyedia **bisa mengunduh dari tunnel**; pertanyaan terbuka di atas terjawab.
- Berkas milik user normal (h264, aac 48 kHz stereo, yuv420p, 24 fps, 576×1024, 8 dtk). Prompt yang terkirim berisi `The new subject: Persis seperti di foto` (deskripsi baku karakter).
- Uji hipotesis (video 1 dtk yang sama dengan jalur B, prompt persis milik user): **ditolak dengan 422 yang sama**, biaya kosong. Jadi penyebabnya ada di teks prompt, bukan tunnel, format, orientasi, atau durasi.
- Belum terpisah: kalimat templat "Replace the person … with the new subject" vs deskripsi "Persis seperti di foto". Dugaan terkuat: rujukan ke foto, karena templat penggantian subjek yang subjeknya dijelaskan dengan kata-kata berhasil di spike 03. Anggaran habis, tidak diuji lagi.
- Total biaya tertagih uji ini: $0,16 (dari $0,20).
- Perubahan: `friendlyError` memetakan pesan ini ke saran Indonesia; mode "Ganti subjek" menampilkan teks deskripsi yang akan ditambahkan ke prompt dan memperingatkan bila menyebut foto/gambar.

## Uji frontend: diuji manual oleh user
1. Isi `PUBLIC_TUNNEL=cloudflared` di `.env`, restart backend. Tiru Gerakan: tombol "Unggah video" aktif.
2. Unggah video pendek lalu pilih mode "Ganti subjek". Estimasi muncul dan job terkirim. Selama job berjalan komputer harus menyala.
3. Tanpa `PUBLIC_TUNNEL`, tombol nonaktif dengan penjelasan baru.

## Riwayat
- 2026-10-21: implementasi, uji gratis, dan uji berbayar pertama (hasil belum final).
- 2026-10-21: revisi 1, pengecekan siap lewat DoH + IP setelah laporan user (DNS lokal lambat).
- 2026-10-21: uji pembanding tunnel vs URL OpenRouter (keduanya berhasil) dan diagnosis 422 (prompt, bukan tunnel).
