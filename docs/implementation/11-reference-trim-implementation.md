# 11 - Trim video referensi (Implementation)

Plan: `docs/plan/11-reference-trim-plan.md` · Grill: `docs/grill/11-reference-trim-grill.md`
Tanggal: 2026-10-21 · Status: backend selesai dan dites; UI selesai dibangun, **menunggu uji manual oleh user**.

## Yang dibangun
### Backend
- `media.prepare_reference_video(src, out, max_seconds, start=0.0)`: `-ss start` sebelum `-i`, di-encode ulang (akurat); normalisasi piksel/audio sama seperti sebelumnya.
- `config.py`: `max_source_seconds` dari `MAX_SOURCE_SECONDS` (bawaan 120).
- `motion.py`:
  - `Motion.trim(ref_id, start, end, ws)` membuat referensi baru dari rentang; referensi asal tidak berubah.
    - `end` yang melewati durasi dipotong ke durasi.
    - Panjang hasil 1 dtk sampai `MAX_REFERENCE_SECONDS`.
    - Sumbernya selalu `ref["path"]` (klip library maupun unggahan).
    - Hasil potong dari klip library butuh hosting publik; tanpa itu 501 sebelum diproses.
    - Hasil berstatus `source_clip_id = NULL`, jadi disajikan lewat tunnel/S3, bukan URL klip.
  - `add_upload` menyimpan video utuh sampai `MAX_SOURCE_SECONDS`; lebih dari itu 413. Referensi yang lebih panjang dari batas pakai tetap ditolak `_check_ref` sebelum biaya dan sebelum publish.
  - Pesan `_check_ref` kini mengarahkan ke "panel Potong video".
- `main.py`: `POST /api/references/{ref_id}/trim` (`TrimIn`, `allow_inf_nan=False`); `/api/health` mengeluarkan `max_reference_seconds`.

### Frontend
- `api.ts`: `trimReference`, `Health.max_reference_seconds`.
- `pages/Motion.tsx`: `TrimPanel`.
  - Dua penggeser (mulai, akhir, langkah 0,1 dtk) dengan batas 1 dtk sampai batas pakai.
  - Pratinjau berputar hanya di rentang terpilih.
  - Panjang hasil ditampilkan, "Potong" membuat referensi baru dan estimasi biaya dihitung ulang otomatis karena id berubah.
  - Di mode "Animasikan gambar": tombol "Samakan dengan durasi video (N dtk)".
  - Untuk klip library tanpa hosting publik, tombol nonaktif dengan penjelasan.
- `App.tsx`: meneruskan `maxReference`.

## Temuan grill yang ditangani
| Grill | Penanganan |
|---|---|
| Sumber trim = `ref["path"]` | Dipakai untuk semua jenis referensi. |
| Unggahan panjang tidak boleh dipakai sebelum dipotong | `_check_ref` menolak sebelum biaya; test `test_long_upload_kept_whole_but_unusable_until_trimmed`. |
| Trim klip library tanpa hosting | 501 sebelum diproses; test `test_trim_library_clip_needs_public_hosting` dan `…_with_hosting_…`. |
| Parameter waktu aneh | Validasi rentang; test `test_trim_validates_range`. |
| Lintas workspace | 404; test `test_trim_reference_of_other_workspace_is_404` dan sweep `test_workspaces` tetap lolos. |

**Keterbatasan:** NaN/Infinity ditolak (`finite_number`), tetapi FastAPI gagal merangkai pesan errornya dan menghasilkan 500, bukan 422, pada permintaan buatan tangan. Klien nyata (`JSON.stringify`) tidak bisa mengirim nilai itu. Tidak ada test.

## Utang yang dicatat
- Tiap "Potong" membuat berkas baru yang tidak pernah dihapus (sama seperti referensi lain). Belum ada pembersihan.
- Waktu pemotongan video panjang besar (mis. 120 dtk 1080p) di request sinkron tidak diukur; hanya video kecil dites.

## Hasil tes
- `make test`: **211 passed** (203 → 211). 8 test baru di `backend/tests/test_motion.py`: unggahan panjang utuh tapi belum bisa dipakai, batas sumber 413, trim membuat referensi baru dan estimasi turun (< 60% biaya penuh), trim berulang, validasi rentang, klip library tanpa dan dengan hosting, lintas workspace, `health.max_reference_seconds`.
- `cd frontend && npm run build`: hijau.
- Tidak ada uji berbayar untuk fitur ini.

## Uji frontend: diuji manual oleh user
Restart backend dulu. Perlu `PUBLIC_TUNNEL=cloudflared` (atau S3) untuk unggah dan untuk memotong klip library.
1. Tiru Gerakan, unggah video 15–30 dtk: muncul peringatan "Video N dtk; yang dipakai maksimal 10 dtk". Estimasi biaya menampilkan error "potong dulu" sampai dipotong.
2. Geser Mulai dan Akhir: pratinjau berputar hanya di rentang itu. Panjang hasil berubah dan tak bisa kurang dari 1 dtk atau lebih dari 10 dtk.
3. Klik Potong: video referensi diganti hasil potong, panjang sesuai pilihan, estimasi biaya turun sebanding.
4. Mode "Animasikan gambar": pilih durasi 5 dtk lalu "Samakan dengan durasi video (5 dtk)": rentang jadi 5 dtk.
5. Pilih klip library saat hosting publik tidak ada: tombol Potong nonaktif dengan penjelasan. Dengan tunnel aktif, tombol bisa dipakai.
6. Potong lagi hasil potong: berfungsi.

## Riwayat
- 2026-10-21: implementasi awal.
