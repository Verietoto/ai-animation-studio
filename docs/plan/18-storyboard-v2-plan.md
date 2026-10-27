# 18 - Storyboard v2: proyek terkunci, suara karakter, gambar per detik, generate Seedance (Plan)

- Status: draft, menunggu persetujuan
- Tanggal: 2026-10-26

## Tujuan
Permintaan user (verbatim): "oke buat plan untuk section storyboard terbaru, 1. Masih bisa per episode 2. Bisa buat latar dan karakter disini 3. Projek harus ditetapkan quality video dan rasio jadi konsisten di semua episode 4. Bisa membuat audio untuk karakter 5. di tiap episode per timeline bisa digenerate beberapa gambar dengan model pilihan kita dengan memasukan karakter dan background juga jadi ada referensi per detiknya gimana 6. generate dengan seadance"

Diterjemahkan jadi enam kebutuhan:
1. Tetap per episode (struktur `films` → `scenes` dipertahankan).
2. Karakter dan latar bisa dibuat langsung dari section ini (tanpa pindah halaman).
3. Proyek punya pengaturan video tetap (kualitas/resolusi + rasio, juga model video) yang berlaku sama di semua episode.
4. Karakter punya suara (audio) yang dipakai saat generate.
5. Di tiap adegan pada timeline, user membagi waktu menjadi beberapa **ketukan (beat)** dengan rentang detik; tiap beat di-generate satu gambar (model gambar pilihan user) dengan referensi karakter + latar. Hasilnya: acuan visual per detik.
6. Video adegan di-generate dengan Seedance 2.x memakai semua acuan itu (gambar beat, karakter, latar, suara) dalam satu request.

## Keadaan sekarang (dicek 2026-10-26)
- Episode = `films` (judul, nomor, sinopsis, `aspect_ratio` **per episode**, naskah). Adegan = `scenes` (latar, waktu, kamera, dialog, `planned_seconds` 1–120, keyframe, klip, blockout/previs). Pemeran adegan di `scene_cast` (maks 3).
- Alur episode 5 langkah (plan 15): pemeran & latar → naskah dengan `@[Karakter]`/`#[Latar]` → timeline (manual/AI) → previs 3D opsional → produksi. Langkah 1 sudah bisa membuat karakter dari prompt (plan 16) dan latar.
- Karakter: `characters` + `character_images` (lembar tampilan) + `outfits`; `look` 3D (plan 17, sebagian).
- Workspace (plan 07) adalah unit "proyek" yang ada: semua aset terikat `workspace_id`. **Plan ini menganggap Proyek = workspace** (lihat pertanyaan terbuka 1).
- Video: `clips` lewat OpenRouter `/api/v1/videos`. `motion.py` sudah mengirim `input_references` bertipe `video_url`. Gambar via data URL diterima; video (dan kemungkinan audio) harus URL HTTPS publik → tunnel/S3 (plan 10).
- Biaya: estimasi → konfirmasi → `authorize()` (plan 04), batas per job $1 dan harian $5.
- Tidak ada fitur audio/suara sama sekali di luar `generate_audio` boolean.

## Fakta Seedance 2.x yang dipakai (riset 2026-10-26)
- Resmi ByteDance: sampai 9 gambar + 3 video + 3 audio + teks dalam satu generate; output multi-shot sampai 15 dtk dengan audio stereo (dialog, SFX, musik) dibuat bersamaan; referensi dirujuk di prompt sebagai `@Image 1`, dst.
- OpenRouter: durasi 4–15 dtk; resolusi 2.0 = 480p/720p/1080p/4K, Fast/Mini = 480p/720p; 7 rasio (1:1, 3:4, 9:16, 4:3, 16:9, 21:9, 9:21); `frame_images` (first/last), `input_references`, `generate_audio`, `seed`. Harga per token video dibedakan audio, resolusi, dan ada/tidaknya input video; token per detik tidak dipublikasikan.
- Temuan kita (plan 03): `frame_images` dan `input_references` tidak bisa digabung (frame menang); identitas karakter dari gambar referensi sangat terjaga di Seedance 2.0 mini; wajah manusia fotorealistis ditolak.
- **Belum terbukti** lewat OpenRouter: notasi `@Image N`/`@Audio N` dihormati, tipe/nama field untuk audio referensi, apakah 9 gambar diterima, kepatuhan prompt bertimecode, rumus biaya per detik. Semua ini diuji di spike Fase 0 sebelum kode inti ditulis.

## Ruang lingkup
**Termasuk**
- Section baru "Storyboard v2" di halaman Storyboard: alur episode yang sama (plan 15) dengan langkah yang disesuaikan: *Pemeran & latar → Suara → Naskah → Timeline & beat → Gambar beat → Video Seedance → Render episode*.
- Pengaturan proyek: model video (keluarga Seedance), resolusi, rasio; rasio terkunci begitu ada hasil generate (lihat desain).
- Suara karakter: deskripsi suara (teks) + sampel audio (unggah rekaman sendiri; generate lewat model TTS bila spike membuktikan tersedia).
- Beat per adegan: rentang detik, deskripsi aksi, kamera, pemeran yang tampil, dialog per karakter. Dibuat manual atau dipecah AI (model teks pilihan, plan 17).
- Gambar per beat: pilih model gambar, referensi = gambar karakter (pakaian terpilih) + gambar latar (+ gambar beat sebelumnya, opsional, untuk kontinuitas). Beberapa take per beat, satu dipilih.
- Generate video adegan dengan Seedance: perakit request murni (deterministik, teruji) yang menyusun referensi dan prompt bertimecode; estimasi biaya; konfirmasi; masuk antrian klip yang sudah ada.
- Aksi massal per episode dengan satu konfirmasi total: "gambar semua beat yang belum ada", "video semua adegan yang belum ada".

**Tidak termasuk**
- Kloning suara orang sungguhan / tokoh publik (ditolak; hanya suara milik user atau suara sintetis).
- Musik latar terpisah, mixing audio multi-track, edit waveform.
- Edit video dan extend gaya Seedance (fitur extend lama tetap ada di Library).
- Seedance 2.5 (30 dtk) dan model video non-Seedance di section ini; jalur lama di Mode lanjutan tetap memakai model apa pun.
- Menghapus alur plan 15: tetap ada; v2 adalah section baru di sebelahnya sampai user memutuskan menggantinya.

## Desain / pendekatan

### 1. Pengaturan proyek (kebutuhan 3)
- Kolom baru di `workspaces`: `video_model` (default `bytedance/seedance-2.0`), `video_resolution` (default `720p`), `aspect_ratio` (default `16:9`), `generate_audio` (default 1), `image_model` (model gambar default beat), `style` (teks gaya visual, opsional).
- Nilai yang diizinkan dibaca dari `GET /api/v1/videos/models` (bukan daftar keras), supaya pilihan resolusi menyesuaikan model (Fast/Mini maks 720p).
- `films.aspect_ratio` tetap ada (data lama), tetapi v2 selalu memakai rasio proyek. Migrasi: rasio proyek = rasio terbanyak di episode workspace itu; episode yang berbeda ditandai "rasio berbeda dari proyek" di daftar episode (tidak diubah diam-diam).
- **Penguncian**: rasio tidak bisa diubah bila proyek sudah punya gambar beat atau klip v2 (409 dengan pesan jumlah aset). Resolusi dan model boleh diubah kapan saja; perubahan hanya berlaku untuk generate berikutnya dan UI menandai klip yang dibuat dengan pengaturan lama.
- Endpoint: `GET/PUT /api/workspaces/{id}/settings`.

### 2. Karakter & latar dari section ini (kebutuhan 2)
- Pakai ulang `CharacterCreator` (plan 16) dan kartu latar (plan 15 langkah 1) di langkah *Pemeran & latar*. Tidak ada komponen baru selain penataan.
- Kesiapan ditampilkan: karakter tanpa gambar referensi, tanpa suara; latar tanpa gambar. Generate gambar beat diblokir untuk item yang belum punya gambar (karena justru gambar itu referensinya).

### 3. Suara karakter (kebutuhan 4)
- Tabel `character_voices(character_id PK, description TEXT, ref_id TEXT, source TEXT, created_at, updated_at)`: `source` = `upload` | `tts`. `ref_id` menunjuk tabel `refs` yang sudah ada (berkas media, durasi, `has_audio`), supaya hosting publik dan trim (plan 10/11) bisa dipakai ulang.
- Unggah: wav/mp3/m4a, dinormalisasi ffmpeg ke mono 48 kHz AAC, dipotong 3–15 dtk (batas akhir ditentukan spike). Tombol putar di kartu karakter.
- TTS: **hanya bila spike Fase 0 menemukan model TTS di OpenRouter** yang bisa dipanggil dengan kunci yang sama. Bila tidak ada, fitur ini memakai unggahan saja + deskripsi suara; tidak menambah penyedia baru tanpa persetujuan user.
- Saat generate video, suara karakter yang berbicara di adegan itu dikirim sebagai referensi audio (maks 3) dan dirujuk di prompt ("@Audio 1 adalah suara Momon"). Bila referensi audio ternyata tidak diterima OpenRouter, jatuh ke deskripsi suara di prompt saja (dicatat sebagai degradasi, ditampilkan di UI).

### 4. Beat per adegan (kebutuhan 5, bagian timeline)
- Tabel `scene_beats(id, scene_id, position, start REAL, end REAL, action TEXT, camera TEXT, cast TEXT JSON [character_id], dialogue TEXT JSON [{character_id, text}], image_id TEXT, created_at, updated_at)`.
- Aturan: beat berurutan, tidak tumpang tindih, menutup 0 sampai durasi adegan; panjang beat ≥ 1 dtk; maks 6 beat per adegan (batas referensi, lihat §6). Validasi di modul murni `beats.py`.
- Durasi adegan v2 dibatasi **4–15 dtk** (batas Seedance). Adegan lama yang lebih panjang ditandai "terlalu panjang untuk satu generate" dengan aksi "pecah jadi beberapa adegan" (AI atau bagi rata).
- "Pecah adegan jadi beat" dengan AI: model teks pilihan (plan 17 `textai.ask`), input = potongan naskah adegan, pemeran (nama, deskripsi, suara), latar, durasi, rasio. Keluaran draf → ditinjau → diterapkan. `kind` estimasi baru `scene_beats`.
- Tampilan: lajur waktu horizontal per adegan (beat sebagai blok yang lebarnya sebanding detik, bisa ditarik batasnya), kartu beat berisi gambar, aksi, dialog.

### 5. Gambar per beat (kebutuhan 5, bagian gambar)
- Endpoint `POST /api/beats/{id}/image` dengan `model` (default `image_model` proyek, dari daftar `Studio.image_models`), `confirmed_cost`. Hasil disimpan di `images` (kind `frame`, `scene_id`, kolom baru `beat_id`) sebagai take; `scene_beats.image_id` = take terpilih.
- Referensi yang dikirim, berurutan: gambar karakter yang tampil di beat (pakaian adegan bila ada, selain itu gambar terbaik lembar tampilan), gambar latar, lalu gambar beat sebelumnya bila user mencentang "lanjutkan dari beat sebelumnya". Jumlah dibatasi oleh `max_input_images` model (sudah dibaca di plan 06/16).
- Prompt gambar dirakit server dari aksi, kamera, waktu/cuaca adegan, rasio proyek, gaya proyek, dan nama karakter yang dipetakan ke urutan gambar ("tokoh di gambar 1 adalah Momon, kucing oranye").
- Rasio gambar = rasio proyek (pakai mekanisme `_aspect_option` yang sudah ada).
- Massal: "Gambar semua beat yang belum ada" per adegan atau per episode, satu konfirmasi total (pola `useBatch` plan 15).

### 6. Generate video Seedance (kebutuhan 6)
- Modul murni `seedance_request.py` → `build(scene, beats, cast, location, voices, settings, mode) -> {payload, references, warnings}`. Tidak memanggil jaringan; diuji penuh.
- **Mode referensi (default)**: `input_references` berurutan:
  1. gambar beat terpilih (urut waktu),
  2. satu gambar per karakter yang tampil (maks 3),
  3. gambar latar,
  4. audio suara karakter yang berdialog (maks 3),
  5. video previs (opsional, maks 1, bila ada dan dicentang).
  Batas gambar total 9: bila beat + karakter + latar > 9, yang dibuang pertama adalah gambar latar (latar sudah tampak di gambar beat), lalu gambar karakter yang sudah tampak di beat; tidak pernah gambar beat. Tiap pembuangan menjadi `warning`.
- **Prompt bertimecode**: legenda referensi lalu daftar shot, contoh:
  ```
  Referensi: @Image 1–3 = acuan bingkai shot 1–3. @Image 4 = Momon (kucing oranye). @Image 5 = Ruang tamu. @Audio 1 = suara Momon.
  Rasio 16:9, gaya: <gaya proyek>.
  [0–4 dtk] Shot 1 sesuai @Image 1: medium shot, Momon melompat ke sofa.
  [4–8 dtk] Shot 2 sesuai @Image 2: close-up, Momon berkata: "Aku lapar!"
  ...
  ```
  Format pastinya (notasi `@Image N` vs "image N", bahasa prompt) diputuskan oleh hasil spike. Dialog dalam tanda kutip untuk lip-sync.
- **Mode frame (cadangan)**: `frame_images` first_frame = gambar beat pertama, last_frame = gambar beat terakhir, tanpa `input_references` (keduanya tidak bisa digabung). Dipakai bila mode referensi gagal atau user memilih kontrol bingkai awal/akhir yang ketat.
- Parameter dari pengaturan proyek: model, resolusi, rasio, `generate_audio`; `duration` = durasi adegan (4–15).
- Hosting: gambar dikirim sebagai data URL; audio dan video lewat URL publik (tunnel/S3 plan 10). Bila hosting publik tidak aktif dan request butuh audio/video, UI menawarkan kirim tanpa audio/video (dengan peringatan) atau mengaktifkan tunnel.
- Hasil masuk `clips` (kind baru `storyboard`, `scene_id`), muncul di QueueDock, jadi take video adegan seperti sekarang. Render episode memakai `merge_videos` yang ada (semua klip satu resolusi/rasio berkat pengaturan proyek).
- Biaya: estimasi pakai SKU OpenRouter (audio, resolusi, `with_video_input`) dikali token per detik **hasil kalibrasi spike**; `usage.cost` nyata dicatat seperti sekarang. Tetap lewat konfirmasi + `authorize()`.

### 7. Frontend
- `pages/Storyboard.tsx`: pemilih section "Storyboard v2" vs alur lama.
- Berkas baru di `frontend/src/storyboard/v2/`: `ProjectSettings.tsx`, `StepVoices.tsx`, `BeatLane.tsx` (lajur beat per adegan), `BeatCard.tsx` (gambar + take + generate), `StepVideo.tsx` (pratinjau referensi yang akan dikirim + prompt hasil rakitan, bisa disunting sebelum kirim, estimasi). Langkah pemeran/latar dan naskah memakai komponen plan 15.
- Pratinjau request wajib terlihat sebelum generate: daftar referensi berurutan dengan nomor `@Image N`, peringatan pembuangan, durasi, resolusi, biaya.

## Langkah kerja
**Fase 0 - Spike berbayar (perlu persetujuan batas biaya; usul maks $1,50).** Skrip `scripts/spike_seedance_v2.py`, model `seedance-2.0-mini` 480p 4–5 dtk kecuali disebut:
1. 2 gambar karakter kartun + 1 gambar latar + prompt dengan `@Image N` vs prompt "image N": apakah penomoran dihormati.
2. 3 gambar beat + prompt bertimecode 3 shot: apakah urutan dan pembagian waktu diikuti.
3. Referensi audio (rekaman suara user / sampel sintetis) dengan beberapa nama field (`audio_url`, `input_audio`): apakah diterima, dan apakah suara hasil mengikuti.
4. 9 gambar sekaligus: diterima atau 400.
5. Kalibrasi biaya: `usage.cost` untuk 480p/720p, dengan/tanpa audio, dengan/tanpa video input, pada 2.0 dan mini → token per detik.
6. Cek katalog OpenRouter untuk model TTS (gratis, hanya baca katalog).
Hasil ditulis ke `docs/implementation/18-storyboard-v2-spike.md`; plan diperbarui di Riwayat bila temuan mengubah desain.

**Fase A - Pengaturan proyek.** Migrasi v14 (kolom `workspaces`), endpoint settings, penguncian rasio, tanda episode berbeda rasio; UI `ProjectSettings`. Test backend.

**Fase B - Suara karakter.** Tabel `character_voices`, unggah + normalisasi + trim, putar; TTS bila tersedia. Salin suara saat copy workspace. Test.

**Fase C - Beat + gambar beat.** Tabel `scene_beats`, `images.beat_id`, validasi `beats.py`, CRUD, AI pecah beat, generate gambar beat (take), massal. UI `BeatLane`/`BeatCard`. Test.

**Fase D - Generate Seedance.** `seedance_request.py` + test, endpoint `POST /api/scenes/{id}/storyboard-video` (+ estimasi `scene_storyboard_video`), mode referensi/frame, hosting, kind klip baru, massal per episode. UI `StepVideo` dengan pratinjau request.

**Fase E - Rapikan.** Render episode dari section v2, status kesiapan di stepper, dokumen implementation lengkap dengan daftar uji manual untuk user.

Tiap fase: `make test` dan `cd frontend && npm run build` hijau; uji UI dilakukan user.

## Kriteria selesai
- Proyek punya model/resolusi/rasio; semua gambar beat dan video v2 di semua episode memakai nilai itu; rasio terkunci setelah ada hasil.
- Karakter dan latar bisa dibuat dari section v2.
- Karakter bisa diberi suara (unggahan; TTS bila tersedia) dan suaranya ikut ke request video adegan yang memuat dialognya, atau ada peringatan jelas bila tidak bisa.
- Adegan bisa dibagi beat dengan rentang detik (manual/AI); tiap beat punya gambar dari model pilihan dengan referensi karakter + latar; take bisa dipilih.
- Video adegan dihasilkan Seedance dari referensi + prompt bertimecode, dengan pratinjau request, estimasi, dan konfirmasi biaya.
- Unit test untuk `beats.py`, `seedance_request.py` (urutan, pembuangan saat >9, penomoran, mode frame), pengaturan proyek (kunci rasio), suara (normalisasi, batas durasi), endpoint baru; semua test lama tetap hijau.
- File implementation 18 berisi hasil spike nyata dan daftar alur uji manual.

## Pertanyaan terbuka
1. **Proyek = workspace?** Plan menganggap ya (pengaturan disimpan di workspace). Bila maksud user "proyek" adalah tingkat baru di atas episode tapi di dalam workspace, desain §1 berubah (tabel `projects`).
2. **Sumber suara**: cukup unggah rekaman sendiri, atau harus bisa generate (TTS)? Bila TTS wajib dan OpenRouter tidak punya, perlu penyedia baru (biaya/kunci baru).
3. **Model gambar default** untuk beat: usul ditetapkan di pengaturan proyek (gaya konsisten antar episode), bisa diganti per generate.
4. **Batas biaya spike** Fase 0: usul $1,50.
5. **Model video default**: `seedance-2.0` (bisa 1080p, lebih mahal) atau `seedance-2.0-mini` (≈ setengah harga, maks 720p)?

## Revisi 1 (2026-10-26): revisi di tiap section
Permintaan user: fitur revisi di tiap section (dijawab "ya" atas usulan pola revisi seragam). Bagian ini menambah, tidak mengganti, desain di atas.

### Pola seragam
1. **Catatan revisi + generate ulang.** Tiap hasil AI punya tombol "Revisi": user menulis instruksi, AI membuat versi baru *dari* hasil sebelumnya (bukan dari nol). Tetap lewat estimasi → konfirmasi → `authorize()`.
2. **Versi, bukan timpa.** Hasil revisi = versi/take baru dengan `parent_id` + `revision_note`. Versi lama tetap bisa dipilih kembali. Tidak ada hasil yang hilang karena revisi.
3. **Tanda basi (stale).** Bila sesuatu di hulu berubah, hasil di hilir yang memakainya ditandai "perlu diperbarui" (tidak dihapus, tidak di-generate ulang otomatis). Dihitung dari hash input yang disimpan saat generate (pola `look_hash` plan 17 / `script_split_hash` plan 15).

### Per section
| Section | Revisi | Penyimpanan |
|---|---|---|
| Karakter & latar | "Revisi gambar" dengan instruksi: edit gambar (model edit plan 02) dengan gambar terpilih sebagai sumber + gambar referensi lain karakter itu | `images.parent_image_id` (sudah ada) + kolom baru `images.revision_note` |
| Suara | Unggah/generate ulang → versi baru; pilih versi aktif; putar dan bandingkan | Tabel `character_voices` diubah jadi berversi: `voice_versions(id, character_id, ref_id, description, source, revision_note, created_at)` + `characters.voice_id` aktif (menggantikan PK tunggal di §3) |
| Naskah | "Revisi dengan AI" (instruksi bebas) → draf diff (sebelum/sesudah) → terapkan; snapshot tiap kali naskah disimpan dari AI atau "simpan versi" | Tabel `film_script_versions(id, film_id, script, note, source ai/manual, created_at)`, maks 50 per episode (yang tertua dibuang, kecuali yang diberi nama) |
| Beat | "Revisi beat dengan AI" per adegan (instruksi) → draf ditinjau → terapkan; snapshot set beat sebelum tiap penerapan; "kembalikan versi" | Tabel `beat_versions(id, scene_id, beats JSON, note, created_at)` |
| Gambar beat | "Revisi" pada take: edit gambar dengan take itu sebagai sumber + referensi karakter/latar yang sama; hasil = take baru turunan | `images.parent_image_id` + `revision_note`; UI menampilkan pohon take (asal → revisi) |
| Video adegan | "Revisi" pada take video: request baru dengan prompt hasil rakitan + catatan revisi, referensi sama (opsional: gambar beat yang direvisi); bila spike membuktikan edit video Seedance, opsi "edit klip ini" (video sumber + instruksi) | `clips.parent_clip_id` (sudah ada) + kolom baru `clips.revision_note` |

### Tanda basi (rantai)
- Gambar/pakaian karakter atau gambar latar berubah → gambar beat yang memakainya basi → video adegan yang memakai gambar beat itu basi.
- Suara aktif berganti → video adegan dengan dialog karakter itu basi.
- Beat berubah (waktu, aksi, dialog, pemeran) → gambar beat itu basi (bila aksi/pemeran berubah) dan video adegan basi.
- Naskah berubah setelah beat dipecah → penanda "naskah berubah" per adegan (pola plan 15).
- Disimpan: `images.input_hash` dan `clips.input_hash` (hash dari id + versi referensi + teks prompt); status basi dihitung saat dibaca, tidak disimpan.
- UI: lencana "perlu diperbarui" + aksi massal "revisi semua yang basi" (satu konfirmasi total).

### Tambahan spike Fase 0
7. **Edit video Seedance lewat OpenRouter**: klip hasil sebelumnya sebagai `video_url` referensi + instruksi edit terarah ("ubah hanya: ..."). Diukur: apakah bagian yang tidak diminta tetap sama, durasi, biaya (SKU `with_video_input`). Bila gagal atau hasilnya berubah total, revisi video hanya memakai generate ulang dengan catatan (tabel di atas), dan "edit klip ini" tidak dibangun.
- Batas biaya spike diusulkan naik dari $1,50 menjadi **$2,00** karena tambahan uji ini.

### Dampak ke langkah kerja
- Fase A: tambah kolom `revision_note` (`images`, `clips`) dan `input_hash` di migrasi v14.
- Fase B: suara berversi (`voice_versions`).
- Fase C: `beat_versions`, `film_script_versions`, revisi gambar beat, revisi AI naskah/beat (`kind` estimasi baru `script_revise`, `scene_beats_revise`).
- Fase D: revisi video + perhitungan basi; edit video Seedance bila spike lolos.
- Fase E: lencana basi dan "revisi semua yang basi".

### Kriteria selesai tambahan
- Setiap section punya aksi revisi; revisi menghasilkan versi baru dengan asal + catatan; versi lama bisa dipilih kembali.
- Rantai basi teruji (unit test per mata rantai di atas).

### Pertanyaan terbuka tambahan
6. Batas riwayat versi naskah 50 per episode cukup?

## Revisi 2 (2026-10-26): tanpa batas di Storyboard v2
Permintaan user: "gausa ada batas di sini". Saat ditanya batas yang mana, user memilih keempatnya: batas per job $1 di v2, anggaran harian $5 di v2, batas biaya spike, dan batas teknis Seedance. Bagian ini mengganti keputusan grill 18 nomor 2, 3, dan 9 (batas spike), serta aturan beat/durasi di §4 dan §6.

### Biaya
- Semua `kind` estimasi v2 (`scene_beats`, `scene_beats_revise`, `script_revise`, gambar beat, `scene_storyboard_video`, revisi video) dilewatkan dari `MAX_COST_PER_JOB_USD` dan `DAILY_BUDGET_USD`: `authorize()` mendapat parameter `limits=False` untuk jalur v2. Jalur lama tetap memakai batasnya.
- **Yang tetap**: estimasi + dialog konfirmasi + pengecekan `confirmed_cost` (409 bila estimasi berubah). Itu bukan batas, melainkan persetujuan per generate (plan 04), dan mencegah tagihan yang tidak terlihat.
- Biaya v2 tetap dicatat dan tetap dihitung di total harian (supaya angka "terpakai hari ini" jujur), hanya tidak memblokir.
- Batch v2: satu konfirmasi total tanpa pemotongan "yang muat saja".
- Spike Fase 0: tanpa plafon. Biaya tiap uji dilaporkan di dokumen spike.

### Batas teknis
Batas yang berasal dari aturan kita dihapus; batas yang berasal dari model diatasi dengan **segmen otomatis**, bukan ditolak:
- Beat per adegan: tanpa batas (aturan "maks 6" dihapus). Panjang beat minimum tetap 1 dtk agar tiap beat punya gambar yang bermakna; ini validasi data, bukan batas jumlah.
- Durasi adegan: tanpa batas atas di v2 (tetap 1–120 dtk dari skema lama; batas 120 juga dilepas untuk v2, dicek ulang di grill). Adegan > 15 dtk dibagi otomatis menjadi **segmen** ≤ 15 dtk pada batas beat (tidak memotong di tengah beat bila bisa; beat > 15 dtk dipotong di 15 dtk). Segmen < 4 dtk digabung ke tetangganya.
- Referensi gambar: bila satu segmen butuh > 9 gambar (beat + karakter + latar), segmen dipecah lagi sampai tiap segmen ≤ 9 gambar. Aturan pembuangan gambar (§6) hanya dipakai bila pemecahan tidak mungkin (satu beat dengan > 9 referensi wajib), dengan peringatan.
- Audio referensi > 3 di satu segmen: segmen dipecah per pembicara bila bisa; selain itu suara ke-4 dst. jatuh ke deskripsi teks.
- Tiap segmen = satu request Seedance; klip segmen disambung (`media.merge_videos`) menjadi take video adegan. Estimasi = jumlah semua segmen, satu konfirmasi.
- Kontinuitas antar segmen: gambar beat terakhir segmen sebelumnya ikut sebagai referensi segmen berikutnya (dihitung ke batas 9).

### Dampak ke langkah kerja
- Fase A: `authorize(limits=False)` + test bahwa jalur v2 lolos di atas batas dan jalur lama tetap terblokir.
- Fase D: `seedance_request.plan_segments()` (murni, teruji: batas beat, gabung segmen pendek, pecah > 9 gambar, > 3 audio) + perakitan klip segmen.
- Pengaturan proyek tetap menampilkan perkiraan biaya per 10 dtk (informasi, bukan blokir).

## Revisi 3 (2026-10-26): hapus banyak adegan
Permintaan user: "tambahin hapus multiple adegannya". Mode "Pilih beberapa" di papan adegan (langkah Adegan v2, Timeline alur lama, dan tab Papan di Mode lanjutan): centang kartu (Shift+klik untuk rentang, Pilih semua, Kosongkan), lalu "Hapus N adegan" dengan satu konfirmasi yang menyebut nomor adegan. Backend: `POST /api/films/{film_id}/scenes/bulk-delete {scene_ids}` atomik (satu transaksi, nomor adegan diurut ulang sekali; ditolak seluruhnya bila ada id asing, daftar kosong, atau episode sedang dirender). Hasil generate tetap di library (hanya terlepas dari adegan); pemeran, beat, dan versi beat ikut dihapus. Risiko dari grill: salah hapus (mitigasi: konfirmasi dengan nomor), penghapusan setengah jadi (mitigasi: atomik).

## Riwayat
- 2026-10-26: draf awal.
- 2026-10-26: Revisi 3, hapus banyak adegan (endpoint atomik + mode pilih di papan).
- 2026-10-26: user: "gausa di test, langsung aja buat". Fase 0 (spike berbayar) dilewati atas permintaan user; Fase D dibangun langsung dengan format request dari dokumentasi ByteDance (`@Image N`/`@Audio N`, prompt bertimecode, `input_references` bertipe `image_url`/`audio_url`/`video_url`) yang BELUM terbukti lewat OpenRouter. Mitigasi: legenda "@Image N: ..." tetap terbaca bila notasinya tidak dikenali; bila penyedia menolak referensi audio, server mengulang tanpa audio (suara jadi deskripsi teks); pratinjau menampilkan persis yang dikirim dan prompt bisa disunting. Deviasi: adegan > 15 dtk ditolak dengan saran membagi adegan (segmen otomatis Revisi 2 belum dibangun); gambar acuan per beat belum bisa dibuat otomatis (video memakai gambar beat bila ada, selain itu karakter + latar).
- 2026-10-26: user: "modelnya di kunci seedance 2 aja". Model video Storyboard v2 dikunci ke keluarga Seedance 2.0 (`bytedance/seedance-2.0`, `-fast`, `-mini`): server menolak model lain (422) dan mengirim `allowed_video_models`; UI hanya menampilkan ketiganya. Model lain tetap bisa dipakai di Alur lama. Seedance 2.5 sengaja tidak termasuk.
- 2026-10-26: Revisi 1, revisi di tiap section (versi + catatan revisi + tanda basi), uji edit video Seedance di spike, usul batas spike $2,00.
- 2026-10-26: user menjawab "y": semua usulan default diterima (Proyek = workspace, suara unggah + TTS bila ada, model gambar default di pengaturan proyek, spike maks $2,00, video default `bytedance/seedance-2.0`, 50 versi naskah).
- 2026-10-26: setelah grill 18 (`docs/grill/18-storyboard-v2-grill.md`), desain berubah: rasio satu sumber (`films.aspect_ratio` diselaraskan ke proyek, baca-saja); estimasi menjelaskan blokir batas per job dan menampilkan biaya per 10 dtk; batch menghitung sisa anggaran harian; referensi gambar diperkecil ≤ 1536 px; model gambar difilter per rasio; batas 4–15 dtk hanya saat generate v2; centang izin suara + URL audio berumur pendek; copy workspace menyalin pengaturan + suara aktif; spike ditambah uji 8 (dialog bahasa Indonesia).
- 2026-10-26: Revisi 2, user: "gausa ada batas di sini" (keempat batas): v2 lepas dari batas per job dan harian (konfirmasi biaya tetap), spike tanpa plafon, batas beat/durasi dihapus dan batas model diatasi dengan segmen otomatis.

---

## Revisi 4 — Format prompt shot Seedance 2.0 (permintaan user: "untuk membuat adegan di sebuah episode dengan ai harus mengikuti format ini")

Semua prompt adegan yang dibuat AI, dan prompt yang dikirim ke Seedance, wajib berbentuk: **blok global** (`FORMAT`, `SUBJECT`, `WARDROBE`, `ENVIRONMENT`, `MOOD`) lalu **daftar shot** `SHOT N — m:ss to m:ss, UKURAN, LENSA, GERAK. Aksi.` Contoh dan aturan lengkap ada di pesan user (disalin ke `docs/reference/seedance-shot-format.md` saat implementasi).

### Pemetaan ke data yang sudah ada
| Bagian format | Sumber |
|---|---|
| FORMAT `15s / 10 SHOTS / genre` | total durasi beat + jumlah beat + genre proyek (field baru `workspaces.genre`, opsional; kosong → bagian genre dihilangkan) |
| SUBJECT `@image_1 — deskripsi` | karakter yang tampil di adegan: gambar acuan + `characters.description` |
| WARDROBE | field baru `characters.wardrobe` (teks bebas, opsional); kosong → bagian dihilangkan, bukan dikarang |
| ENVIRONMENT | latar adegan (nama + deskripsi) + gambar acuan; sub-lokasi (A)(B)… ditunda |
| MOOD | field baru `scenes.mood` (opsional) atau gaya proyek (`workspaces.style`) |
| SHOT N | beat: `start/end`, `camera` (gerak), field baru `scene_beats.size` (WS/MS/MCU/CU/ECU) dan `scene_beats.lens` (24/35/50/85mm), `action`, dialog |

### Perubahan
1. **Migrasi v16**: `scene_beats.size`, `scene_beats.lens`, `characters.wardrobe`, `scenes.mood`, `workspaces.genre`. Semua nullable; beat lama tetap valid (ukuran/lensa kosong → bagian itu dilewati di prompt).
2. **`beats.clean()`**: validasi `size` ∈ {WS,MS,MCU,CU,ECU}, `lens` ∈ {24,35,50,85}; peringatan bila durasi shot > 3 dtk ("pecah jadi shot lebih pendek"), tetap dibolehkan; peringatan bila tiga shot berturut-turut punya ukuran+lensa sama (variasi).
3. **`seedance_request.build()`** ditulis ulang agar keluaran mengikuti format di atas. Notasi gambar berubah dari `@Image N` menjadi **`@image_N`** (sesuai format user); legenda referensi tetap ada di akhir blok SUBJECT/ENVIRONMENT. Timestamp `m:ss`. Konsistensi pakaian/aksesori cukup di WARDROBE, tidak diulang per shot.
4. **Pembuatan adegan dengan AI** (bagian Fase C yang belum dibangun): endpoint `POST /api/scenes/{id}/beats/ai` memakai model teks pilihan (plan 17), keluaran JSON terstruktur (bukan teks bebas) lalu dirender oleh `build()`. Prompt sistemnya memuat aturan format: shot 1–3 dtk, timestamp berurutan tanpa tumpang tindih, total = durasi adegan, variasikan ukuran/lensa, satu shot satu ide aksi, `locked` untuk shot diam. Hasil divalidasi `beats.clean()`; yang tidak lolos ditolak, tidak diperbaiki diam-diam. Estimasi biaya + konfirmasi wajib (kind `scene_beats`).
5. **UI**: editor beat mendapat pilihan ukuran & lensa; panel karakter mendapat "Pakaian"; panel adegan mendapat "Mood"; pengaturan proyek mendapat "Genre". Pratinjau prompt di langkah 6 menampilkan format baru.

### Di luar lingkup
Sub-lokasi berlabel (A)(B)(C), auto-segmen >15 dtk, gambar acuan per beat otomatis (tetap di daftar tunda).

### Risiko yang perlu digrill
- Notasi `@image_N` dan format timestamp ini belum terbukti diterima Seedance via OpenRouter (spike dilewati).
- Model teks murah bisa melanggar aturan 1–3 dtk / total durasi → validasi keras + satu kali ulang.
- Perubahan notasi memecah tes `test_storyboard_video.py` yang mengunci `@Image N`; tes ditulis ulang, bukan dilonggarkan.

### Riwayat
- Revisi 4: format prompt shot Seedance 2.0 dari user (ditambahkan; Revisi 1–3 tidak diubah).

---

## Revisi 5 — Naskah yang ditulis AI mengikuti format shot Seedance 2.0

Laporan user: "aku coba tulis naskah dengan ai tapi ga sesuai format yang tadi aku kirim". Penyebab: `script.SCRIPT_SYSTEM` meminta prosa bebas; Revisi 4 hanya mencakup beat dan prompt video, bukan langkah Naskah.

### Bentuk naskah baru
Naskah = deretan blok adegan (maks 15 dtk per adegan, batas Seedance), tiap blok memakai format `docs/reference/seedance-shot-format.md`, dengan sintaks mention yang sudah ada (`@[Nama]`, `#[Nama]`), bukan `@image_N`:

```
ADEGAN 1 — #[Dapur]
FORMAT: 12s / 5 SHOTS / komedi keluarga
SUBJECT: @[Momon], kucing oren gemuk, mata bulat, ekor tebal
WARDROBE: Momon: syal merah
ENVIRONMENT: #[Dapur], pagi hari. (A) meja makan. (B) kulkas.
MOOD: hangat, jenaka
SHOT 1 — 0:00 to 0:02, WS, 24mm, locked. @[Momon] menyelinap masuk.
SHOT 2 — 0:02 to 0:04, MS, 35mm, slow push-in. ... @[Momon] says: "Lapar…"
```

### Perubahan
1. **`SCRIPT_SYSTEM` ditulis ulang**: AI wajib menulis blok seperti di atas (aturan sama dengan `beatsai.SYSTEM`: shot 1–3 dtk, timestamp bersambung, total = FORMAT, variasi ukuran/lensa, satu shot satu ide). Hanya karakter dan latar episode; tidak mengarang yang baru; WARDROBE dari deskripsi/tampilan yang diberikan, kosong bila tidak ada.
2. **Pengurai murni `script_format.py`**: membaca blok di atas jadi daftar adegan + beat (ukuran, lensa, gerak, aksi, dialog, waktu), pemeran dari mention, latar dari `#[…]`, MOOD → `extra_prompt`, durasi → `planned_seconds`. Dipakai untuk:
   - **memvalidasi keluaran AI** (salah format → satu kali ulang dengan pesan galat, lalu 502; tanpa perbaikan diam-diam),
   - **membuat adegan + beat dari naskah berformat tanpa panggilan AI** (gratis). Naskah prosa lama tetap memakai pemisah AI yang ada.
3. **Alur "Buat adegan"**: bila naskah terdeteksi berformat, hasil berupa draf yang sama bentuknya dengan draf pemisah AI (ditinjau lalu diterapkan), beat ikut tersimpan lewat `Beats.replace`. Adegan > 15 dtk ditolak dengan pesan jelas.
4. **UI**: langkah Naskah menampilkan lencana "format Seedance: N adegan, M shot" atau daftar baris yang bermasalah; tombol bertuliskan sumbernya ("dari format, gratis" atau "dengan AI").

### Di luar lingkup
Sub-lokasi (A)(B) hanya teks bebas di ENVIRONMENT (tidak jadi entitas); GENRE di baris FORMAT tidak mengubah genre proyek otomatis.

### Risiko untuk digrill
Model teks murah melanggar format; mention nama berspasi; naskah campuran (sebagian prosa); dialog tanpa sintaks pasti (diputuskan: `@[Nama] says: "…"`); migrasi tidak diperlukan.

### Riwayat
- Revisi 5: dari laporan user soal naskah AI (Revisi 1–4 tidak diubah).

---

## Revisi 6 — Ubah adegan dengan AI

Permintaan user: "masih kurang fitur edit dengan ai, jadi adegannya bisa di update dengan AI". Ini bagian "revisi di tiap section" (Revisi 1) untuk adegan yang belum dibangun.

### Perilaku
Pada satu adegan, user menulis instruksi bebas ("ubah jadi malam hari", "tambah dialog Momon yang lapar", "buat lebih cepat, 8 detik", "ganti shot 3 jadi close-up") lalu AI mengembalikan **versi baru adegan** (beat dan catatan adegan). Hasilnya **draf**: ditampilkan berdampingan dengan versi sekarang, user menerapkan atau membuang. Tidak ada perubahan tersimpan tanpa persetujuan.

### Desain
1. **`beatsai.py`**: prompt revisi memakai aturan format yang sama dengan pembuatan shot (1–3 dtk, bersambung, variasi ukuran/lensa, hanya pemeran adegan) ditambah: beat sekarang (JSON), MOOD/waktu/catatan adegan sekarang, dan instruksi user. Aturan "ubah seperlunya, pertahankan yang tidak disebut" supaya bagian yang tidak diminta tidak berubah.
2. **`Beats.revise_ai(scene_id, instruction, …)`** + `POST /api/scenes/{id}/revise`; estimate kind `scene_revise`. Keluaran JSON `{shots:[…], mood?, time_of_day?, total_seconds?}`; divalidasi `beats.clean`; salah → ulang SEKALI dengan galat, lalu 502 (pola sama dengan `generate_ai`). Instruksi maksimal 500 karakter, wajib tidak kosong.
3. **Identitas beat**: AI memberi `keep` (nomor beat lama) pada shot yang berasal dari beat lama; id dan gambar acuan beat itu dipertahankan hanya bila `keep` valid dan tidak ganda. Shot baru = id baru, tanpa gambar.
4. **Penerapan**: lewat editor beat yang sudah ada (draf belum tersimpan) lalu Simpan → `Beats.replace` otomatis memotret versi lama sehingga **bisa dikembalikan** dari Versi. Catatan versi memuat instruksi user. Perubahan MOOD/waktu diterapkan ke adegan saat Simpan, bukan sebelumnya.
5. **UI** (langkah Beat): kotak "Ubah dengan AI" dengan instruksi + beberapa chip contoh, pemilih model teks, estimasi, konfirmasi biaya; pratinjau sebelum/sesudah (daftar shot dengan waktu, ukuran, lensa, aksi; baris yang berubah ditandai); tombol Terapkan ke editor / Buang.
6. Biaya: estimasi + konfirmasi wajib (kind `scene_revise`).

### Di luar lingkup
Merevisi banyak adegan sekaligus; menulis ulang blok adegan di teks naskah (naskah tidak ikut berubah); revisi gambar/video dengan AI (tetap lewat alur generate masing-masing).

### Risiko untuk digrill
Model mengubah hal yang tidak diminta; total durasi bergeser dari durasi adegan; `keep` salah/ganda; instruksi mengandung perintah sistem (prompt injection → diperlakukan sebagai data di blok terpisah); biaya ganda saat ulang.

### Riwayat
- Revisi 6: ubah adegan dengan AI (Revisi 1–5 tidak diubah).

---

## Revisi 7 — Ubah naskah dengan AI (langkah Naskah)

Permintaan user: "aku butuh di naskah juga" (setelah Revisi 6 yang hanya ada di langkah Beat). Di langkah Naskah baru ada "Tulis dengan AI" (tulis/tulis ulang seluruh naskah, tanpa instruksi).

### Perilaku
Di langkah Naskah, bila naskah sudah ada, muncul "Ubah dengan AI": user menulis instruksi ("ubah adegan 3 jadi malam", "tambah adegan di mana Momon ketahuan", "buat adegan 2 lebih singkat"). AI mengembalikan **naskah baru berformat Seedance**, ditampilkan sebagai perbandingan per adegan (yang berubah disorot), lalu user menerapkannya ke editor naskah (draf, belum tersimpan sampai Simpan) atau membuangnya.

### Desain
1. `script.py`: `REVISE_SCRIPT_SYSTEM` = aturan format `SCRIPT_SYSTEM` + aturan revisi: ubah hanya yang diminta, salin utuh blok adegan yang tidak disentuh (karakter demi karakter), nomor ADEGAN diurut ulang bila ada adegan disisip/dihapus, tetap hanya karakter dan latar episode.
2. `Journey.script_revise_estimate` / `script_revise` + `POST /api/films/{id}/script/revise` (`ReviseIn`), estimate kind `script_revise`. Naskah sekarang dikirim UTUH (tidak dipotong 6.000 karakter seperti "Tulis dengan AI"); batas keluaran dihitung dari panjang naskah (min 4.000, maks 16.000 token) sehingga naskah panjang tidak terpotong. Estimasi memakai instruksi sepanjang batas 500 karakter (konstan, tanpa 409 palsu).
3. Validasi sama dengan penulisan: diurai `script_format.parse`; salah format → ulang SEKALI dengan daftar galat → 502 (digeneralisasi dari `_check_script`). Naskah sekarang berupa prosa boleh direvisi; hasilnya wajib berformat (jadi ini juga cara mengubah prosa lama ke format).
4. Perbandingan oleh server: `script_format` memecah naskah lama dan baru per blok adegan; tiap blok baru diberi `changed` bila teksnya (dinormalisasi spasi) tidak sama dengan blok lama di nomor yang sama atau yang cocok persis di nomor lain; juga `removed` (jumlah blok lama yang hilang). Respons: `{script, scenes:[{n,changed,text}], previous_scenes, warnings, cost, attempts}`.
5. UI (StepScript): kotak instruksi + chip contoh + pemilih model + estimasi/konfirmasi → daftar adegan dengan sorotan perubahan (dan blok lama untuk yang berubah) → "Terapkan ke editor" / "Buang". Konfirmasi bila editor punya perubahan belum tersimpan.
6. Setelah naskah disimpan, mekanisme `script_changed` yang sudah ada memberi tanda "Naskah berubah sejak adegan dibuat" di langkah Adegan.

### Di luar lingkup
Sinkronisasi otomatis adegan/beat yang sudah ada dengan naskah baru (user membuat ulang adegan dari format lewat langkah Adegan, atau mengubah per adegan lewat Revisi 6); revisi sebagian teks di dalam editor (hanya seluruh naskah); riwayat versi naskah.

### Risiko untuk digrill
Model menulis ulang blok yang tidak diminta; naskah panjang terpotong di batas token keluaran; biaya besar karena naskah dikirim dan ditulis ulang utuh; nomor adegan bergeser; instruksi menyuntik perintah; naskah diedit user saat AI bekerja (hasil menimpa); perbandingan salah menandai karena beda spasi.

### Riwayat
- Revisi 7: ubah naskah dengan AI (Revisi 1–6 tidak diubah).

---

## Revisi 8 — Satu sumber: "prompt adegan" (latar, pemeran, beat diturunkan dari prompt)

Laporan user: di sidebar ada prompt adegan yang sudah menyebut Adegan dan Karakter, tetapi di bawahnya ada lagi pilihan Latar dan Pemeran: "kan nabrak". Instruksi: generate video cukup dari prompt adegan; prompt bisa disunting; aset harus terhubung.

### Diagnosis
Latar/pemeran/beat/mood/durasi punya DUA sumber: teks blok adegan (naskah, "Dari naskah", prompt di panel video) dan data terstruktur (`scenes.location_id`, `scene_cast`, `scene_beats`) yang diedit lewat dropdown/editor terpisah. Mengubah salah satu tidak mengubah yang lain; prompt video yang sudah disunting bahkan tetap menyebut `@image_2` setelah pemerannya dihapus.

### Prinsip baru (Storyboard v2 saja; "Alur lama" tidak berubah)
**Prompt adegan = sumber tunggal.** Isinya blok berformat Seedance yang sama dengan naskah (`ADEGAN … FORMAT … SUBJECT … WARDROBE … ENVIRONMENT … MOOD … SHOT …`, mention `@[Karakter]` dan `#[Latar]`). Latar, pemeran, beat, MOOD, dan durasi DITURUNKAN dari prompt tiap kali prompt disimpan; di v2 tidak ada lagi pemilih terpisah.

### Perubahan
1. **Migrasi v17**: `scenes.prompt TEXT`. Adegan yang belum punya prompt: prompt dirender dari data terstruktur yang ada (satu fungsi `scene_prompt.render`, kebalikan pengurai), sehingga adegan lama tidak kehilangan apa pun.
2. **`PUT /api/scenes/{id}/prompt`**: urai dengan `script_format` (satu adegan). Gagal → 422 dengan nomor baris. Berhasil → satu transaksi (tanpa kunci DB bersarang): `location_id`, `scene_cast` (tampilan/aksi karakter yang sama dipertahankan), `scene_beats` (lewat `Beats.replace`, versi lama terpotret, catatan "dari prompt adegan"), `extra_prompt` (MOOD), `planned_seconds`, lalu `prompt`. Karakter proyek yang disebut tetapi belum ada di episode otomatis masuk episode (perilaku yang sudah ada untuk pemeran adegan); nama yang tidak dikenal = galat, bukan entitas baru. Mengubah beat/pemeran lewat jalur lain (editor Beat, revisi AI) merender ulang `prompt` dari data supaya tetap sinkron.
3. **Inspector (v2)**: bagian Latar dan Pemeran diganti **editor prompt adegan** (dengan autocomplete mention seperti Naskah, validasi hidup) dan **kartu aset turunan** (thumbnail latar + karakter yang disebut, tanda bila aset belum bergambar). Tidak ada dropdown atau editor pemeran terpisah di v2.
4. **Generate video (langkah 6)**: request dirakit dari prompt adegan itu: blok → `build()` (mention → `@image_N` yang benar saat dikirim) + gambar karakter dan latar yang DISEBUT. Satu prompt saja: kotak prompt kedua di panel video dihapus (panel hanya menampilkan prompt adegan yang sama, bisa diedit di tempat dan tersimpan ke adegan). Dihapus dari panel video: centang previs 3D dan gambar acuan beat. Sampel suara karakter yang berdialog tetap (diturunkan dari penutur di prompt). Backend modul previs/beat-image tidak dihapus.
5. **Keterhubungan aset**: mention karakter/latar tanpa gambar → peringatan di editor dan di panel video; server menolak (422) generate bila ada mention tanpa aset yang bisa dikirim ATAU nama tak dikenal. Tidak ada lagi nomor `@image_N` yang bisa basi, karena nomor ditentukan server saat kirim.
6. Naskah → adegan (Revisi 5) mengisi `prompt` dari blok naskah; revisi AI adegan (Revisi 6) merender ulang prompt.

### Di luar lingkup
Alur lama; sub-lokasi; sinkronisasi balik adegan → teks naskah (naskah tetap berupa catatan awal).

### Risiko untuk digrill
Parse gagal membuat user tak bisa menyimpan (pesan galat harus jelas, draf tetap di editor); dua jalur edit bersamaan (editor Beat vs prompt) saling menimpa; kehilangan tampilan/aksi karakter per adegan; adegan lama dengan data yang tidak bisa dirender ke format; migrasi; biaya 0 (tanpa AI).

### Riwayat
- Revisi 8: satu sumber prompt adegan (Revisi 1–7 tidak diubah).

---

## Revisi 9 — Frame awal dari adegan sebelumnya (adegan ke-2 dst.)

Permintaan user: "untuk adegan ke 2 ke atas aku mau ada fitur bisa atur start frame dari adegan sebelumnya (kalau di centang)".

### Fakta
- Katalog publik OpenRouter (dibaca 2026-10-27): `seedance-2.0`, `-2.0-fast`, `-2.0-mini` mendukung `frame_images` `first_frame` dan `last_frame`.
- Dokumentasi OpenRouter: `frame_images` dan `input_references` **tidak bisa digabung** (plan 01: bila keduanya dikirim, frame yang diprioritaskan; perilaku nyata belum diuji berbayar). Jadi mode frame awal tidak bisa sekaligus mengirim gambar karakter/latar/suara sebagai referensi.
- `media.extract_last_frame` dan pola `extend_clip` (frame akhir → gambar `kind="frame"`) sudah ada.

### Perilaku
Adegan ke-2 dan seterusnya punya kotak centang **"Mulai dari frame akhir adegan sebelumnya"** (panel video langkah 6). Bila dicentang, video adegan itu dibuat dengan **frame akhir video adegan sebelumnya** sebagai frame pertama.

### Desain
1. **Migrasi v18**: `scenes.start_from_prev INTEGER NOT NULL DEFAULT 0`; masuk `SCENE_FIELDS` dan `Scenes.public` (`start_from_prev`). Adegan pertama menolak nilai 1 (422). Duplikat adegan: bawaan 0.
2. **`StoryboardVideo.plan`**: bila `start_from_prev`: adegan sebelumnya (menurut urutan SAAT INI) harus punya klip `completed` berkas ada, bila tidak 422 ("buat/ pilih video adegan N dulu"). Rencana memuat `start_frame {scene_number, clip_id}`.
3. **Pengiriman**: frame akhir diambil dari klip itu saat generate (bukan disimpan lebih awal), dinormalisasi, disimpan sebagai gambar library `kind="frame"` (dibersihkan bila penyedia menolak, seperti `extend_clip`), dikirim sebagai `frame_images=[{frame_type:"first_frame"}]`. **`input_references` tidak dikirim** (gambar karakter, latar, suara; previs). Prompt: mention diselesaikan menjadi nama biasa (tanpa `@image_N`), suara dijelaskan lewat teks, dan satu baris ditambahkan sebelum SHOT: "Start exactly from the provided first frame and continue seamlessly from it."
4. **Estimasi**: `mode="i2v"`, 1 input gambar, durasi sama (tanpa tarif video-input). Konfirmasi biaya tetap wajib.
5. **Catatan klip**: `params.start_from = {scene_id, clip_id, image_id}` supaya terlacak; gambar frame dilepas dari library hanya lewat penghapusan biasa.
6. **UI (langkah 6)**: kotak centang di panel adegan (nonaktif dengan penjelasan bila adegan pertama, atau adegan sebelumnya belum punya video selesai); saat dicentang, daftar aset diganti kartu "Frame awal: frame akhir video adegan N" (pratinjau dari video itu), dan catatan jelas: "Gambar karakter, latar, dan sampel suara tidak dikirim di mode ini; wajah dan tempat mengikuti frame awal." Penanda `start_from_prev` tampil di baris adegan ("berantai dari adegan N").
7. **Batch "Buat semua video yang belum ada"**: adegan berantai hanya diikutkan bila adegan sebelumnya SUDAH selesai; sisanya ditampilkan sebagai "menunggu adegan N" (user menjalankan lagi setelah selesai). Tidak ada antrean otomatis menunggu job.

### Di luar lingkup
`last_frame` (frame akhir yang dituju); membuat ulang otomatis adegan berikutnya saat video sebelumnya diganti (hanya peringatan "adegan sebelumnya berubah" bila murah dibuat); menggabungkan gambar karakter ke mode frame (butuh bukti API bahwa kombinasi aman).

### Risiko untuk digrill
Kombinasi frame+referensi ternyata diterima API (peluang untuk revisi); frame akhir hitam/fade; rasio frame ≠ rasio proyek; adegan sebelumnya dihapus/diurutkan ulang; klip sebelumnya diganti setelah adegan ini dibuat (rantai basi); berkas klip hilang; biaya; file frame yatim; deadlock kunci DB.

### Riwayat
- Revisi 9: frame awal dari adegan sebelumnya (Revisi 1–8 tidak diubah).

---

## Revisi 10 — Ubah adegan dengan AI di langkah Adegan

Permintaan user: "di bagian adegan aku mau bisa update adegan dengan AI". "Ubah dengan AI" (Revisi 6) ada di langkah Beat dan bekerja pada beat; di langkah Adegan (inspector, tempat prompt adegan diedit, Revisi 8) belum ada.

### Perilaku
Di inspector langkah Adegan, di bawah editor prompt adegan, ada **"Ubah dengan AI"**: user menulis instruksi ("pindahkan ke dapur", "tambah Sari di adegan ini", "buat jadi malam dan lebih tegang") lalu AI mengembalikan **prompt adegan baru** (blok berformat Seedance yang sama dengan yang diedit). Hasilnya draf: ditampilkan dengan baris yang berubah disorot dan blok lama bisa dibuka; "Terapkan ke editor" mengisi editor prompt sebagai teks belum tersimpan; menyimpan prompt (tombol Simpan yang sudah ada) menurunkan latar, pemeran, beat, mood, dan durasi. "Buang" tidak mengubah apa pun.

### Desain
1. `script.py`: `REVISE_SCENE_SYSTEM` = `REVISE_SCRIPT_SYSTEM` + aturan satu blok: kembalikan TEPAT SATU blok adegan, nomor ADEGAN tetap, hanya karakter dan latar yang diberikan, jangan menambah/mengurangi blok.
2. `ScenePrompt.revise_estimate` / `revise` + `POST /api/scenes/{id}/prompt/revise` (`ReviseIn`), estimate kind `scene_prompt_revise`. Konteks: prompt tersimpan (atau dirender dari data), daftar karakter dan latar proyek (nama + deskripsi), genre dan gaya proyek. Estimasi memakai instruksi sepanjang batas (konstan), seperti Revisi 6/7. Instruksi di blok DATA.
3. Validasi keluaran dengan `ScenePrompt.parse` (satu blok, nama dikenal dan tidak ganda, timestamp bersambung, shot ≤ 15 dtk total, ≤ 3 pemeran); salah → ulang SEKALI dengan galat → 502. Kedua panggilan tercatat (`text_jobs.kind = scene_prompt_revise`).
4. Respons: `{prompt, changed: [nomor baris yang berubah/baru], previous, warnings, cost, attempts}`; perbandingan per baris dihitung server (multiset baris, bukan posisi).
5. **UI**: tombol dinonaktifkan selama editor punya perubahan belum tersimpan ("simpan prompt dulu"), karena AI merevisi prompt yang tersimpan dan estimasi harus sama dengan panggilan. Pemilih model teks, estimasi, konfirmasi biaya. Setelah diterapkan, editor menunjukkan "belum disimpan" dan validasi hidup yang sudah ada berjalan.
6. "Ubah dengan AI" di langkah Beat (Revisi 6) tetap ada; keduanya konsisten karena beat dan prompt saling menurunkan (Revisi 8).

### Di luar lingkup
Merevisi banyak adegan sekaligus; menyimpan otomatis hasil AI; riwayat versi prompt (versi beat lama tetap terpotret saat menyimpan).

### Risiko untuk digrill
Model mengubah bagian yang tidak diminta; mengembalikan lebih dari satu blok atau menghapus label; nama karakter/latar baru yang dikarang; instruksi menyuntik perintah; editor kotor saat tombol ditekan; biaya ganda saat ulang; nomor ADEGAN berubah; kesalahan durasi >15 dtk.

### Riwayat
- Revisi 10: ubah adegan dengan AI di langkah Adegan (Revisi 1–9 tidak diubah).
