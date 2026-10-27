# 18 - Storyboard v2 (Implementation)

Plan: `docs/plan/18-storyboard-v2-plan.md` (draf + Revisi 1 + Revisi 2). Grill: `docs/grill/18-storyboard-v2-grill.md`.
Status: **sedang dikerjakan**. Fase 0 tertahan (kredit OpenRouter habis). Backend fase A, B, dan C bagian non-AI selesai (353 tes lulus). Belum ada UI v2; fase C (AI), D, E belum dimulai.

## Fase 0 - Spike Seedance (TERTAHAN: kredit OpenRouter habis)
- Skrip: `scripts/spike_seedance_v2.py` (8 uji: `@Image N`, prompt bertimecode, referensi audio, 9 gambar, dialog Indonesia vs Inggris, kalibrasi biaya 2.0/mini, edit video, katalog TTS). Tanpa plafon biaya (keputusan user, plan 18 Revisi 2); biaya tiap uji ditulis ke `summary.json`.
- Percobaan pertama (2026-10-26) gagal di panggilan pertama (generate gambar aset): `OpenRouter 402 Insufficient credits`. Tidak ada biaya terpakai, tidak ada hasil.
- Dilanjutkan setelah kredit akun OpenRouter ditambah user. Hasil akan ditulis ke `docs/implementation/18-storyboard-v2-spike.md`; plan diperbarui di Riwayat bila temuan mengubah desain.
- Akibat: fase yang bergantung pada format request Seedance (D) belum boleh dikerjakan; fase A/B/C bagian non-AI tidak bergantung.

## Fase A - Pengaturan proyek (backend selesai)
**File berubah**
- `backend/app/db.py`: migrasi **v14**. Kolom `workspaces`: `video_model`, `video_resolution`, `aspect_ratio`, `generate_audio`, `image_model`, `style`. Kolom `images`: `beat_id`, `revision_note`, `input_hash`. Kolom `clips`: `revision_note`, `input_hash`. Rasio proyek diisi dari rasio episode terbanyak per workspace (seri: yang terbaru).
- `backend/app/workspaces.py`: `settings()`, `update_settings()`, penguncian rasio, sinkron `films.aspect_ratio`, konstanta `RATIOS`/`RESOLUTIONS`.
- `backend/app/main.py`: `SettingsIn`, `GET/PUT /api/workspaces/{id}/settings`.
- `backend/app/service.py`: `authorize(..., limits=True)`; `limits=False` melewati batas per job dan harian, konfirmasi tetap wajib (plan 18 Revisi 2).
- `backend/tests/test_project_settings.py` (baru, 7 tes); 8 berkas tes lama dinaikkan ke `user_version == 14`.

**Perilaku**
- Rasio terkunci (409) bila proyek punya gambar beat atau klip `storyboard`; rasio yang sama dikirim ulang tidak dianggap perubahan.
- Mengubah rasio menyelaraskan semua `films.aspect_ratio` di workspace; bila ada episode berbeda rasio yang sudah punya keyframe/video, butuh `confirm_sync` (409 memuat jumlahnya). Aset lama tidak diubah.
- Model video divalidasi ke katalog OpenRouter; resolusi divalidasi ke `supported_resolutions` model bila katalog menyebutnya.

**Temuan grill yang sudah ditangani**: no. 1 (rasio satu sumber), no. 2 dan 3 (batas v2 dilepas lewat `limits=False`).

**Belum**: UI `ProjectSettings` (frontend); `limits=False` belum dipanggil siapa pun (dipakai fase C/D); perkiraan biaya per 10 dtk di pengaturan proyek menunggu kalibrasi spike.

**Hasil tes**: `make test` -> 337 passed (330 lama + 7 baru). Setelah fase B dan C (non-AI): **353 passed** (+16 di `tests/test_voices_beats.py`; tes sweep workspace diperluas dengan route `voice_id`; versi skema sekarang 15).

## Fase B - Suara karakter (backend selesai)
**File**: `backend/app/voices.py` (baru), `media.prepare_voice` (mono 48 kHz AAC `.m4a`, dipotong 15 dtk), tabel `voice_versions`, kolom `characters.voice_id` (migrasi **v15**), endpoint di `main.py`:
`GET/POST /api/characters/{id}/voices`, `POST /api/voices/{id}/activate`, `DELETE /api/voices/{id}`, `GET /api/voices/{id}/file`.
**Perilaku**
- Versi baru langsung aktif; versi lama bisa diaktifkan lagi; menghapus yang aktif pindah ke versi terbaru yang tersisa (atau kosong).
- Unggahan butuh `consent` (centang izin suara); minimal 2 dtk, maksimal 15 dtk (lebih panjang dipotong); non-audio -> 415. Tanpa unggahan, deskripsi suara saja diterima (`source: text`).
- Dibersihkan saat karakter dihapus dan saat workspace dihapus (file ikut dihapus); salin workspace menyalin versi aktif saja.
**Deviasi dari plan**: sampel disimpan langsung di `voice_versions.path`, bukan lewat tabel `refs` (refs mewajibkan lebar/tinggi video); `characters.voice_id` menggantikan PK tunggal `character_voices`. TTS belum dikerjakan (menunggu spike katalog).
**Belum**: UI suara (frontend); pemakaian suara di request video (fase D).

## Fase C - Beat adegan (backend bagian non-AI selesai)
**File**: `backend/app/beats.py` (baru: `clean` murni + kelas `Beats`), tabel `scene_beats` dan `beat_versions`, endpoint `GET/PUT /api/scenes/{id}/beats`, `GET /api/scenes/{id}/beats/versions`, `POST /api/scenes/{id}/beats/restore`.
**Perilaku**
- Aturan: beat pertama mulai di 0, bersambung tanpa celah/tumpang tindih, panjang minimal 1 dtk, rentang dibulatkan 0,1 dtk; pemeran dan penutur dialog harus bagian dari adegan; aksi 300, kamera 120, dialog 300 karakter. Total beat berbeda dari `planned_seconds` -> peringatan, bukan galat. Dialog > 3 kata/dtk -> peringatan. Tidak ada batas jumlah beat (penjaga teknis 200).
- Setiap penggantian memotret susunan lama ke `beat_versions` dalam satu transaksi (maks 50 per adegan); pemulihan versi juga dipotret (bisa dibatalkan) dan membuang pemeran yang sudah tidak ada dengan peringatan.
- `image_id` beat hanya diwarisi dari beat lama dengan id yang sama; id dan gambar buatan klien diabaikan (tidak bisa membajak beat adegan/workspace lain).
- Beat yang menyebut pemeran yang sudah dilepas dari adegan ditandai `broken` (tidak dihapus); menyimpan ulang beat rusak ditolak.
- Dihapus bersama adegan, episode, dan workspace; episode yang sedang dirender menolak edit (409).
**Bug yang ditemukan tes**: dua deadlock (kunci DB tidak reentrant) saat memanggil `db.one` di dalam `db.transaction()` (salin suara, cek gambar beat); diperbaiki dengan mengambil data sebelum transaksi dibuka.
**Belum (fase C sisanya)**: pemecahan beat dengan AI (`scene_beats` estimasi), gambar beat per model pilihan + take, UI `BeatLane`/`BeatCard`, `images.beat_id` belum terisi siapa pun, revisi gambar/naskah/beat dengan AI, versi naskah, tanda basi.

## UI Storyboard v2 (frontend, dibangun; diuji manual oleh user)
**Akses**: halaman Storyboard, buka episode; di kepala episode ada pemilih **Storyboard v2 | Alur lama** (bawaan v2, pilihan diingat di browser). Alur lama utuh (termasuk Mode lanjutan). Backend harus di-restart (`make dev`) untuk endpoint dan migrasi v15.

**File baru** (`frontend/src/storyboard/v2/`): `V2Flow.tsx` (stepper 6 langkah + langkah 6 berupa daftar kesiapan), `ProjectSettings.tsx`, `StepVoices.tsx`, `BeatEditor.tsx`, `beatMath.ts` (logika murni jalur waktu). Berubah: `pages/Storyboard.tsx` (pemilih alur, langkah v2 tersimpan per episode di `sb2-step:<id>`, rasio episode jadi lencana baca-saja di v2), `api.ts` (tipe + fungsi), `styles.css` (kelas `v2-*`).

**Langkah**: 1 Proyek & pemeran (pengaturan proyek di atas, `StepCast` lama di bawah) · 2 Suara (opsional) · 3 Naskah (`StepScript` lama) · 4 Adegan (`StepTimeline` lama) · 5 Beat · 6 Gambar & video (belum aktif; berisi daftar kesiapan dan penjelasan jujur bahwa generate menunggu uji Seedance).

**Keputusan UX**
- Beat disunting sebagai daftar durasi, bukan kolom awal/akhir: susunan selalu bersambung, tidak ada galat celah/tumpang tindih. Jalur waktu: lebar blok sebanding durasi, batas bisa diseret (snap 0,5 dtk) atau digeser dengan panah keyboard saat difokus.
- Aksi: bagi dua, gabung ke berikutnya, tambah di akhir, bagi rata 2 sampai 8, +/- 0,5 dtk, samakan beat ke durasi adegan atau durasi adegan ke total beat. Hapus beat memberikan waktunya ke tetangga.
- Tombol Simpan menghitung adegan yang belum tersimpan; Ctrl/Cmd+S menyimpan semua; pindah langkah atau halaman menyimpan otomatis yang belum tersimpan (toast). Versi sebelumnya bisa dipulihkan dari tombol Versi.
- Suara: rekam langsung (mikrofon, maks 15 dtk), unggah, atau deskripsi saja; centang izin wajib bila ada sampel; versi bisa dipakai ulang/dihapus.
- Pengaturan proyek tersimpan otomatis; rasio berupa kotak berbentuk rasio dan terkunci dengan penjelasan bila sudah ada aset v2; mengubah rasio yang menyentuh episode ber-aset meminta konfirmasi.
- Bagian yang belum ada tidak dipalsukan: bingkai gambar beat menjelaskan bahwa gambar menyusul.

**Diverifikasi agent (tanpa browser)**: `npm run build` hijau (tsc + vite); logika `beatMath` dicek dengan skrip node (equalSplit, splitAt, mergeNext, resizeWithin, moveBoundary, scaleTo, payload bersambung) semuanya lulus.

**Diuji manual oleh user** (alur yang perlu dicoba):
1. Buka Storyboard, pastikan pemilih "Storyboard v2 / Alur lama" muncul dan Alur lama tetap bekerja seperti biasa.
2. Langkah 1: ubah model/resolusi/rasio/gaya (tersimpan setelah refresh); ubah rasio di workspace yang episodenya beda rasio (konfirmasi muncul bila ada keyframe/video).
3. Langkah 2: tambah suara dengan deskripsi saja; unggah audio tanpa centang izin (tombol harus mati); rekam dari mikrofon; ganti suara lalu "Pakai" versi lama; hapus versi.
4. Langkah 4 lalu 5: pilih adegan, "Bagi rata 3", seret batas antar beat, geser dengan panah keyboard, bagi dua/gabung, pilih tokoh dan tambah dialog, ubah durasi adegan lalu "Samakan beat", Simpan, ubah lagi, buka Versi dan Pulihkan.
5. Ubah beat lalu pindah ke langkah lain: harus muncul "Beat tersimpan otomatis".
6. Langkah 6: daftar kesiapan menunjuk ke langkah yang perlu dilengkapi.
7. Layar sempit (di bawah 860 px): rel adegan menjadi baris horizontal, detail beat satu kolom.

**Keterbatasan yang diketahui**: durasi adegan di server bilangan bulat; bila total beat pecahan (mis. 9,5) tombol "Samakan adegan" membulatkan sehingga selisih kecil bisa tersisa; gunakan "Samakan beat". Duplikat adegan belum menyalin beat.

## Revisi 3 - Hapus banyak adegan
**File**: `backend/app/scenes.py` (`delete_many`), `backend/app/main.py` (`POST /api/films/{film_id}/scenes/bulk-delete`, `SceneIdsIn`), `frontend/src/storyboard/Views.tsx` (`Board`: mode pilih, `SceneCard`: kotak centang), `StepTimeline.tsx` dan `V2Flow.tsx` (prop `onBulkDelete`), `pages/Storyboard.tsx` (`bulkRemove`), `api.bulkDeleteScenes`, kelas `board-tools`/`scene-check` di `styles.css`.
**Perilaku**: atomik dalam satu transaksi; id duplikat diabaikan; id asing atau episode workspace lain -> 404 tanpa efek; daftar kosong -> 422; episode dirender -> 409. Hasil generate (gambar/klip) terlepas dari adegan tetapi tetap di library; pemeran, beat, dan versi beat ikut dihapus; nomor diurut ulang sekali.
**Tes**: 2 tes baru di `tests/test_scenes.py`; `make test` -> **355 passed**. `npm run build` hijau.
**Diuji manual oleh user**: di langkah Adegan klik "Pilih beberapa"; centang beberapa kartu, Shift+klik rentang, "Pilih semua", "Kosongkan"; "Hapus N adegan" harus meminta konfirmasi berisi nomor adegan; setelah hapus nomor adegan berurutan lagi; Esc keluar dari mode pilih; seret-urut dan tombol hapus per kartu tersembunyi saat mode pilih; coba juga di alur lama (Timeline) dan di Mode lanjutan (Papan).

## Model video dikunci ke Seedance 2.0
`workspaces.V2_VIDEO_MODELS` = seedance-2.0, -fast, -mini; `PUT /api/workspaces/{id}/settings` menolak model lain (422, termasuk 2.5 dan model non-Seedance); `GET` mengembalikan `allowed_video_models`; `ProjectSettings.tsx` hanya menampilkan ketiganya. Tes: `test_video_model_is_locked_to_seedance_2_family` dan `test_validation` diperbarui (katalog fake disuntik model 2.0 lewat cache). `make test` -> 356 passed; `npm run build` hijau. Diuji manual oleh user: di langkah 1 daftar "Model video (Seedance 2.0)" hanya berisi tiga model.

## Fase D - Generate video Seedance (dibangun tanpa spike, atas permintaan user)
**File**: `backend/app/seedance_request.py` (perakit murni), `backend/app/storyboard_video.py` (plan/preview/estimate/generate), `media.shrink_data_url` (gambar referensi ≤ 1536 px JPEG), `service._release_published` (kini juga `published_keys`), `main.py` (`GET /api/scenes/{id}/storyboard-video/preview`, `POST /api/scenes/{id}/storyboard-video`, estimasi kind `storyboard_video`), frontend `storyboard/v2/StepVideo.tsx` + `V2Flow.tsx` (langkah 6), `api.ts`, `styles.css`.
**Perilaku**
- Satu adegan = satu request Seedance. Parameter dari pengaturan proyek (model Seedance 2.0 saja, resolusi, rasio, suara); durasi = akhir beat terakhir (atau durasi rencana) dibulatkan ke atas, minimal 4, maksimal 15 dtk (lebih dari itu ditolak dengan saran membagi adegan).
- Referensi bernomor: gambar beat (urut waktu) → gambar karakter → gambar latar (maks 9; beat dijarangkan merata bila lebih, lalu karakter didahulukan atas latar) → audio suara karakter yang berdialog (maks 3, butuh hosting publik) → video previs (opsional). Prompt: gaya proyek, legenda `@Image N: ...`, deskripsi suara, daftar shot bertimecode dengan dialog, dan kalimat konsistensi.
- Pratinjau di UI menunjukkan persis referensi dan prompt; prompt bisa disunting (disimpan sebagai prompt klip). Biaya: estimasi + dialog konfirmasi wajib; batas per job dan harian tidak memblokir jalur ini (`authorize(limits=False)`), estimasi basi tetap ditolak 409.
- Klip disimpan dengan `kind = storyboard`, jadi take video adegan (adegan yang sudah punya video bagus tidak ditimpa); tombol "Buat semua video yang belum ada" memakai batch yang ada (satu konfirmasi total).
- Kegagalan: penyedia menolak audio → diulang tanpa audio; penolakan lain → tidak ada klip tercatat dan file publik (suara/previs) dilepas.
**Belum terbukti (jujur)**: format `@Image N`/`@Audio N`, tipe `audio_url`, batas 9 gambar, dan kepatuhan prompt bertimecode belum pernah diuji ke OpenRouter nyata (kredit habis; spike dilewati atas permintaan user). Bila hasil/penolakan nyata menunjukkan format lain, ubah `seedance_request.py` (satu tempat). Biaya estimasi memakai SKU harga yang ada; tidak dikalibrasi.
**Tes**: `tests/test_storyboard_video.py` (13 tes, OpenRouter palsu): penomoran dan legenda, batas gambar/audio, fallback tanpa hosting publik, pratinjau/estimasi/payload, batas biaya tidak memblokir tetapi konfirmasi basi ditolak, adegan > 15 dtk, prompt sunting, isolasi workspace, audio sebagai referensi + pelepasan kunci saat job selesai, ulang tanpa audio, penolakan penyedia. `make test` -> **369 passed**; `npm run build` hijau.
**Diuji manual oleh user**: (1) langkah 6 → "Siapkan video…" pada satu adegan: lihat daftar referensi bernomor, prompt, estimasi; sunting prompt lalu "Kembalikan rakitan otomatis"; (2) "Buat video" → dialog konfirmasi biaya → video muncul di antrian dan di baris adegan; (3) adegan > 15 dtk menampilkan peringatan dan tombol batch melewatinya; (4) dengan tunnel/S3 aktif dan sampel suara: kartu referensi `@Audio` muncul; tanpa hosting: ada keterangan; (5) hasil nyata: periksa apakah gambar acuan dan urutan shot diikuti; laporkan bila Seedance menolak format.

## Fase E
Belum dimulai (render episode dari section v2 memakai render yang ada; gambar per beat dengan AI dan segmen otomatis belum dibangun).

## Diuji manual oleh user
Belum ada UI v2; belum ada yang perlu diuji.

## Riwayat
- 2026-10-26: dokumen dibuat; fase 0 tertahan 402, fase A backend selesai.

---

## Revisi 4 — Format prompt shot Seedance 2.0

**Dibangun**
- `db.py` migrasi **v16**: `scene_beats.size`, `scene_beats.lens`, `workspaces.genre` (nullable).
- `beats.py`: `size` ∈ WS/MS/MCU/CU/ECU, `lens` ∈ 24/35/50/85 (menerima "85mm"); peringatan shot > 3 dtk dan tiga shot berturut-turut dengan ukuran+lensa sama; ikut snapshot versi. `Beats.generate_ai` / `ai_estimate`: model teks pilihan membuat shot (JSON), divalidasi `clean` + total harus = durasi adegan + tiap shot ≤ 3 dtk; salah → satu kali ulang dengan pesan galat, lalu 502 (kedua panggilan tercatat di `text_jobs`). Hasil berupa draf, tidak disimpan.
- `beatsai.py` (baru, murni): prompt sistem berisi aturan format, prompt user dari konteks adegan, konversi jawaban → beat.
- `seedance_request.build()` ditulis ulang: `FORMAT / SUBJECT / WARDROBE / ENVIRONMENT / MOOD / REFERENCES` lalu `SHOT N — m:ss to m:ss, UKURAN, LENSA, GERAK. Aksi.`; notasi `@image_N`, `@audio_N`, `@video_1`; bagian kosong dihilangkan.
- Endpoint `POST /api/scenes/{id}/beats/ai`, estimate kind `scene_beats`, `genre` di settings proyek (maks 80).
- Frontend: tombol "Buat shot dengan AI" (pemilih model teks + estimasi + konfirmasi biaya), pilihan ukuran & lensa per beat, peringatan >3 dtk, kolom Genre di pengaturan proyek.
- `docs/reference/seedance-shot-format.md`: salinan format dari user.

**Menyimpang dari plan (lebih sedikit kolom)**
- WARDROBE diambil dari **tampilan (outfit) karakter di adegan** yang sudah ada, bukan kolom `characters.wardrobe` baru.
- MOOD diambil dari `scenes.extra_prompt`, jika kosong dari gaya proyek; tanpa `scenes.mood`.
- Ditunda seperti di plan: sub-lokasi (A)(B)(C), auto-segmen >15 dtk, gambar beat otomatis.

**Temuan grill → penanganan**: R4-1 (belum terbukti) didokumentasikan di docstring dan di sini; R4-2 validasi keras + satu ulang; R4-3 kolom nullable + tes migrasi v16; R4-4 WARDROBE kosong dihilangkan; R4-5 tes `@Image N` ditulis ulang; R4-6 estimasi + konfirmasi; R4-7 tanpa kunci DB bersarang.

**Hasil tes (dijalankan)**: `make test` → lihat baris terakhir laporan; `tests/test_beats_ai.py` (7 tes baru: konfirmasi wajib, draf tak tersimpan, ulang sekali, selalu invalid → 502 + biaya tercatat, total salah/pemeran asing, adegan tanpa bahan, ukuran/lensa, genre) dan 1 tes format lengkap di `test_storyboard_video.py`. `npm run build` hijau.

**Belum terbukti**: `@image_N`, timestamp `m:ss`, `audio_url` diterima Seedance via OpenRouter (tanpa uji berbayar). Kualitas shot dari model teks nyata juga belum diukur.

**Diuji manual oleh user**
1. Pengaturan proyek → isi Genre → muncul di prompt langkah 6 (`FORMAT: … / genre`).
2. Langkah Beat → adegan berpemeran → "Buat shot dengan AI" → dialog biaya → draf muncul (tombol Simpan aktif) → ukuran/lensa terisi.
3. Ubah ukuran/lensa per beat, simpan, muat ulang: tetap.
4. Beat > 3 dtk menampilkan peringatan; "Bagi dua" menyelesaikannya.
5. Langkah 6 "Siapkan video": prompt berbentuk FORMAT/SUBJECT/…/SHOT N.

---

## Revisi 5 — Naskah berformat shot Seedance 2.0

**Dibangun**
- `backend/app/script_format.py` (baru, murni): `is_formatted`, `parse`. Blok `ADEGAN n — #[Latar]` + `FORMAT/SUBJECT/WARDROBE/ENVIRONMENT/MOOD` + baris `SHOT n — m:ss to m:ss, UKURAN, LENSA, GERAK. Aksi.` → draf adegan (latar, pemeran dari mention, MOOD → `extra_prompt`, durasi → `planned_seconds`, dialog `@[Nama] says: "…"`) + `beats` yang divalidasi `beats.clean`. Galat per adegan (nomor adegan disebut): label wajib hilang, timestamp bercelah, >15 dtk, >3 pemeran. Nama tak dikenal = peringatan, tidak ada entitas baru.
- `script.SCRIPT_SYSTEM` ditulis ulang (aturan format lengkap); `clean_split` meneruskan `beats`.
- `journey.py`: `script_draft` memvalidasi keluaran AI dengan pengurai; salah → ulang SEKALI dengan daftar galat, lalu 502 (kedua panggilan tercatat). `format_info` (masuk `state.format`), `split_format` (gratis, `POST /api/films/{id}/split/format`), `apply_split` memvalidasi SEMUA beat sebelum membuat adegan pertama lalu menyimpan beat lewat `Beats.replace`.
- Frontend: lencana "Format shot Seedance terbaca: N adegan, M shot" di langkah Naskah; tombol "Buat adegan dan beat dari format (gratis)" di langkah Adegan; draf menampilkan ukuran/lensa tiap shot.

**Temuan grill → penanganan**: R5-1 uji ulang+502; R5-2 deteksi butuh FORMAT: dan SHOT; R5-3 nama dicocokkan casefold; R5-4 galat bernomor, tanpa pemotongan diam-diam; R5-5 dialog `@[Nama] says: "…"`; R5-6 tes "satu beat buruk → nol adegan"; R5-7 draf klien divalidasi ulang; R5-8 tanpa kunci DB bersarang.

**Hasil tes (dijalankan)**: `make test` → 393 lulus (baru: `tests/test_script_format.py`, 14 tes; `test_journey` diperbarui memakai naskah berformat). `npm run build` hijau.

**Belum terbukti**: kepatuhan model teks nyata pada format (hanya diuji dengan jawaban palsu); format ke Seedance (lihat Revisi 4).

**Diuji manual oleh user**
1. Langkah Naskah → "Tulis dengan AI" → konfirmasi biaya → draf berbentuk blok `ADEGAN … FORMAT … SHOT …`.
2. Simpan; lencana format muncul. Langkah Adegan → "Buat adegan dan beat dari format (gratis)" → draf menunjukkan jumlah shot → Terapkan.
3. Langkah Beat: adegan tadi sudah berisi beat dengan ukuran, lensa, gerak, dialog.
4. Rusak satu timestamp di naskah: lencana menampilkan galat dengan nomor adegan, tombol gratis nonaktif.

---

## Revisi 6 — Ubah adegan dengan AI

**Dibangun**
- `beatsai.py`: `REVISE_SYSTEM` (aturan format + aturan revisi: ubah seperlunya, `keep`, `total_seconds`, mood/waktu), `revise_prompt` (instruksi di blok berlabel DATA), `revision_to_beats`.
- `beats.py`: `revise_estimate` (instruksi dipadatkan ke batas 500 karakter sehingga estimasi konstan dan sama dengan saat generate; tanpa 409 palsu), `revise_ai`: draf yang divalidasi `clean`, total = `total_seconds` (1–15; bila tak disebut = durasi sekarang), shot ≤ 3 dtk; `keep` hanya dipercaya bila bulat 1..N sekali pakai → mewarisi id + gambar beat lama; tiap shot diberi `from` dan `changed`. Salah → ulang SEKALI, lalu 502; kedua panggilan tercatat (`text_jobs.kind = scene_revise`).
- `main.py`: `POST /api/scenes/{id}/revise`, estimate kind `scene_revise` (422 bila adegan belum punya beat).
- Frontend (langkah Beat): tombol "Ubah dengan AI" → kotak instruksi + chip contoh + pemilih model + estimasi/konfirmasi → pratinjau sebelum/sesudah (shot berubah disorot, "baru"/"diubah", aksi lama dicoret, total durasi, perubahan mood/waktu) → "Terapkan ke editor" / "Buang". Penerapan mengisi editor sebagai draf (titik "belum disimpan"); saat Simpan: beat disimpan dengan catatan versi `AI: <instruksi>` lalu mood/waktu/durasi diperbarui ke adegan. Versi lama bisa dikembalikan dari Versi.

**Temuan grill → penanganan**: R6-1 sorotan `changed` + draf; R6-2 `total_seconds` + validasi; R6-3 `keep` divalidasi (tes keep ganda/99/boolean); R6-4 instruksi di blok DATA, keluaran tetap divalidasi; R6-5 konfirmasi bila editor dirty + versi otomatis; R6-6 mood/waktu hanya saat Simpan; R6-7 estimasi konstan, tes dua panjang instruksi tanpa 409; R6-8 tanpa kunci DB bersarang.

**Hasil tes (dijalankan)**: `make test` → 399 lulus (6 tes revisi baru di `tests/test_beats_ai.py`: konfirmasi/instruksi/belum ada beat, id+gambar dipertahankan dan flag `changed`, ubah durasi + `keep` tak sah, ulang sekali lalu 502, estimasi tak bergantung panjang instruksi, isolasi workspace). `npm run build` hijau.

**Belum terbukti**: kepatuhan model teks nyata (apakah benar-benar mengubah seperlunya); hanya diuji dengan jawaban palsu. Naskah (teks blok adegan) tidak ikut berubah.

**Diuji manual oleh user**
1. Langkah Beat, adegan yang sudah punya beat → "Ubah dengan AI" → tulis instruksi → dialog biaya → pratinjau menyorot shot yang berubah.
2. "Terapkan ke editor" → titik belum tersimpan muncul → Simpan → muat ulang: beat baru tersimpan; mood/waktu/durasi adegan ikut berubah.
3. Versi → pulihkan versi dengan catatan `AI: …`: beat lama kembali.
4. Buang di pratinjau: tidak ada yang berubah. Instruksi kosong: tombol nonaktif.

---

## Revisi 7 — Ubah naskah dengan AI (langkah Naskah)

**Dibangun**
- `script.py`: `REVISE_SCRIPT_SYSTEM` (aturan format + "salin utuh blok yang tidak disentuh", renumber ADEGAN, boleh mengubah prosa jadi format), `revise_user` (naskah utuh + instruksi di blok DATA), `revise_tokens` (batas keluaran 4.000–16.000 sebanding panjang naskah), `INSTRUCTION_MAX = 500`.
- `script_format.py`: `compare(old, new)` memecah per blok dan mencocokkan berdasarkan ISI (judul ADEGAN n dan spasi diabaikan) → `changed`, `previous`, `removed`.
- `journey.py`: `script_revise_estimate` (instruksi dipadatkan ke 500 karakter: estimasi konstan), `script_revise`; `_check_script` digeneralisasi (parameter `kind` dan `max_tokens`) sehingga validasi format + ulang sekali + 502 dipakai bersama penulisan naskah. `POST /api/films/{id}/script/revise`, estimate kind `script_revise`.
- Frontend (StepScript): kartu "Ubah naskah dengan AI" (instruksi, chip contoh, estimasi, konfirmasi biaya) → perbandingan per adegan (berubah disorot, "Versi sebelumnya" dilipat) → "Terapkan ke naskah" / "Buang"; setelah diterapkan ada tombol "Kembalikan naskah sebelum revisi".

**Menyimpang dari plan/grill**
- R7-6: server tidak mengirim `base_hash`; UI menyimpan teks dasar saat revisi diminta dan meminta konfirmasi bila editor sudah berbeda saat diterapkan.
- Editor naskah menyimpan otomatis (perilaku lama), jadi "terapkan" langsung tersimpan; pengaman: tombol kembalikan (sesi ini saja, tanpa riwayat versi naskah).
- `_editable` tidak dicek pada draf (sama dengan "Tulis dengan AI").

**Temuan grill → penanganan**: R7-1 `changed` per blok; R7-2 batas keluaran proporsional + `finish_reason=length` ditolak `textai`; R7-3 estimasi batas atas yang sama dengan panggilan, kedua percobaan tercatat; R7-4 pencocokan berdasar isi (tes sisip di depan); R7-5 instruksi di blok DATA; R7-7 nama tak dikenal → peringatan dari pengurai; R7-8 `_check_script` digeneralisasi.

**Hasil tes (dijalankan)**: `make test` → 404 lulus (baru di `tests/test_script_format.py`: perbandingan, naskah kosong/instruksi/konfirmasi, draf tak tersimpan + `changed` per adegan + naskah dikirim utuh, prosa→format dengan ulang sekali dan 502 + biaya tercatat, estimasi tak bergantung panjang instruksi + batas token). `npm run build` hijau.

**Belum terbukti**: model nyata benar-benar menyalin blok yang tidak disentuh (hanya jawaban palsu); biaya naskah panjang nyata.

**Diuji manual oleh user**
1. Langkah Naskah dengan naskah berformat → "Ubah naskah dengan AI" → instruksi → dialog biaya → perbandingan per adegan menyorot yang berubah.
2. "Terapkan ke naskah" → naskah di editor berganti dan tersimpan otomatis; "Kembalikan naskah sebelum revisi" memulihkan.
3. Ketik di editor setelah meminta revisi lalu terapkan: muncul konfirmasi.
4. Naskah prosa lama → revisi → hasil berformat (lencana format muncul) → langkah Adegan → "Buat adegan dan beat dari format (gratis)".

---

## Revisi 8 — Prompt adegan sebagai sumber tunggal

**Dibangun**
- `db.py` migrasi **v17**: `scenes.prompt` (NULL = dirender dari data).
- `scene_prompt.py` (baru): `render` (murni; data adegan → blok berformat Seedance dengan mention `@[Karakter]`/`#[Latar]`, kebalikan `script_format.parse`; adegan lama tanpa beat → satu shot sepanjang durasi) dan `ScenePrompt` (`get`, `check`, `put`). `put` memvalidasi SEMUA hal dulu (nama dikenal & tidak ganda, tepat satu blok, parse, `beats.clean`) lalu menurunkan `location_id`, `scene_cast` (outfit/aksi karakter yang sama dipertahankan; karakter proyek yang belum di episode otomatis masuk), `scene_beats` (hanya bila berubah, jadi tanpa versi sampah; catatan "dari prompt adegan"), MOOD → `extra_prompt`, FORMAT → `planned_seconds`, dan menulis `prompt` TERAKHIR.
- Sinkron: jalur lain yang mengubah data (`Scenes.update` untuk latar/pemeran/mood/durasi, `Beats._write`, hapus karakter, hapus latar) mengosongkan `prompt`; ganti nama latar menulis ulang mention di prompt tersimpan.
- `seedance_request.resolve` (murni): `@[Nama]` → `@image_N — Nama` (sekali, di baris SUBJECT), `#[Latar]` → `Latar (see @image_N)` (baris ENVIRONMENT), selain itu nama biasa; nomor dari daftar referensi AKTUAL (`build()["map"]`). `build()` kini juga mengembalikan `references`, `tail`, `map`.
- `storyboard_video.plan`: prompt akhir = prompt adegan yang diselesaikan + baris `Visual style:` (gaya proyek, sebelum SHOT) + REFERENCES (suara/previs) + kalimat konsistensi. Pratinjau mengembalikan `scene_prompt` (sumber) dan `prompt` (yang persis dikirim).
- Endpoint: `GET/PUT /api/scenes/{id}/prompt`, `POST /api/scenes/{id}/prompt/check` (validasi tanpa menyimpan).
- Frontend: `v2/ScenePrompt.tsx` (editor + tombol sisip mention + validasi hidup + aset terhubung bergambar + Simpan/Ctrl+S). Inspector `promptMode` (v2): bagian Latar, Pemeran, Dialog/catatan, Buat keyframe, Buat video diganti editor prompt. Panel video langkah 6: satu prompt (editor yang sama), centang previs dan kotak prompt kedua dihapus, daftar aset berlabel `@image_N`, "Teks yang persis dikirim" (read-only), tombol Buat video terkunci selama prompt belum tersimpan.

**Menyimpang dari plan/grill**
- R8-10: mention aset TANPA gambar = peringatan (tetap bisa dikirim sebagai teks), bukan 422; nama tak dikenal / ganda tetap 422 saat simpan.
- R8-8: penyimpanan berurutan di bawah `Studio._lock` setelah validasi penuh, bukan satu transaksi.
- Gaya visual proyek tidak lagi menjadi MOOD cadangan; ditambahkan sebagai baris `Visual style:` saat kirim.
- `time_of_day`, `camera`, `dialogue` adegan tidak ditimpa dan tidak tampil di inspector v2 (isi relevan ada di prompt). Parameter `prompt` pada POST generate tetap ada di API tetapi tidak dipakai UI.
- Sampel suara tetap (diturunkan dari penutur); previs dan gambar beat tidak lagi bisa dipilih dari UI (backend tetap mendukung).

**Hasil tes (dijalankan)**: `make test` → lihat baris terakhir (417 sebelum doc ini). Baru: `tests/test_scene_prompt.py` (13 tes: render format, simpan stabil tanpa menumpuk versi, penurunan latar/pemeran/beat/mood/durasi + aksi lama dipertahankan, prompt tidak valid tidak mengubah apa pun, nama ganda, `check` tanpa simpan, semua jalur lain mengosongkan prompt, ganti nama latar, video memakai prompt adegan dengan nomor sesuai referensi aktual dan pemeran yang dihapus tidak meninggalkan `@image_N`, pratinjau, isolasi workspace, `resolve`). `npm run build` hijau.

**Belum terbukti**: format `@image_N`/`(see @image_N)` ke Seedance via OpenRouter (tanpa uji berbayar), seperti Revisi 4.

**Diuji manual oleh user**
1. Langkah Adegan: inspector kanan menampilkan satu kotak "Prompt adegan" (tanpa dropdown Latar/Pemeran). Ubah `SUBJECT`/`ENVIRONMENT`, Simpan: kartu aset dan baris adegan di tengah mengikuti.
2. Tulis `@[Nama]` yang tidak ada: pesan merah dan Simpan terkunci; prompt/aset lama tidak berubah.
3. Langkah Beat: ubah beat lalu kembali ke inspector: prompt memuat beat baru.
4. Langkah 6: panel video hanya punya satu kotak prompt; hapus karakter dari prompt, simpan, lalu lihat "Aset yang dikirim" dan "Teks yang persis dikirim" tanpa karakter itu.

---

## Revisi 9 — Frame awal dari adegan sebelumnya

**Dibangun**
- `db.py` migrasi **v18**: `scenes.start_from_prev` (default 0). `Scenes.update`/`SceneUpdateIn` menerima `start_from_prev` (boolean ketat; adegan pertama → 422); `public` mengembalikannya.
- `storyboard_video.py`:
  - `start_info` — adegan sebelumnya (urutan SAAT ini) harus punya klip `completed` dengan berkas ada.
  - `plan(strict)` — bila dicentang & tersedia: mode frame (refs hanya `frame`, mention jadi nama biasa, suara lewat teks, baris "Start exactly from the provided first frame…" ditambahkan sebelum SHOT bersama `Visual style:`); tidak tersedia → 422 (generate/estimasi) atau peringatan (pratinjau, supaya kotak centang bisa dilepas); previs + frame → 422.
  - `estimate` — mode `i2v` 1 gambar.
  - `generate` — `_start_frame` mengekstrak frame akhir (ffmpeg, di luar kunci Studio), menyimpannya sebagai gambar library `kind=frame`, mengirim `frame_images=[first_frame]` dan TIDAK mengirim `input_references`; klip mencatat `params.start_from` dan `source_image_id` = frame; penolakan penyedia/biaya menghapus frame (tanpa yatim).
  - Pratinjau: `start_from_prev`, `start_frame`, `can_start_from_prev`.
- Frontend (langkah 6): kotak centang "Mulai dari frame akhir adegan sebelumnya" (adegan ke-2 dst.; nonaktif dengan alasan), kartu "Frame awal" dengan pratinjau frame terakhir video itu dan penjelasan tradeoff, lencana "berantai dari frame akhir adegan N" di baris adegan, batch hanya menjalankan adegan berantai yang induknya selesai (sisanya "menunggu adegan N").

**Temuan grill → penanganan**: R9-1 payload tanpa `input_references` (tes); R9-2 strict vs pratinjau non-strict; R9-3 urutan dihitung saat generate (tes hapus adegan pertama); R9-6 tes tanpa frame yatim; R9-8 batch; R9-9 previs 422 (tes); R9-10 estimasi + konfirmasi (409 tanpa konfirmasi); R9-11 ekstraksi di luar kunci.

**Tidak ditangani (disengaja)**: R9-4 frame akhir hitam/fade tidak dideteksi; R9-7 peringatan "adegan sebelumnya berubah" otomatis tidak ada (hanya tercatat di `params.start_from`).

**Hasil tes (dijalankan)**: `make test` → 423 lulus (baru: `tests/test_start_frame.py`, 6 tes: validasi + adegan pertama, preview/estimasi/generate menolak tanpa video selesai, `frame_images` first_frame tanpa `input_references` + `params.start_from` + `source_image_id` frame, penolakan penyedia tanpa frame yatim, previs 422 dan melepas centang memulihkan referensi, urutan adegan saat ini). `npm run build` hijau.

**Belum terbukti**: perilaku nyata Seedance via OpenRouter dengan `frame_images` saja (tanpa uji berbayar); kualitas kesinambungan; apakah kombinasi frame + referensi diterima API (sengaja tidak dipakai).

**Diuji manual oleh user**
1. Langkah 6: adegan 1 tidak punya kotak centang; adegan 2 menampilkan kotak dengan alasan bila adegan 1 belum punya video selesai.
2. Selesaikan video adegan 1 → centang di adegan 2: muncul kartu "Frame awal" (frame terakhir video adegan 1); daftar aset hanya frame; "Teks yang persis dikirim" tanpa `@image_N` dan memuat baris "Start exactly…".
3. Buat video adegan 2: di library muncul gambar tipe Frame; lepas centang: aset karakter dan latar kembali.
4. "Buat semua video yang belum ada" dengan adegan berantai yang induknya belum selesai: muncul catatan "menunggu adegan N".

---

## Revisi 10 — Ubah adegan dengan AI di langkah Adegan

**Dibangun**
- `script.py`: `REVISE_SCENE_SYSTEM` (= `REVISE_SCRIPT_SYSTEM` + aturan tepat satu blok, nomor ADEGAN tetap, hanya karakter/latar yang diberikan, label lengkap, ≤ 15 dtk).
- `scene_prompt.py`: `ScenePrompt.revise_estimate` / `revise` (instruksi di blok DATA, konteks: prompt tersimpan atau render dari data, karakter + latar proyek, genre, gaya; estimasi dengan instruksi dipadatkan konstan), `changed_lines` (multiset baris, bukan posisi). Keluaran divalidasi `ScenePrompt.parse` (satu blok, nama dikenal dan tidak ganda, timestamp, ≤ 15 dtk, ≤ 3 pemeran); salah → ulang SEKALI dengan galat → 502; kedua panggilan tercatat (`text_jobs.kind = scene_prompt_revise`). Hasil berupa draf; tidak ada yang disimpan.
- `POST /api/scenes/{id}/prompt/revise`; estimate kind `scene_prompt_revise`.
- Frontend: tombol "Ubah dengan AI" di bawah editor prompt adegan (inspector langkah Adegan dan panel video langkah 6): instruksi + chip contoh + pemilih model + estimasi/konfirmasi; hasil menyorot baris yang berubah, "Prompt sebelumnya" bisa dibuka, "Terapkan ke editor" mengisi editor sebagai teks belum tersimpan (validasi hidup berjalan; Simpan prompt menurunkan latar, pemeran, beat, mood, durasi), "Buang" tidak mengubah apa pun. Tombol dikunci selama editor punya perubahan belum tersimpan.

**Temuan grill → penanganan**: R10-1 baris berubah ditandai + draf; R10-2/3 `parse` yang sama dengan Simpan (nama karangan ditolak, satu blok); R10-4 blok DATA; R10-5 UI mengunci saat kotor dan server memakai prompt tersimpan, estimasi konstan; R10-6 `parse` menolak >15 dtk; R10-7 estimasi batas atas + dua panggilan tercatat; R10-8 hanya masuk lewat "Terapkan" dan bisa "Batalkan perubahan".

**Hasil tes (dijalankan)**: `make test` → 429 lulus (6 tes baru di `tests/test_scene_prompt.py`: konfirmasi/instruksi, draf valid tak tersimpan + baris berubah + isi prompt sistem/user, ulang sekali dengan galat lalu 502 + biaya tercatat (nama karangan dan dua blok), estimasi tak bergantung panjang instruksi, isolasi workspace, `changed_lines`). `npm run build` hijau.

**Belum terbukti**: model teks nyata mengubah seperlunya dan lolos validasi (hanya jawaban palsu).

**Diuji manual oleh user**
1. Langkah Adegan → pilih adegan → di bawah editor prompt: "Ubah dengan AI" → instruksi → dialog biaya → baris yang berubah disorot.
2. "Terapkan ke editor" → muncul "belum disimpan" → Simpan prompt → kartu aset, baris adegan, dan langkah Beat mengikuti.
3. Ketik di editor tanpa menyimpan: tombol "Minta revisi AI" terkunci dengan penjelasan.
4. "Buang": tidak ada yang berubah. Instruksi kosong: tombol nonaktif.
