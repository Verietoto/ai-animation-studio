# 10 - Unggah video referensi lewat tunnel sementara (Plan)

- Status: draft, menunggu persetujuan
- Tanggal: 2026-10-21

## Tujuan
Permintaan user: unggah video referensi (Tiru Gerakan) tanpa S3/R2, "coba nomor 2" (tunnel sementara).

Model video mengunduh video referensi dari URL HTTPS publik, jadi berkas lokal harus bisa dijangkau dari internet selama job berjalan. Dengan tunnel, komputer user menyajikan berkas itu sendiri dan tidak butuh akun storage.

## Keadaan sekarang
- Antarmuka `PublicMedia` sudah ada di `backend/app/publicmedia.py`: `publish(path) -> (key, url)`, `delete(key)`, `cleanup(older_than_seconds)`. Implementasinya `NoPublicMedia` dan `S3PublicMedia`. Dipilih di `create_app` (`main.py`) berdasarkan variabel S3 di `.env`.
- `Motion.create` memanggil `publish` sebelum submit dan `delete` saat job selesai (`service.py`, jalur polling) atau saat submit gagal.
- `cloudflared` sudah terpasang di komputer user (`/opt/homebrew/bin/cloudflared`). Mode "quick tunnel" (`cloudflared tunnel --url http://127.0.0.1:PORT`) tidak butuh akun dan memberi URL acak `https://xxxx.trycloudflare.com`.
- `/api/health.public_media` dan tombol "Unggah video" di halaman Tiru Gerakan sudah menyesuaikan diri: aktif bila `public_media` true.

## Ruang lingkup
Termasuk:
- Kelas baru `TunnelPublicMedia` (satu file, `publicmedia.py`) dengan antarmuka yang sama. Dipilih bila S3 tidak dikonfigurasi dan `PUBLIC_TUNNEL=cloudflared` di `.env`.
- Server berkas kecil terpisah yang hanya menyajikan berkas yang didaftarkan.
- Pengelolaan proses `cloudflared`: dijalankan saat publish pertama, dimatikan setelah tidak ada berkas terdaftar selama beberapa menit dan saat aplikasi berhenti.
- Test dengan tunnel palsu (tanpa jaringan).

Tidak termasuk:
- Penyedia tunnel lain (ngrok, Tailscale Funnel), tunnel bernama dengan akun Cloudflare.
- Mengekspos aplikasi utama. Hanya berkas video referensi yang terbuka.
- Pengaturan lewat UI. Tetap lewat `.env`.

## Desain
1. **Server berkas terpisah, bukan aplikasi utama.** `http.server.ThreadingHTTPServer` di thread daemon, mengikat `127.0.0.1` pada port acak. Yang diekspos tunnel hanya server ini, jadi API aplikasi (kunci API, library, biaya) tidak pernah terbuka ke internet.
2. **Hanya berkas terdaftar.** `publish(path)` membuat token acak 128-bit dan memetakan `token -> path`. URL: `https://<host>.trycloudflare.com/<token>.mp4`. Selain path itu, jawabannya 404. Hanya GET/HEAD. Tidak ada daftar direktori, tidak ada penelusuran path (`..`), karena yang dilayani hanya path hasil pemetaan.
3. **Range request didukung** (`Range: bytes=…`, jawaban 206). Penyedia model biasa mengunduh bertahap.
4. **Kedaluwarsa.** Token mati setelah `PUBLIC_URL_TTL_SECONDS` (bawaan 3600) dan dihapus oleh `delete(key)` saat job selesai. `cleanup` menghapus token yang kedaluwarsa.
5. **Proses cloudflared.** `subprocess.Popen(["cloudflared","tunnel","--url",f"http://127.0.0.1:{port}","--no-autoupdate"])`, membaca stderr sampai muncul URL `https://…trycloudflare.com` (batas waktu 30 detik). Bila gagal: `PublicMediaError` dengan pesan jelas (cloudflared tidak ada, tunnel tidak naik). Dimatikan saat tidak ada berkas aktif selama 5 menit dan di `lifespan` shutdown.
6. **Pemilihan.** `create_app`: S3 bila lengkap; kalau tidak, `TunnelPublicMedia` bila `PUBLIC_TUNNEL=cloudflared` dan `cloudflared` ada di PATH; kalau tidak, `NoPublicMedia`. `/api/health.public_media` ikut true untuk tunnel.
7. **Pesan UI.** Penjelasan di tombol "Unggah video" diperluas: S3/R2, atau `PUBLIC_TUNNEL=cloudflared`.

## Risiko awal (bahan grill)
- **Keamanan:** berkas video user terbuka di internet lewat URL acak. Mitigasi: token 128-bit, TTL, hapus setelah job, hanya berkas terdaftar. Tetap ada risiko kecil bila URL bocor di log OpenRouter/penyedia.
- **Ketersediaan:** quick tunnel tidak punya jaminan uptime dan URL berubah tiap start. Komputer harus menyala dan tidak sleep selama job (bisa puluhan menit). Belum diketahui apakah job yang gagal karena tunnel putus tetap ditagih.
- **Kapan penyedia mengunduh:** belum terbukti apakah video diunduh saat submit atau saat pemrosesan. Berkas tidak boleh dihapus sebelum job selesai. Alur sekarang sudah menunggu sampai job selesai.
- **Throughput:** unggah dari rumah (upstream) lebih lambat; video referensi dibatasi `MAX_REFERENCE_SECONDS` (10 dtk) dan dinormalisasi, jadi kecil.
- `cloudflared` mungkin menolak atau dibatasi untuk quick tunnel pada jaringan tertentu.
- Proses anak yatim bila aplikasi mati paksa.

## Langkah kerja
1. Grill plan ini.
2. `TunnelPublicMedia` + server berkas + pengelola proses (tunnel dapat disuntik agar bisa dipalsukan di test).
3. Test: token acak dan unik, hanya berkas terdaftar (404 untuk path lain dan `..`), Range 206, kedaluwarsa, `delete`, `cleanup`, kegagalan tunnel → `PublicMediaError`, pemilihan di `create_app`.
4. Spike gratis: jalankan nyata, `curl` URL publik untuk membuktikan tunnel + Range bekerja. Tanpa biaya OpenRouter.
5. Spike berbayar kecil (butuh persetujuan anggaran): satu job `flux_edit` memakai video unggahan, ±$0,15, untuk membuktikan penyedia bisa mengunduh dari URL ini.
6. Dokumen implementation 10.

## Kriteria selesai
- `make test` hijau dengan test baru. Build frontend hijau.
- Spike gratis: URL publik menyajikan berkas utuh dan 206 untuk Range.
- Spike berbayar: satu klip `flux_edit` sukses dari video unggahan (bila anggaran disetujui). Bila tidak, ditandai belum terbukti.
- Setelah job selesai atau gagal, token tidak lagi bisa diakses dan proses cloudflared berhenti setelah idle.

## Pertanyaan terbuka
1. Boleh memakai `cloudflared` quick tunnel (URL acak, tanpa akun) ini, dengan komputer harus tetap menyala selama job?
2. Anggaran spike berbayar ±$0,15 untuk satu job `flux_edit`: setuju?

## Riwayat
- 2026-10-21: draft awal.
