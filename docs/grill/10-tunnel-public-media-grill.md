# 10 - Unggah video referensi lewat tunnel sementara (Grill)

Plan terkait: `docs/plan/10-tunnel-public-media-plan.md`
Tanggal: 2026-10-21. Temuan dari membaca `publicmedia.py`, `motion.py`, `service.py` (`_release_published`), `main.py` (`create_app`, `lifespan`), `config.py`.

## Lubang pada plan
1. **Umur token vs lama job.** Plan memakai TTL 3600 dtk. Penyedia mengunduh di awal job, tapi bila tunnel baru terbuka dan job antre lama, token bisa habis sebelum diunduh. S3 punya risiko yang sama. Keputusan: TTL tunnel = `max(PUBLIC_URL_TTL_SECONDS, 7200)`; token tetap dihapus lebih awal oleh `delete(key)` saat job selesai.
2. **Restart backend membuang pemetaan token.** Pemetaan hanya di memori. Job yang sedang jalan saat restart tidak bisa diunduh lagi oleh penyedia. Diterima dan dicatat: sama seperti tunnel putus.
3. **`lifespan` memanggil `studio.public.cleanup(...)` tetapi tidak ada `close()`.** Proses `cloudflared` yatim bila backend berhenti. Perlu `close()` opsional (dipanggil lewat `getattr`) di shutdown.
4. **Dua `publish` bersamaan** (dua unggahan) tidak boleh menyalakan dua tunnel. Perlu lock di sekitar start tunnel.
5. **`/api/health.public_media`** hanya memeriksa `NoPublicMedia`. Untuk tunnel, nilainya true walau `cloudflared` gagal naik; error baru muncul saat publish pertama. Diterima: pesan error dari `PublicMediaError` ditampilkan di UI (sudah ada jalur 501).

## Risiko (dampak, kemungkinan, mitigasi)
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| URL bocor, video terbuka untuk orang lain | Privasi | Rendah | Token 128-bit, hanya GET/HEAD, hanya berkas terdaftar, dihapus setelah job. |
| Penelusuran path / membaca berkas lain | Kebocoran data | Rendah | Server tidak memetakan path ke sistem berkas; hanya `token -> Path` dari dict. Test: `..`, path ganda, token salah → 404. |
| Server berkas menerima Host/Range aneh | Crash thread | Sedang | Parse Range dengan validasi ketat; rentang tidak valid → 416; semua exception di handler ditangkap per request. |
| Tunnel putus saat penyedia mengunduh | Job gagal | Sedang | Tidak bisa dicegah; pesan error provider diteruskan. Biaya job gagal belum diketahui (dicatat di implementation). |
| `cloudflared` tidak ada / gagal | Unggah tidak jalan | Sedang | Cek `shutil.which` di `create_app`; gagal naik dalam 30 dtk → `PublicMediaError` yang jelas. |
| Proses yatim | Sampah proses | Sedang | `close()` di shutdown, `terminate` lalu `kill`; thread idle ikut berhenti. |

## Edge case
- File dihapus dari disk sebelum diunduh: 404, bukan crash.
- `HEAD` mengembalikan `Content-Length` tanpa body.
- `Range: bytes=0-` dan `bytes=-N` (suffix) dan `bytes=a-b`; di luar ukuran berkas → 416.
- Klien menutup koneksi di tengah (`BrokenPipeError`): diabaikan.
- `publish` untuk berkas yang tidak ada → `PublicMediaError`.

## Potensi bug
1. `Popen` dengan `stderr=PIPE` yang tidak dibaca setelah URL ditemukan bisa memblokir `cloudflared` saat buffer penuh. Thread pembaca harus terus menguras stderr sampai proses berhenti.
2. Mencocokkan URL dengan regex yang terlalu longgar bisa menangkap `api.trycloudflare.com` dari log. Regex harus mengecualikan `api.`.
3. Menunggu URL harus memakai batas waktu nyata (bukan loop tanpa akhir bila proses mati lebih dulu).

## Asumsi yang belum terbukti
- Penyedia (FLUX/Aleph/Seedance via OpenRouter) mau mengunduh dari `*.trycloudflare.com` dan mengikuti sertifikatnya. Dibuktikan oleh spike berbayar (±$0,15, disetujui user).
- Penyedia mendukung Range atau mengunduh utuh; keduanya didukung server.
- Quick tunnel bekerja di jaringan user (belum dicoba).

## Keputusan setelah grilling (perubahan pada plan)
- TTL tunnel `max(PUBLIC_URL_TTL_SECONDS, 7200)`.
- `close()` opsional di `lifespan`.
- Satu lock untuk start tunnel; thread pembaca stderr; regex tanpa `api.`.
- Tunnel disuntikkan sebagai fungsi (`starter`) supaya test tanpa jaringan; server berkas diuji nyata di `127.0.0.1`.

## Riwayat
- 2026-10-21: grill awal.
