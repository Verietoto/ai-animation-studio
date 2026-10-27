# 11 - Trim video referensi (Grill)

Plan terkait: `docs/plan/11-reference-trim-plan.md`
Tanggal: 2026-10-21. Temuan dari membaca `motion.py` (`add_upload`, `add_from_clip`, `_save_ref`, `_check_ref`, `_public_url`, `create`), `media.prepare_reference_video`, endpoint `/api/references*` di `main.py`, dan sweep lintas workspace di `test_workspaces.py`.

## Lubang pada plan
1. **Plan menyebut sumber klip library diambil "lewat `get_clip`", padahal tidak perlu.** `add_from_clip` sudah menyimpan `ref["path"]` = jalur berkas klip itu. Jadi `trim` cukup memakai `ref["path"]` untuk semua jenis referensi. Satu cabang lebih sedikit.
2. **Unggahan panjang tanpa trim tidak boleh bisa dipakai.** Setelah unggahan tidak lagi dipotong otomatis, referensi 100 dtk akan tersimpan. `_check_ref` sudah menolaknya (> `MAX_REFERENCE_SECONDS`) sebelum biaya dan sebelum `publish`, jadi tidak ada risiko biaya atau berkas publik. Yang perlu: pesan error dan UI mengarahkan ke panel trim.
3. **Estimasi sebuah referensi panjang gagal 400.** UI memanggil `/api/estimate` begitu referensi dipilih; untuk referensi panjang hasilnya error "melebihi batas". Panel trim harus tetap terlihat dan terbuka saat itu, dan error estimasi dijelaskan sebagai "potong dulu".
4. **Seedance + trim.** Mode `reference` memakai durasi keluaran terpisah. Tombol "samakan" menimpa rentang, bukan durasi. Bila user mengubah durasi setelah memotong, referensi tidak ikut berubah. Dibiarkan; user menekan tombol lagi.
5. **Batas jumlah berkas.** Plan menyebut risiko disk tetapi tidak mengusulkan batas. Trim memakai satu hasil per klik; hasil lama tetap di disk seperti referensi sekarang. Dicatat sebagai utang, bukan diselesaikan di sini.

## Risiko (dampak, kemungkinan, mitigasi)
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| Trim klip library tanpa hosting publik menghasilkan referensi yang tak bisa dipakai | Biaya waktu, membingungkan | Sedang | Server menolak 501 sebelum memproses; UI menonaktifkan tombol dengan penjelasan. |
| Parameter waktu aneh (negatif, NaN, start > end, > durasi) | ffmpeg error / berkas kosong | Sedang | Validasi ketat di server; NaN/Infinity ditolak oleh Pydantic (`allow_inf_nan=False`). |
| `-ss` sebelum `-i` meleset | Potongan tidak pas | Rendah | Di-encode ulang, jadi akurat; test memeriksa panjang hasil. |
| Referensi tanpa audio | Gagal map audio | Rendah | `prepare_reference_video` sudah memakai `-an` bila tak ada audio. |
| Hasil potong terlalu pendek | Provider menolak | Sedang | Minimal 1 dtk. |

## Edge case
- `end` sedikit melebihi durasi sumber (pembulatan UI): di-clamp ke durasi.
- Referensi dari workspace lain: 404 (sweep `ID_PARAMS` sudah mencakup `ref_id`; route baru harus lolos sweep).
- Trim berulang pada hasil potong: diizinkan, sumbernya berkas hasil potong.
- Berkas referensi hilang dari disk: error jelas, bukan crash.

## Potensi bug
1. Sweep `test_workspaces` mengirim body generik; route trim dengan body wajib bisa memberi 422 sebelum 404. Cek saat menjalankan test; bila perlu, id divalidasi sebelum body.
2. `_save_ref` menandai `trimmed` memakai `source_duration`; untuk hasil potong dari referensi, `source_duration` = durasi sumber agar chip "dipotong" benar.
3. Unggahan lama (sudah dipotong ke 10 dtk) tetap valid.

## Asumsi yang belum terbukti
- Pemotongan + normalisasi video 120 dtk 1080p selesai dalam waktu wajar di request sinkron (ffmpeg `veryfast`). Diukur di test dengan video kecil; video besar nyata tidak diukur.

## Keputusan setelah grilling (perubahan pada plan)
- `trim` memakai `ref["path"]` untuk semua sumber.
- `GET /api/health` mengeluarkan `max_reference_seconds` agar UI tidak menebak.
- Pesan `_check_ref` diubah: "potong dengan panel trim".
- Sisa berkas hasil potong dicatat sebagai utang di implementation 11.

## Riwayat
- 2026-10-21: grill awal.
