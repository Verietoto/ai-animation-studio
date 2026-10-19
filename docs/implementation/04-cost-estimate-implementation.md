# 04 - Cost Estimate (Implementation)

Plan: `docs/plan/04-cost-estimate-plan.md`
Grill: `docs/grill/04-cost-estimate-grill.md`

## Yang dibangun
- `backend/app/pricing.py`: estimator video (SKU per detik, per token video, biaya gambar input/referensi, minimum per generasi) dan gambar (per gambar, per megapiksel, per token dengan riwayat atau batas atas). Tingkat keyakinan: `exact`, `formula`, `history`, `bound`, `unknown`.
- `POST /api/estimate`: perkiraan tanpa efek samping; parameter divalidasi sama seperti generate.
- Semua endpoint generate (`/api/clips`, `/extend`, `/images/{id}/edit`) mewajibkan `confirmed_cost` (atau `accept_unknown_cost`). Server menghitung ulang, menolak 409 bila estimasinya lebih tinggi dari yang dikonfirmasi, 402 bila melebihi `MAX_COST_PER_JOB_USD` atau batas harian (biaya aktual + estimasi job aktif + estimasi baru).
- Cek anggaran, kirim ke provider, dan pencatatan `estimated_cost` dalam satu `RLock` (tanpa celah balapan).
- Migrasi DB bernomor (`PRAGMA user_version` = 2) dengan kolom `estimated_cost`.
- UI: baris perkiraan biaya yang ikut berubah menurut parameter, dialog konfirmasi (rincian dasar, sisa anggaran, centang khusus untuk biaya tidak diketahui), 409/402 membuka ulang dialog dengan estimasi terbaru; library menampilkan perkiraan vs biaya nyata.

## File yang diubah
`backend/app/{pricing,service,main,db,config,openrouter}.py`, `backend/tests/{test_pricing,test_cost_guard,conftest,test_api}.py` + fixture nyata di `backend/tests/fixtures/`, `frontend/src/{estimate.tsx,api.ts,styles.css,pages/*}`, `scripts/fake_openrouter.py`, `.env.example`.

## Penyimpangan dari plan
- Tingkat keyakinan `bound` ditambah (plan hanya `unknown`): untuk harga per token tanpa riwayat, estimator memberi batas atas konservatif (4.500 token output + 2.000 token per gambar input) alih-alih "tidak diketahui", sehingga batas per job tetap berlaku. `unknown` hanya untuk model tanpa SKU yang cocok atau satuan tak didukung (megapiksel-detik).
- Kalibrasi dari riwayat memakai `images` saja; untuk video token (Seedance) rumus piksel dengan margin 10%.
- Tombol "generate" tidak dinonaktifkan oleh estimasi `bound`; hanya `blocked` (melebihi batas) yang menonaktifkan.

## Temuan grill yang sudah ditangani
| Temuan | Penanganan | Bukti |
|---|---|---|
| Parser salah baca satuan | Tes tangan untuk 14 kombinasi model/resolusi/audio + semua 30 model nyata tidak melempar error | `test_pricing.py` |
| Estimasi browser tidak dipercaya | Hitung ulang server, tolak bila lebih tinggi | `test_confirmed_cost_lower_than_server_estimate_is_rejected` |
| Balapan batas harian | `RLock` + estimasi job aktif dihitung | `test_concurrent_requests_cannot_both_pass_the_budget_check`, `test_daily_limit_counts_active_jobs_not_only_finished_ones` |
| Biaya token tanpa riwayat | `bound` konservatif, riwayat setelah job pertama | `test_image_token_pricing_*` |
| Resolusi/durasi kosong | Rentang konservatif | `test_unspecified_resolution_*`, `test_unspecified_duration_*` |
| Biaya input dan minimum | Dihitung | `test_minimum_per_generation_applies`, `test_reference_images_add_cost`, kalibrasi Grok |
| Biaya job gagal | Biaya nyata bila dilaporkan, selain itu 0 | `test_failed_job_without_cost_is_not_counted` |
| Migrasi DB | `user_version` + ALTER idempoten | `test_old_database_is_migrated` |
| Frame yatim saat extend ditolak | Dihapus | `test_extend_rejection_leaves_no_orphan_frame` |
| Respons estimasi usang di UI | Nomor urut permintaan, abaikan yang lama | kode `useEstimate` |

## Bug nyata yang ditemukan tes saat pengerjaan
- Tarif dengan suara kalah oleh SKU i2v tanpa suara (Kling): diperbaiki dengan memprioritaskan SKU suara.
- `minimum_cents_per_generation` tidak dibagi 100 (Aleph tampil $56): diperbaiki.

## Pengujian (perintah dan hasil nyata)
- `.venv/bin/python -m pytest backend`: **71 lulus** (31 tes estimator, 13 tes pengaman biaya termasuk 4 request paralel dan migrasi DB lama, 27 tes fitur 01/02).
- Frontend: `npm run build` lulus. Uji UI di Chromium (server palsu): perkiraan $0,12 tampil dan berubah menurut resolusi, dialog muncul, generate, extend (dengan dialog), gabung, edit foto (dengan dialog) lulus.
- **Uji nyata OpenRouter:**
  - Tanpa konfirmasi: 409. Dengan konfirmasi: job jalan. Grok lite 1 detik 480p: **perkiraan $0,03, biaya nyata $0,03** (cocok persis).
  - Estimasi nyata (gratis) untuk model lain: Seedance 2.5 10 detik 720p $2,54 (ditolak oleh batas per job $1), Seedance 2.0 mini 4 detik 480p $0,148, Veo 3.1 8 detik 1080p dengan suara $3,20 (ditolak), Wan 3.0 5 detik 720p $0,50, gpt-image-2 edit batas atas $0,151 (biaya nyata sebelumnya $0,012 sampai $0,015).

## Masalah tersisa
- Rumus token Seedance belum dicocokkan dengan tagihan nyata (hanya dengan angka di review); margin 10%.
- Batas atas `bound` untuk gambar bisa terlalu pesimis atau, untuk gambar resolusi sangat tinggi, terlalu optimis; hasil nyata pertama mengisi riwayat.
- Job gagal tanpa biaya yang dilaporkan dianggap $0.
- Estimator belum dipakai untuk fitur tiru gerakan dan karakter (plan 03), tetapi `mode="edit"`, `video_input_seconds`, dan `reference_images` sudah didukung.

## Riwayat
- 2026-10-19: iterasi 1.
