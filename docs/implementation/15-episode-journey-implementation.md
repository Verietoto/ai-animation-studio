# 15 - Alur pembuatan episode per langkah (Episode Journey) (Implementation)

Plan: `docs/plan/15-episode-journey-plan.md` · Grill: `docs/grill/15-episode-journey-grill.md`
Tanggal: 2026-10-26 · Status: fase A, B, dan C selesai dibangun. Backend teruji (278 test), build frontend hijau, spike AI nyata berhasil. **Menunggu uji manual oleh user** (UI) dan uji Seedance dengan previs asli (butuh persetujuan biaya baru).

User menyetujui ketiga fase sekaligus ("oke langsung aja sampai fase c"), jadi tidak ada jeda persetujuan antar fase.

## Yang dibangun
### Backend (fase A)
- `db.py` migrasi **v12**: tabel `film_characters`, `film_locations`; kolom `films.script`, `script_split_hash`, `previs_skipped`; `scenes.script_excerpt`. Isi awal dari adegan yang ada (urutan kemunculan pertama, idempoten).
- `script.py` (baru, murni): parser mention `@[…]` / `#[…]` (regex yang sama dengan frontend), `analyze` (mention tak dikenal / nama ganda), `rename`, `digest`, `clean_script` (maks 20.000), `clean_split` (pembersih adegan dari AI/klien), serta prompt sistem dan pengguna untuk naskah dan pemecahan.
- `journey.py` (baru):
  - `set_cast`: validasi milik workspace (404 lintas workspace), tanpa id ganda, nama unik di dalam episode, tanpa `[ ]`, maks 30 karakter / 40 latar; mengeluarkan yang masih dipakai adegan → 409 menyebut nomor adegannya, atau `release` untuk melepasnya.
  - `ensure`: pemeran/latar yang dipakai adegan (termasuk lewat Mode lanjutan) otomatis masuk episode.
  - `state`: keadaan alur untuk stepper (pemeran + kesiapan, naskah, analisis mention, `script_changed`, kemajuan adegan/blockout/previs/keyframe/video/render).
  - `rename_location`: mention `#[nama lama]` di naskah episode yang memakai latar itu ikut diganti.
  - Pembersihan di `delete_character`, `delete_location`, `Films.delete`, dan hapus workspace permanen.
- `scenes.py`: `update` memanggil `journey.ensure`; field `script_excerpt`; nama latar menolak `[ ]`; `update_location` menulis ulang mention. `service.create_character` menolak `[ ]`.
- `main.py`: `GET /api/films/{id}/journey`, `PUT /api/films/{id}/cast`; `PUT /api/films/{id}` menerima `script` dan `previs_skipped`.

### Backend (fase B)
- `textai.py` (baru): satu jalur panggilan model teks berbiaya (estimasi, `authorize`, catat `text_jobs` sebelum parsing, parse JSON). `scenes.generate_blockout` (plan 14) direfaktor memakai jalur ini; test plan 14 tetap hijau.
- `journey.py`: `script_draft` (AI menulis naskah, draf), `split_draft` (AI memecah naskah jadi adegan, draf), `apply_split` (mode `append` / `replace`).
  - Draf divalidasi ulang saat diterapkan terhadap pemeran/latar episode **saat itu**; id asing dibuang per pemeran/latar dengan peringatan, tidak pernah menciptakan entitas.
  - `replace` ditolak (409) bila ada adegan dengan keyframe/video/blockout/previs; `append` ditolak bila total > 50.
  - Hash naskah disimpan saat diterapkan → penanda "naskah berubah".
- Endpoint: `POST /api/films/{id}/script/draft`, `/split`, `/split/apply`; kind estimasi `episode_script`, `episode_split`.

### Backend (fase C)
- `Scenes.previs_video_plan` / `previs_video`: video adegan dari previs lewat Seedance reference. Video previs + gambar pemeran (maks 3 gambar, pemeran dulu lalu latar) dan prompt yang menyebut warna manekin tiap tokoh ("Image 1 shows CHARACTER Rani (the blue mannequin)"). Hasilnya klip `motion` yang ditautkan ke adegan (`scene_id`) dan, bila adegan belum punya video bagus, menjadi videonya.
- `Motion.create` menerima `scene_id`. Endpoint `POST /api/scenes/{id}/previs-video`; kind estimasi `scene_previs_video`.

### Frontend
- `storyboard/journey/`:
  - `Stepper.tsx`: lima langkah, tanda selesai (diturunkan dari data), tanda "opsional" (langkah 4), tanda peringatan, langkah awal otomatis (episode lama dengan hasil langsung ke Animasi), petunjuk "apa yang kurang" tanpa memblokir.
  - `StepCast.tsx`: centang karakter dan latar episode, kesiapan (tanpa lembar tampilan / tanpa gambar), tambah latar baru, konfirmasi bila perlu melepas dari adegan.
  - `StepScript.tsx`: editor naskah dengan simpan otomatis, autocomplete saat mengetik `@`/`#` (↑↓, Enter/Tab, Esc), tombol sisipkan, pratinjau berwarna, daftar mention tak dikenal + "tambahkan", dan AI bantu tulis (estimasi → konfirmasi → draf: ganti / tambahkan / buang).
  - `StepTimeline.tsx`: "Pecah naskah dengan AI" (draf dengan peringatan, pilihan tambah/ganti), papan adegan yang sudah ada.
  - `StepPrevis.tsx`: status blockout/previs per adegan, editor 3D, "Susun semua dengan AI" (batch), "Lewati langkah ini".
  - `StepProduce.tsx`: ringkasan, "Buat semua keyframe / video yang belum ada" (batch), video dari previs per adegan, render episode.
  - `batch.tsx`: aksi massal berurutan dengan satu konfirmasi total.
  - `mentions.ts`: parser mention TS.
- `pages/Storyboard.tsx`: stepper dan isi langkah di area utama; tab lama dipindah ke tombol "Mode lanjutan"; inspector adegan muncul mulai langkah Timeline; pintasan keyboard adegan dimatikan di langkah 1–2.
- `Generate.tsx` (`PrevisVideoPanel`), `Inspector.tsx` (video dari previs, "Dari naskah: …"), `Motion.tsx` (daftar referensi tersimpan, termasuk previs).
- `api.ts`, `styles.css`.

## Spike AI nyata (dalam batas $0.05 yang dicatat di plan)
`scripts/spike_journey.py` (2 panggilan Haiku 5.5). Sinopsis satu kalimat → naskah 3.732 karakter dengan **47 mention, semuanya dikenal** (0 tak dikenal) → **14 adegan, 106 detik, 0 peringatan**. Total **$0.0044**. Adegan awal wajar (sawah → Rani berjalan → warung → Budi dan Rani).

## Temuan grill yang ditangani
| Grill | Penanganan |
|---|---|
| Karakter tak bisa diganti nama | Hanya latar yang menulis ulang mention (karakter belum punya endpoint ganti nama). |
| Nama tidak unik | Unik di dalam episode; tolak `[ ]`. Test `test_set_cast_validations_and_state`, `test_names_with_brackets_are_refused`. |
| Penghapusan tak tahu tabel baru | Dibersihkan di karakter, latar, film, workspace. Test `test_deleting_character_location_film_and_workspace_cleans_episode_tables`. |
| Keyframe sinkron/lama | Aksi massal berurutan dari browser, satu konfirmasi total, berhenti saat gagal/melebihi total. |
| Keluaran AI terpotong | `max_tokens` 12.000 untuk pemecahan; naskah maks 20.000. |
| Draf basi saat diterapkan | `apply_split` memvalidasi ulang. Test `test_apply_split_revalidates_against_current_episode_cast`. |
| Menimpa kerja manual | `replace` diblokir bila ada hasil. Test `test_apply_split_replace_is_blocked_by_results_and_works_otherwise`. |
| Pemeran lewat Mode lanjutan | `ensure` otomatis. Test `test_cast_added_to_scene_joins_episode_automatically`. |
| Sorot mention meleset | Pratinjau terpisah di bawah editor, bukan lapisan di belakang textarea. |

**Bug yang ditemukan lewat test:** isi awal migrasi v12 mengurutkan pemeran dengan `GROUP BY … MIN()` sehingga dua pemeran seri bertukar urutan; diganti dengan urutan kemunculan pertama (Python `dict.fromkeys`).

## Menyimpang dari plan
- Dokumen implementation satu berkas dengan bagian per fase (sesuai plan).
- Ganti nama **karakter** dengan tulis ulang mention tidak ada (belum ada endpoint).
- Aksi massal berjalan di browser (bukan satu permintaan server), sesuai grill.
- "Susun semua dengan AI" (previs) menyimpan setiap susunan langsung ke adegannya, tanpa langkah tinjau per adegan; bisa diubah di editor sesudahnya.
- Video dari previs memakai paling banyak 3 gambar: pemeran lebih dulu, latar menyusul bila masih ada tempat.
- Daftar referensi di Tiru Gerakan menampilkan semua referensi tersimpan yang bukan dari klip library.
- Utang yang dicatat: referensi previs milik adegan yang dihapus belum dibersihkan; hasil trim lama juga; `Scenes` masih memuat logika previs-video yang bisa dipindah ke modul sendiri bila membesar.

## Hasil tes
- `make test`: **278 passed** (256 → 278; 22 test baru di `backend/tests/test_journey.py`).
  - Murni: mention, analisis, rename, digest; `clean_split` (id asing, batas pemeran, durasi, 50 adegan).
  - Migrasi v12 isi awal + idempoten; pemeran/latar episode (validasi, lintas workspace, nama ganda, kurung siku, pelepasan); pembersihan karakter/latar/film/workspace; naskah (simpan, analisis mention, batas panjang); rename latar menulis ulang mention.
  - AI naskah (butuh sinopsis, draf tidak tersimpan, biaya tercatat, konfirmasi wajib, jawaban kosong 502); AI pemecahan (id asing dibuang, jawaban rusak 502 tetap berbiaya, `replace`/`append`/batas 50/mode salah, render mengunci perubahan); kemajuan; video dari previs (butuh previs, mengirim video previs + 3 gambar dengan prompt benar, klip tertaut adegan, 404 lintas workspace).
  - Test lama yang berubah hanya nomor versi skema (11 → 12).
- `cd frontend && npm run build`: hijau. Bundel utama ±342 kB; three.js tetap terpisah.
- Parser mention TS vs Python: identik pada 12 teks uji (termasuk batas 80/81 karakter, non-Latin, kurung bersarang), diperiksa dengan node.
- Uji UI dan uji Seedance dengan previs asli: **belum dijalankan** (lihat bawah).

## Uji frontend: diuji manual oleh user
Restart backend dulu (`make dev`): migrasi v12 dan endpoint baru. `PUBLIC_TUNNEL=cloudflared` di `.env` diperlukan untuk video dari previs.
**Fase A**
1. Storyboard → pilih episode: stepper 5 langkah di atas. Episode lama dengan hasil langsung terbuka di langkah Animasi; episode kosong di langkah 1.
2. Langkah 1: centang karakter dan latar; tambah latar baru; karakter tanpa lembar tampilan dan latar tanpa gambar bertanda. Mengeluarkan karakter yang masih dipakai adegan menampilkan pertanyaan "lepaskan dari adegan?".
3. Langkah 2: ketik `@` atau `#` → saran muncul (↑↓, Enter, Esc); klik tombol sisipkan; pratinjau berwarna; mention yang tak ada di episode ditandai merah dengan tombol "tambahkan". Berhenti mengetik ±1 detik → "Tersimpan".
4. Ganti nama sebuah latar di tab Latar (Mode lanjutan) → mention `#[nama lama]` di naskah ikut berganti.
5. Langkah 3: tambah adegan manual, seret urutan; panel kanan mengisi latar/pemeran.
6. "Mode lanjutan" membuka tab lama (Papan, Naskah, Timeline, Latar) dan "Kembali ke alur" menutupnya.
**Fase B**
7. Langkah 2: "Tulis naskah dengan AI" (butuh sinopsis): dialog biaya (± $0.002), draf muncul; Ganti / Tambahkan / Buang.
8. Langkah 3: "Pecah naskah dengan AI" (± $0.005): draf berisi adegan, latar, pemeran + aksi, durasi, peringatan. "Tambahkan di akhir" menambah adegan; "Ganti semua" nonaktif bila ada adegan yang sudah punya hasil. Setelah mengedit naskah, muncul peringatan "naskah berubah".
**Fase C**
9. Langkah 4: "Susun semua dengan AI" (satu dialog total), buka editor 3D per adegan, "Lewati langkah ini".
10. Langkah 5: "Buat semua keyframe yang belum ada" dan "Buat semua video yang belum ada": dialog total biaya, berjalan satu per satu, bisa dihentikan, berhenti bila ada yang gagal. **Berbayar**: coba dengan 1–2 adegan dulu.
11. Adegan dengan previs: "Video dari previs" (Seedance, gaya kartun) di langkah 5 dan di inspector. **Berbayar** (Mini 480p 4 dtk ≈ $0,18). Nilai apakah gerak dan komposisi mengikuti previs dan manekin tidak bocor.
12. Tiru Gerakan: bagian "Referensi tersimpan" menampilkan unggahan, hasil potong, dan previs adegan.

## Riwayat
- 2026-10-26: implementasi fase A, B, C.
