# 08 - Storyboard per episode dan adegan (Implementation)

Plan: `docs/plan/08-episode-scene-storyboard-plan.md` (+ Revisi 1). Grill: `docs/grill/08-episode-scene-storyboard-grill.md` (+ Grill revisi 1).

- Status: **selesai di kode**: tahap tanpa biaya (naskah, latar, tampilan, episode, render) dan tahap berbayar (latar dari teks, keyframe, video dari adegan, take, durasi rencana; lihat "Revisi 1" di bawah). Spike $0,2413 dari $0,50 (`08-episode-scene-storyboard-spike.md`). **Uji frontend menunggu user.** Mode "bertahap" sengaja tidak dibuat (spike: tidak lebih baik).
- Tanggal: 2026-10-20

## Yang dibangun
**Backend**
- `backend/app/db.py`: migrasi **v9**. Tabel baru `locations`, `outfits`, `scenes`, `scene_cast`; kolom `films.number/synopsis/aspect_ratio`. Film lama menjadi episode (nomor urut `created_at`), tiap id di `clip_ids` menjadi satu adegan (duplikat tetap, klip yang sudah terhapus menjadi adegan tanpa video). Kolom `clip_ids` dibiarkan, tidak dipakai lagi.
- `backend/app/scenes.py` (baru): `Scenes` untuk adegan (tambah dengan pewarisan, ubah parsial, hapus, duplikat naskah, urut), latar, dan tampilan/baju. Semua dibatasi workspace.
- `backend/app/films.py`: episode berbasis adegan. `public` menghitung `scene_count`, `ready_count`, `clip_ids` turunan. `detail` memuat `scenes`. Render memakai video terpilih tiap adegan; adegan tanpa video menolak render (409) dan muncul sebagai peringatan. `detach_clip` kini mengosongkan `scenes.clip_id` (adegan tetap ada).
- `backend/app/service.py`: `delete_image` menolak gambar yang dipakai latar/tampilan (409) dan mengosongkan keyframe adegan secara atomik. `delete_character` membersihkan `scene_cast` dan `outfits` dalam satu transaksi.
- `backend/app/workspaces.py`: `delete` ikut membersihkan 4 tabel baru; `copy` karakter ikut menyalin tampilannya (beserta gambarnya).
- `backend/app/main.py`: endpoint `POST /api/films/{id}/scenes`, `PUT /api/films/{id}/scene-order`, `PUT|DELETE /api/scenes/{id}`, `POST /api/scenes/{id}/duplicate`, `GET|POST /api/locations`, `PUT|DELETE /api/locations/{id}`, `GET|POST /api/characters/{id}/outfits`, `PUT|DELETE /api/outfits/{id}`. `clip_ids` di `PUT /api/films/{id}` kini 422. Model update adegan menolak field asing (`extra="forbid"`). `GET /api/characters` memuat `outfits`.

**Frontend**
- `api.ts`: tipe dan metode baru. `pages/Storyboard.tsx` ditulis ulang: daftar episode (nomor, progres), tampilan **Papan / Naskah / Timeline / Latar**, inspector adegan, simpan otomatis, polling hanya saat ada render/video berjalan, shortcut `N` `D` panah.
- `storyboard/fields.tsx` (`SaveText`, `CastEditor`), `storyboard/Views.tsx` (Board, ScriptView, TimelineView), `storyboard/Inspector.tsx`, `storyboard/Locations.tsx`.
- `outfits.tsx`: lemari tampilan di kartu karakter (`pages/Characters.tsx`) dan tombol **Simpan ke karakter…** pada hasil Edit Foto (`pages/EditPage.tsx`). Prompt Edit Foto tidak disentuh.
- `App.tsx`: "Tambah ke storyboard" kini membuat adegan dari klip di episode terakhir (`POST /films/{id}/scenes`).
- `styles.css`: blok "storyboard per episode (plan 08)".

## Temuan grill yang ditangani
| Grill | Penanganan |
|---|---|
| 1 | Prompt Edit Foto tidak diubah; compose belum dibuat (menunggu spike) |
| 4 | "Tambah ke storyboard" dipindah ke endpoint adegan; `clip_ids` di PUT → 422 (tes) |
| 5 | Take dipilih manual dari library; auto-pilih dari generate menyusul bersama generate |
| 6 | `films.aspect_ratio` ada dan bisa diubah per episode; belum dipakai generate |
| 7 | PUT adegan parsial + respons terlama diabaikan + simpan saat fokus lepas/dilepas dari layar; gagal simpan tidak menimpa teks |
| 8 | `scene-order` 409 bila himpunan beda; nomor dirapatkan ulang dalam transaksi (tes) |
| 9 | `delete_image` menjaga gambar latar/tampilan, mengosongkan keyframe (tes) |
| 10, 11 | Hapus karakter/klip melepas dari adegan tanpa menghapus adegan (tes) |
| 12, 13 | Batas panjang per field; dialog hanya catatan, tidak dikirim ke AI |
| 14 | Hapus workspace membersihkan tabel baru; salin karakter menyalin tampilan (tes) |
| 15 | Nomor episode diedit manual |
| 18 | Tampilan boleh teks saja (gambar atau deskripsi, minimal salah satu) |
| 22 | Endpoint tampilan memakai `get_image/get_character(ws)`; masuk sapuan lintas workspace |

## Deviasi dari plan
- **Take belum ada daftar.** Kolom `images.scene_id`/`clips.scene_id` ditunda sampai generate dibuat (YAGNI: belum ada yang menulisnya). Sekarang user memilih keyframe/video dari library; "daftar take hasil generate" ikut tahap berbayar. Label "Ep 3 · Adegan 4" di Library (grill 16) ikut ditunda.
- `Workspaces.jobs` tidak diubah (sesuai grill 14).
- Duplikat adegan menyalin naskah saja, tanpa keyframe/video.
- Tombol "Buat keyframe" dan "Buat video" **tidak ada**; inspector menyatakan "menyusul".

## Revisi 1: tahap berbayar (user: "0.5 dolar", lalu "oke go")
Dibangun setelah spike (hasil + keputusan di `08-episode-scene-storyboard-spike.md`).
- **Migrasi v10**: `scenes.planned_seconds`, `images.scene_id`, `clips.scene_id` (daftar take; ditunda di tahap pertama).
- `backend/app/sceneprompt.py` (baru, murni): `keyframe_prompt`, `video_prompt`, `location_prompt`. `editprompt.py` tidak disentuh.
- `backend/app/openrouter.py`: `generate_image` (teks ke gambar tanpa `input_references`).
- `backend/app/scenes.py`: `keyframe_plan`/`keyframe` (gambar 1 = latar, lalu satu gambar per pemeran, satu panggilan; rasio episode dikirim bila model mendukung), `video_plan`/`video` (keyframe terpilih, prompt gerakan, rasio episode, `scene_id` di klip), `location_plan`/`location_image` (latar dari deskripsi, rasio 16:9). Estimasi dan generate memakai `*_plan` yang sama. Dikunci (409) saat episode dirender.
- **Aturan pilih otomatis**: keyframe hasil baru dipilih hanya bila adegan belum punya keyframe; video baru dipilih hanya bila adegan belum punya video atau video terpilihnya gagal/terhapus. Selain itu hasil baru jadi take (`keyframe_takes`, `video_takes`), dipilih manual.
- `backend/app/main.py`: `POST /api/scenes/{id}/keyframe|video`, `POST /api/locations/{id}/image`; estimasi `scene_keyframe`, `scene_video`, `location_image` (`inputs` dikembalikan). `PUT /api/scenes/{id}` menerima `planned_seconds` (1-120 atau kosong).
- Durasi rencana: total per episode (`planned_seconds` di daftar/detail episode); durasi bawaan video = rencana dibulatkan ke durasi yang didukung model.
- Pembersihan: hapus adegan/episode melepas `scene_id` di gambar dan klip (hasil tetap di library).
- Frontend: `storyboard/Generate.tsx` (`KeyframePanel`, `VideoPanel`, `LocationImagePanel`, `Takes`), field "Durasi rencana" di inspector, "rencana Ns" di kartu, chip "rencana m:ss · jadi m:ss" di header episode, rencana vs jadi di Timeline, tab Latar punya "Buat gambar dari deskripsi". Semua lewat `useEstimate` + `useConfirmedRun` (dialog biaya wajib). Model bawaan keyframe/latar: Seedream 5.0 flash.
- Lightbox: label jenis gambar "Keyframe" dan "Latar".
- Tes: `backend/tests/test_scene_generate.py` (15 tes) + versi skema 10 di 7 tes lama. Estimasi = generate (jumlah gambar input sama) diuji; konfirmasi biaya wajib dan tepat diuji; take tidak menimpa pilihan diuji; tampilan hanya-teks diuji; batas input model dan rasio yang tidak didukung diuji.
- **Tidak diuji dengan model sungguhan**: 3 pemeran, tampilan beda dari gambar karakter, video i2v dari keyframe dua karakter (lihat spike).

## Hasil tes
- `make test`: **181 passed** (166 setelah tahap pertama; 147 sebelum plan 08). Tes baru `backend/tests/test_scenes.py` (19 tes): episode, pewarisan, urut/sisip/hapus/duplikat, batas dan validasi, status keyframe/video, render butuh video di tiap adegan, kunci saat render, latar, tampilan, hapus karakter/outfit/gambar, isolasi workspace, hapus workspace, salin tampilan, migrasi v8→v9 dengan duplikat dan klip terhapus (idempoten). Tes lama diperbarui: versi skema 9, helper film memakai endpoint adegan, `clip_ids` PUT → 404/422. Sapuan `test_every_id_route_rejects_foreign_ids` mencakup `scene_id`, `location_id`, `outfit_id`.
- `cd frontend && npm run build` (tsc + vite): hijau. `grep "fetch("` di `frontend/src` = 1 (satu pintu, header workspace aman).
- Frontend: **diuji manual oleh user** (daftar di bawah). Agent tidak membuka browser.

## Alur yang perlu dicoba user
Restart backend dulu (`make be`): migrasi v9 + endpoint baru.
1. Storyboard lama: film yang sudah ada tampil sebagai "Ep 1 · …", tiap klip menjadi satu adegan dengan video terpilih; Timeline: render tetap berhasil, video sama.
2. Episode baru → tambah adegan di Papan; kartu bisa dipilih dan digeser urutannya; nomor terbarui.
3. Latar: buat dari tab **Latar** (nama, deskripsi, gambar opsional) dan dari dropdown "+ Latar baru…" di inspector; pasang ke adegan; hapus latar → adegan tetap ada.
4. Karakter: di kartu karakter buka "Tampilan / baju", buat satu bergambar dan satu hanya teks; di inspector adegan tambah pemeran, pilih tampilan, isi aksi (maks 3 pemeran).
5. Edit Foto: setelah ada hasil, "Simpan ke karakter…" → sebagai tampilan dan sebagai sudut sheet.
6. Tab **Naskah**: ketik waktu, aksi, dialog di beberapa adegan; indikator "Menyimpan…/Tersimpan"; refresh halaman, isi tetap.
7. Adegan baru mewarisi latar, waktu, pemeran + tampilan dari adegan sebelumnya (aksi kosong). Shortcut `N`, `D`, panah (di luar kolom teks).
8. Pilih video dari library untuk tiap adegan (inspector → Hasil); progres "n/m adegan siap" di daftar episode naik; Timeline → Render episode. Adegan tanpa video: tombol render nonaktif dengan peringatan.
9. Library → "Tambah ke storyboard" pada sebuah video: masuk sebagai adegan baru di episode terakhir.
10. Hapus gambar yang dipakai latar/tampilan: ditolak dengan pesan; hapus karakter yang dipakai di adegan: adegan tetap ada tanpa pemeran itu.
11. Pindah workspace: episode, latar, tampilan terpisah; salin karakter ke workspace lain ikut membawa tampilannya.
12. **Berbayar** (gunakan sedikit dulu): tab Latar → kartu latar → "Buat gambar dari deskripsi": dialog biaya muncul, setelah setuju gambar latar terpasang.
13. Adegan dengan latar bergambar + 1-2 pemeran → inspector "Buat keyframe": estimasi menyebut jumlah gambar; setelah jadi, keyframe terpilih; "Buat keyframe lagi" menambah take tanpa mengganti pilihan; klik take untuk memilih.
14. Isi "Durasi rencana" (mis. 8): kartu menampilkan "rencana 8d"; header episode menampilkan "rencana … · jadi …"; "Buat video" memakai durasi terdekat yang didukung model dan memperingatkan bila beda dari rencana.
15. "Buat video" dari keyframe: job masuk antrian dock, adegan berstatus "video diproses" lalu "siap"; Timeline: Render episode setelah semua adegan siap.
16. Rasio episode (dropdown di header): ubah ke 9:16 lalu buat keyframe/video: hasil mengikuti rasio itu bila model mendukung.

## Riwayat
- 2026-10-20: tahap tanpa biaya diimplementasi dan dites (backend). Tahap berbayar menunggu persetujuan budget spike.
- 2026-10-20: spike $0,2413 (budget $0,50 dari user), lalu tahap berbayar diimplementasi (Revisi 1): 181 tes lulus, build hijau, uji frontend menunggu user.
