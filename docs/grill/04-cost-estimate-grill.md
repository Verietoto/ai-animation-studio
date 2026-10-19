# 04 - Cost Estimate (Grill)

Plan terkait: `docs/plan/04-cost-estimate-plan.md`

Keparahan: **T** tinggi, **S** sedang, **R** rendah.

## Lubang pada plan
1. **(T) Estimator yang salah memberi rasa aman palsu.** ~45 nama SKU dengan satuan berbeda; satu salah baca (sen vs USD, per detik vs per token) membuat angka meleset 100x tanpa terlihat.
   - Mitigasi: tes tabel untuk **setiap** model di snapshot nyata `/videos/models` (30 model) dengan nilai yang dihitung tangan untuk kombinasi (resolusi, audio); SKU tak dikenal membuat estimasi `unknown` (bukan menebak); satu uji nyata membandingkan estimasi vs biaya aktual (Grok lite 1 detik 480p: $0,03 vs $0,03 sudah ada).
2. **(T) Estimasi dari browser tidak boleh dipercaya, tapi plan hanya menyebut `confirmed_estimate` tanpa aturan perbandingan.** Bila server menghitung ulang lebih mahal dari yang dikonfirmasi (harga model berubah di antaranya, cache daftar model 5 menit), job harus ditolak, bukan lolos.
   - Mitigasi: server menolak 409 bila `estimasi_server.high > confirmed_cost * 1.0 + 0,0001`; respons menyertakan estimasi baru agar UI bisa meminta konfirmasi ulang. Cache harga berumur pendek (5 menit, sama dengan daftar model).
3. **(T) Perhitungan batas harian masih punya celah balapan dan celah "job aktif".** Dua request bersamaan sama-sama lolos cek sebelum salah satunya tercatat. Job yang belum selesai belum punya biaya aktual sehingga tidak terhitung.
   - Mitigasi: cek dan pencatatan `estimated_cost` dalam satu transaksi/kunci (`Studio._lock`); batas = `biaya aktual hari ini + estimasi job aktif + estimasi baru`. Biaya klip aktif memakai `estimated_cost` sampai biaya aktual masuk.
4. **(S) Sebaran biaya token (gambar gpt-image-2, Seedance) tidak punya batas atas pasti.** Plan menandainya "history/unknown" tetapi tidak menjelaskan tindakan bila riwayat kosong, padahal itu kasus pengguna baru.
   - Mitigasi: tanpa riwayat -> `unknown`; UI wajib centang "saya mengerti biaya tidak diketahui" dan batas per job tetap dicek terhadap *pagu konservatif* khusus satuan token yang dipakai estimator (per model, mis. token output maksimum yang diketahui) bila ada; bila tak ada, hanya batas harian yang melindungi. Hasil nyata pertama mengisi riwayat.
5. **(S) Resolusi/durasi/rasio kosong ("default") membuat estimasi ambigu.** Default model tidak diumumkan.
   - Mitigasi: bila kosong, estimasi dihitung sebagai rentang seluruh resolusi yang didukung (low = termurah, high = termahal) sehingga konfirmasi bersifat konservatif; UI menyarankan memilih eksplisit.
6. **(S) Biaya input (gambar, video referensi) dan minimum per generasi mudah terlewat.** Grok membebankan $0,01 per gambar input; Aleph minimum $0,56; Hailuo/HeyGen punya biaya per gambar referensi.
   - Mitigasi: estimator menambahkan SKU input dan menerapkan `minimum_cents_per_generation`; tes untuk masing-masing.
7. **(S) Biaya gagal/ditolak provider.** Job `failed` kadang tetap ditagih, kadang tidak; plan tidak menyebut.
   - Mitigasi: biaya aktual dari `usage.cost` dipakai bila ada, termasuk untuk job gagal; bila tidak ada, job gagal dihitung 0 di batas harian tetapi estimasinya tetap tercatat.
8. **(S) Migrasi DB tidak dirancang** (kolom `estimated_cost`); `CREATE TABLE IF NOT EXISTS` tidak mengubah tabel lama.
   - Mitigasi: migrasi bernomor via `PRAGMA user_version` dengan `ALTER TABLE ADD COLUMN` idempoten + tes membuka DB skema lama.
9. **(R) Perubahan antarmuka API merusak klien lama.** Menambah `confirmed_cost` wajib membuat semua pemanggil lama (tes, skrip) gagal.
   - Mitigasi: hanya frontend dan tes yang memanggil API; keduanya diperbarui. Dokumentasikan di README.

## Risiko
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| Dialog konfirmasi jadi kebiasaan (klik OK tanpa baca) | Sedang | Tinggi | Batas per job dan harian tetap penegak utama; dialog menampilkan sisa anggaran |
| SKU baru muncul di API, parser menganggap unknown terus | Rendah | Sedang | Log SKU tak dikenal; fixture diperbarui berkala |
| Estimasi terlalu pesimis (high) membuat job wajar ditolak | Sedang | Sedang | Batas per job dapat diubah lewat config; pesan penolakan menyebut angka dan cara mengubahnya |
| Harga berubah antara estimasi dan eksekusi | Rendah | Rendah | Aturan nomor 2 |

## Edge case
- `duration` kosong atau bukan bilangan bulat: tolak sebelum estimasi.
- Model tanpa `pricing_skus` atau SKU kosong -> `unknown`.
- Resolusi ada di model tetapi tak ada SKU berakhiran resolusi itu (Veo 1080p): pakai SKU tanpa akhiran (tier default) dan tandai `basis` jelas.
- `generate_audio` pada model tanpa audio: backend sudah menolak (fitur 01); estimator memakai SKU tanpa audio.
- Estimasi 0 (model gratis): tampil $0 dan tetap lewat konfirmasi.
- Nilai uang float: akumulasi pembulatan; simpan dan bandingkan dengan toleransi 1e-4, tampil 4 desimal bila < $0,01.

## Potensi bug
- Satuan: `cents_*` dibagi 100; `duration_seconds*` sudah USD; `video_tokens*` USD per token. Tes eksplisit tiap satuan.
- Rumus token memakai piksel: 480p = 854x480 (bukan 640x480); rasio non-16:9 memengaruhi lebar. Diverifikasi dengan angka resmi review Seedance 2.5 ($0,103/dtk 480p, $0,231/dtk 720p).
- Race UI: respons estimasi lama menimpa yang baru saat parameter cepat berubah; abaikan respons usang.
- Estimasi dipanggil saat klik, bukan hanya saat render: dialog selalu memakai respons segar.

## Asumsi yang belum terbukti
- Rumus token Seedance mencocokkan tagihan nyata (hanya cocok dengan angka di review).
- `SKU tanpa akhiran` = tier default (Veo, Hailuo).
- Biaya job gagal.

## Keputusan setelah grilling (perubahan pada plan)
- `confirmed_cost` wajib; server menolak bila estimasinya lebih tinggi (409) atau melebihi batas (402); `accept_unknown_cost` untuk kasus unknown.
- Batas harian memakai biaya aktual + estimasi job aktif, dalam satu kunci.
- Default batas per job $1 (config `MAX_COST_PER_JOB_USD`); konfirmasi di setiap job.
- Resolusi kosong = rentang konservatif.
- Migrasi DB bernomor; tes tabel dari snapshot nyata; log SKU tak dikenal.

## Riwayat
- 2026-10-19: draft awal.
