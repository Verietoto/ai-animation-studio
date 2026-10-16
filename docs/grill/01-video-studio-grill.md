# 01 - Video Studio (Grill)

Plan terkait: `docs/plan/01-video-studio-plan.md`

Keparahan: **T** tinggi, **S** sedang, **R** rendah.

## Lubang pada plan
1. **(T) Kontrak API OpenRouter belum pernah diuji nyata.** Seluruh desain bertumpu pada hasil pencarian web; akses ke openrouter.ai dari lingkungan pengembangan ini diblokir dan tidak ada API key. Nama field (`frame_images`, `input_references`, `generate_audio`) dan bentuk respons job belum terverifikasi.
   - Mitigasi: semua kontak OpenRouter lewat satu klien tipis dengan model respons longgar (field tak dikenal diabaikan), diuji dengan mock berdasar dokumen, dan ada skrip `scripts/smoke_openrouter.py` untuk uji nyata begitu key tersedia. Fitur ditandai "belum diuji nyata" di catatan implementasi.
2. **(T) Extend native Seedance 2.5 tidak pasti jalan** (issue typescript-sdk #1096: butuh `duration=-1`/`aspect_ratio=adaptive` yang tidak diekspos).
   - Mitigasi: jalur extend default = frame terakhir + ffmpeg (model-agnostik). Extend native dibuat opsional, aktif hanya bila `/videos/models` menyatakan mendukung; kalau gagal, otomatis fallback.
3. **(S) Plan tidak menyebut kontinuitas.** Extend lewat frame terakhir memutus gerak (kecepatan, kamera) dan suara; sambungan bisa terlihat.
   - Mitigasi: prompt extend menyertakan deskripsi klip sebelumnya; opsi crossfade pendek di ffmpeg; batas jumlah rantai extend di UI dengan peringatan penurunan kualitas.
4. **(S) Copy gerakan + suara belum punya jalur teruji.** Bila Seedance tidak cukup, plan tidak punya langkah cadangan yang konkret.
   - Mitigasi: fase 2 diawali spike riset/uji; tidak dibangun di iterasi ini.

## Risiko
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| Biaya membengkak (video mahal, retry, klik ganda) | Tinggi | Tinggi | Batas biaya per job dan harian di config; estimasi biaya sebelum kirim; tombol kirim dikunci selama submit; idempotency key per permintaan |
| API key bocor | Tinggi | Sedang | Key hanya di env backend; tidak pernah dikirim ke frontend; `.env` di `.gitignore`; log disanitasi |
| Job tertahan/hilang bila server restart saat polling | Sedang | Tinggi | Status job disimpan di DB; saat startup, job `pending` dilanjutkan polling |
| Provider mengubah API tanpa pemberitahuan | Sedang | Sedang | Validasi parameter dari `/videos/models` saat runtime; model respons longgar; adapter per model |
| Konten referensi melanggar kebijakan/hak cipta/wajah orang nyata (copy gerakan+suara) | Tinggi | Sedang | Peringatan di UI; catat asal aset; tidak ada fitur kloning suara pihak ketiga tanpa persetujuan di iterasi ini |
| URL publik untuk aset bocor/ditebak | Sedang | Rendah | Signed URL berumur pendek untuk S3; nama file acak (UUID) |
| Upload berbahaya/terlalu besar | Sedang | Sedang | Batas ukuran, validasi tipe dengan ffprobe/Pillow, tolak selain gambar/video yang dikenal |
| SSRF bila backend mengambil URL dari user | Tinggi | Rendah | Backend hanya mengunduh dari host OpenRouter hasil job; tidak ada fitur "impor dari URL" |

## Edge case
- Job selesai sukses tapi unduhan konten gagal atau kosong: status `failed_download`, bisa dicoba ulang tanpa membayar ulang.
- Job gagal di provider (moderasi, timeout): simpan pesan error asli, jangan tampilkan stack trace.
- Polling tanpa batas: timeout maksimum per job (config), backoff bertahap.
- Gambar dengan EXIF rotasi, CMYK, alpha, atau ukuran/aspect ratio tidak didukung model: normalisasi sebelum kirim; tolak dengan pesan jelas.
- Durasi/resolusi/aspect ratio di luar daftar model: validasi di backend dan UI (bukan hanya UI).
- Klip pertama tanpa audio lalu digabung dengan klip beraudio: ffmpeg concat gagal atau audio putus; selalu normalisasi (codec, fps, sample rate, trek audio senyap bila kosong).
- Dua klip beda resolusi/fps saat digabung: transcode ke profil seragam.
- Frame terakhir hitam/fade-out: ambil beberapa frame terakhir dan pilih yang valid, atau minta user memilih.
- Dua tab/klik ganda memulai job duplikat: idempotency key.
- Nama file dengan karakter khusus, path traversal pada penyimpanan lokal: nama disimpan sebagai UUID, path divalidasi.

## Potensi bug
- Race condition polling vs. update status dari request lain pada SQLite: pakai satu penulis/transaksi pendek, `WAL`.
- Mengira `frame_images` dan `input_references` bisa dikirim bersamaan: frame image menang; UI melarang kombinasi yang membingungkan.
- Konversi biaya: model dihitung per token/megapiksel/gambar/detik; jangan menjumlah tanpa satuan. Simpan biaya apa adanya dari respons job bila ada, kalau tidak, tandai "estimasi".
- Zona waktu/penyimpanan timestamp: simpan UTC.
- `ffmpeg` tidak terpasang di mesin user: cek saat startup dengan pesan jelas.

## Asumsi yang belum terbukti
- Respons `POST /videos` mengembalikan id/polling URL dengan bentuk seperti di dokumen.
- Biaya dikembalikan di respons job.
- Video hasil bisa dipakai kembali sebagai `input_references` lewat URL HTTPS publik.
- Seedance 2.5 benar-benar mengganti subjek dengan gambar referensi sambil mempertahankan gerak dan suara.

## Keputusan setelah grilling (perubahan pada plan)
- Extend default = frame terakhir + ffmpeg; extend native opsional dengan fallback otomatis.
- Fase 2 (copy gerakan+suara) tidak dibangun di iterasi ini; hanya spike setelah ada API key.
- Tambah wajib: batas biaya, idempotency key, resume job saat startup, normalisasi media, smoke test nyata terpisah.
- Iterasi 1 = image-to-video, extend (ffmpeg), library, edit foto (plan 02).

## Riwayat
- 2026-10-16: draft awal.
