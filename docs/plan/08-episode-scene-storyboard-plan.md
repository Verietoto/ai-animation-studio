# 08 - Storyboard per episode dan adegan (Plan)

- Status: disetujui user ("go", 2026-10-20) dan sudah digrill. Tahap tanpa biaya selesai di kode (lihat `docs/implementation/08-episode-scene-storyboard-implementation.md`); tahap berbayar (keyframe/video/latar dari teks) menunggu budget spike dari user; uji frontend menunggu user
- Tanggal: 2026-10-20
- Asal: permintaan user "oke lanjut planning untuk bagian storyboard, gimana iar uxnya enak untuk develop per episode dan per scene dalam episode itu, latarnya apa aja, karakter baju dan apa yang dilakukan".

## Tujuan
Storyboard menjadi tempat **menulis dan membangun cerita**, bukan hanya mengurutkan klip jadi. Satu workspace (= satu serial/proyek) berisi beberapa **episode**. Tiap episode berisi **adegan** berurutan. Tiap adegan mencatat:
- **latar**: lokasi (bisa dipakai ulang antar adegan) + waktu/suasana,
- **pemeran**: karakter yang muncul, **baju** yang dipakai di adegan itu, dan **apa yang dilakukan** masing-masing,
- **kamera** dan catatan dialog/narasi.

Dari data itu aplikasi menyusun prompt sendiri, membuat **keyframe** (gambar adegan) lalu **video** adegan. Episode dirender menjadi satu video seperti film sekarang.

## Kondisi sekarang (dicek di kode)
- `films(id, title, clip_ids JSON, merged_path, rendered_ids, render_status, …, workspace_id)`. Adegan = id klip saja, tanpa data cerita (`backend/app/films.py`).
- `pages/Storyboard.tsx`: daftar film kiri, player, timeline drag (`@dnd-kit`), kolam "Klip tersedia".
- Karakter punya sheet (`character_images` berlabel front/side/…) dan bisa dikunci di Edit Foto (plan 06, `editprompt.plan_inputs/build_prompt`). Edit selalu butuh gambar sumber (tidak ada text-to-image). Input gambar maksimal 5 (1 sumber + 4) kecuali model bilang lain.
- Belum ada konsep lokasi, baju, ataupun episode.

## Ruang lingkup
Termasuk:
1. **Episode** = baris `films` yang sudah ada, ditambah nomor + sinopsis. UI menyebutnya "Episode". Tabel tidak di-rename.
2. **Adegan** (tabel baru `scenes`) dengan latar, pemeran (+ baju + aksi), kamera, dialog/catatan, keyframe terpilih, video terpilih.
3. **Latar** (tabel baru `locations`): nama, deskripsi, gambar referensi. Per workspace, dipakai ulang di banyak adegan.
4. **Lemari baju** (tabel baru `outfits`): per karakter, nama + deskripsi + gambar referensi opsional. Baju bawaan = gambar sumber karakter.
5. Prompt adegan dirakit otomatis dari data terstruktur (fungsi murni, dipakai bersama oleh estimasi dan generate) dan bisa ditambah teks bebas.
6. **Buat keyframe** dan **Buat video** per adegan lewat alur biaya yang sama (estimasi → konfirmasi → `confirmed_cost`). Hasil disimpan sebagai *take*; user memilih satu.
7. Render episode = gabungan video terpilih tiap adegan, urut. Pakai `_render_job` yang ada.
8. Migrasi film lama: tiap klip di `clip_ids` menjadi satu adegan dengan video itu terpilih. Tidak ada data yang hilang.

TIDAK dikerjakan (bisa jadi plan sendiri):
- AI yang menulis naskah/adegan dari sinopsis (LLM). Lihat pertanyaan terbuka 1.
- Generate massal "semua adegan sekaligus" dengan satu konfirmasi biaya. v1 per adegan.
- Suara/dialog jadi audio, subtitle, musik.
- Tingkat "serial" di atas episode: workspace sudah berperan sebagai serial.
- Menyalin episode/adegan antar workspace (sesuai keputusan plan 07: film tidak disalin).
- Shot di dalam adegan (satu adegan = satu klip utama; perpanjangan klip tetap lewat Extend).

## Desain UX

### Struktur halaman Storyboard (`#/storyboard`)
```
┌ Episode ────┐┌ Episode 3 · "Pulang ke Desa" ── [Papan|Naskah|Timeline] ──┐┌ Inspector adegan ─────┐
│ Ep 1  6/6 ✓ ││ Sinopsis (bisa dilipat)                                    ││ Adegan 4              │
│ Ep 2  3/5   ││ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌ + ┐                  ││ Latar  [Sawah ▾] Senja│
│▶Ep 3  1/8   ││ │ key  │ │ key  │ │  —   │ │ ▶vid │ │   │                  ││ Pemeran               │
│ + Episode   ││ │Sawah │ │Rumah │ │Pasar │ │Sawah │ └───┘                  ││  Rani  [Kebaya ▾]     │
│             ││ │Rani… │ │Rani, │ │Budi  │ │Rani  │                        ││   "berlari ke pematang"│
│ Bahan cerita││ │●siap │ │●key  │ │○naskh│ │●siap │                        ││  + Tambah karakter    │
│  Latar (5)  ││ └──────┘ └──────┘ └──────┘ └──────┘                        ││ Kamera [dolly in ▾]   │
│  Karakter   ││                                                            ││ Dialog/catatan        │
└─────────────┘└────────────────────────────────────────────────────────────┘│ ▸ Prompt jadi (lihat) │
                                                                              │ [Buat keyframe $0.04] │
                                                                              │ Take: ▣ ▢ ▢           │
                                                                              │ [Buat video  $0.30]   │
                                                                              └───────────────────────┘
```
- **Kiri**: daftar episode (nomor, judul, progres "adegan siap/total") + tautan "Bahan cerita": **Latar** dan **Karakter** (lemari baju). Episode bisa diurut ulang nomornya.
- **Tengah**, tiga tampilan untuk episode aktif:
  - **Papan** (bawaan): kartu adegan berurutan (drag untuk urut). Kartu = keyframe/video terpilih, nama latar + waktu, avatar pemeran, potongan aksi, status. Kartu terakhir "+" menambah adegan.
  - **Naskah**: satu baris per adegan, semua field teks bisa diketik langsung (latar, pemeran, aksi, dialog). Untuk menulis satu episode penuh dengan cepat sebelum generate apa pun. `Enter` di baris terakhir = adegan baru. `Tab` pindah field.
  - **Timeline**: tampilan sekarang (urutan + durasi + player + Render episode).
- **Kanan, inspector adegan**: semua field adegan + prompt jadi (bisa dilihat, dan teks tambahan bisa diketik) + tombol biaya + daftar take.

### Supaya enak dipakai
- **Kontinuitas otomatis**: adegan baru mewarisi latar, waktu, pemeran, dan baju dari adegan sebelumnya. Yang diubah biasanya hanya aksi. Ada juga "Duplikat adegan".
- **Status adegan** dihitung, bukan diisi: `naskah` (belum ada keyframe) → `keyframe` → `video diproses` → `siap` / `gagal`. Progres episode = jumlah `siap`.
- **Pilih atau buat di tempat**: dropdown latar dan baju punya "+ Latar baru…" / "+ Baju baru…" (nama, deskripsi, gambar dari library/unggah) tanpa pindah halaman.
- **Take**: keyframe dan video bisa dibuat ulang. Semua hasil tersimpan sebagai take (thumbnail kecil). Klik untuk memilih yang dipakai. Take lama tidak dihapus otomatis.
- **Keyframe bisa juga dari library**: "Pakai gambar yang ada" untuk adegan yang keyframenya sudah dibuat di Edit Foto.
- Kartu adegan menandai masalah: latar tanpa gambar, karakter tanpa sheet, baju tanpa gambar (boleh, tapi hasil kurang konsisten), terlalu banyak gambar untuk model.
- Shortcut di halaman ini: `N` adegan baru setelah yang terpilih, `D` duplikat, `↑/↓` pindah adegan, `⌘↵` buka konfirmasi biaya untuk aksi utama adegan (tidak pernah melewati dialog).
- Workspace (plan 07) tetap: semua latar, baju, episode, adegan milik workspace aktif.

### Bahan cerita
- **Latar**: grid kartu (gambar, nama, deskripsi singkat, dipakai di N adegan). Field: nama (wajib), deskripsi (dipakai di prompt, maks 300), gambar referensi (opsional, dari library).
- **Lemari baju** di halaman Karakter (bagian baru di kartu karakter) dan dari inspector: nama ("Kebaya merah"), deskripsi (masuk prompt), gambar opsional. Gambar bisa foto baju saja atau karakter yang sudah memakai baju itu (dibuat lewat Edit Foto).

## Desain backend

### Data (migrasi v9)
```
locations(id, workspace_id, name, description, image_id NULL, created_at, updated_at)
outfits(id, character_id, name, description, image_id NULL, created_at)          -- workspace ikut karakter
films + kolom: number INTEGER, synopsis TEXT                                      -- episode
scenes(id, film_id, position INTEGER, location_id NULL, time_of_day TEXT, camera TEXT,
       dialogue TEXT, extra_prompt TEXT, keyframe_image_id NULL, clip_id NULL, created_at, updated_at)
scene_cast(scene_id, character_id, outfit_id NULL, action TEXT, position INTEGER, PRIMARY KEY(scene_id, character_id))
images + kolom scene_id NULL; clips + kolom scene_id NULL                         -- take milik adegan
```
- Migrasi: tiap film lama → `number` urut `created_at`. Tiap id di `clip_ids` menjadi baris `scenes` dengan `clip_id` itu (duplikat tetap jadi adegan terpisah). `clip_ids` tidak dipakai lagi (kolom dibiarkan, tidak dihapus).
- Batas: 50 adegan per episode (sama dengan `MAX_SCENES`), 3 pemeran per adegan (batas input gambar, lihat di bawah).
- Hapus latar/baju: baris dihapus, referensi di adegan jadi NULL, gambar tetap di library. Hapus karakter: `scene_cast` miliknya ikut dihapus. Hapus klip/gambar (soft delete): `scenes.clip_id/keyframe_image_id` yang menunjuknya jadi NULL (menggantikan `detach_clip`).
- `Workspaces.delete` dan `Workspaces.jobs` ikut tabel baru. Salin karakter antar workspace ikut menyalin lemari bajunya (gambar baju disalin seperti gambar sheet).

### Modul baru `backend/app/scenes.py`
- `Scenes` (pola sama dengan `Films`): CRUD adegan, urut, duplikat, pemeran, latar, baju. Semua dibatasi `ws`.
- Fungsi murni `compose(scene_data) -> (input_entries, keyframe_prompt, video_prompt)`: **satu sumber kebenaran** untuk daftar gambar input dan prompt. Dipakai `/api/estimate` (kind baru `scene_keyframe`, `scene_video` dengan `scene_id`) dan generate. Pola sama dengan `Studio.plan_edit` di plan 06.
- Keyframe = `edit_image` dalam mode baru **compose** di `editprompt.py`:
  - Gambar 1 = gambar latar (bila ada), atau gambar sumber karakter pertama bila latar tanpa gambar.
  - Lalu per pemeran: gambar identitas (sheet terpenting saja) + gambar baju (bila ada).
  - Prompt berperan: "Image 1 is the LOCATION…; Image 2 is CHARACTER Rani…, dress her in the OUTFIT from image 3…; Rani is running to the rice field…, time: dusk, camera: …". Yang dipangkas bila melebihi batas model: sheet tambahan dulu, lalu gambar baju (diganti deskripsi teks), lalu ditolak dengan pesan jelas.
- Video = `create_clip(image_id=keyframe terpilih, prompt=video_prompt)` + `scene_id`. Prompt video = aksi tiap pemeran + kamera + waktu, tanpa deskripsi identitas yang panjang (gambar sudah membawanya).
- Render episode: daftar klip = `clip_id` tiap adegan urut `position`. Adegan tanpa video = peringatan `unplayable` (sama seperti sekarang). `rendered_ids` tetap dipakai untuk "perlu render ulang".

### API
```
GET/POST        /api/locations            PUT/DELETE /api/locations/{id}
GET/POST        /api/characters/{id}/outfits   PUT/DELETE /api/outfits/{id}
GET/POST        /api/films  (+number, synopsis)   GET /api/films/{id} → episode + adegan lengkap
POST            /api/films/{id}/scenes   {after_scene_id?, inherit=true}
PUT/DELETE      /api/scenes/{id}         (field + cast: [{character_id, outfit_id, action}])
POST            /api/scenes/{id}/duplicate
PUT             /api/films/{id}/scene-order   {scene_ids}
GET             /api/scenes/{id}/prompt  → pratinjau prompt + daftar gambar input (gratis)
POST            /api/scenes/{id}/keyframe   {model, aspect_ratio?, …, confirmed_cost}
POST            /api/scenes/{id}/video      {model, duration, …, confirmed_cost}
PUT             /api/scenes/{id}/takes      {keyframe_image_id?, clip_id?}   (pilih take)
```
`PUT /api/films/{id}` tidak lagi menerima `clip_ids` (urutan lewat `scene-order`).

## Desain frontend
- `pages/Storyboard.tsx` dipecah: `storyboard/EpisodeList.tsx`, `SceneBoard.tsx`, `ScriptView.tsx`, `SceneInspector.tsx`, `Timeline.tsx` (isi timeline sekarang), `StoryBible.tsx` (Latar).
- Lemari baju: bagian baru di `pages/Characters.tsx` + komponen `OutfitPicker` yang dipakai juga di inspector.
- Biaya: tombol keyframe/video memakai `useEstimate` + `useConfirmedRun` yang sudah ada (pintu tunggal panggilan berbayar). Pilihan model memakai katalog model + harga yang ada (plan 05 revisi 2).
- Simpan field teks dengan debounce (± 600 ms) + indikator "tersimpan". Gagal simpan = toast + nilai tidak hilang dari input.
- Polling klip adegan memakai `useClips()` yang ada. Kartu memperbarui status dari situ.

## Langkah kerja
0. **Spike compose** (berbayar, perlu persetujuan budget): 1 latar + 1 dan 2 karakter (dengan/tanpa gambar baju) di 2–3 model murah. Pertanyaan: identitas tetap? Baju mengikuti referensi? Latar dipertahankan? Dua karakter tidak tertukar? Hasil menentukan urutan gambar, batas pemeran, dan model bawaan. Usulan budget maksimal **$0.50**. Catat di `docs/implementation/08-...-spike.md`.
1. Migrasi v9 + `scenes.py` CRUD + latar + baju + migrasi film lama + tes.
2. `compose` + mode compose di `editprompt.py` + estimasi + endpoint keyframe/video/takes + tes (FakeOpenRouter).
3. Pembersihan: hapus aset/karakter/workspace, salin karakter + baju, `jobs`. Tes.
4. Frontend: daftar episode + Papan + inspector + take.
5. Frontend: tampilan Naskah, bahan cerita (Latar, Lemari baju), Timeline dipindah, shortcut.
6. Dokumen implementasi + daftar alur untuk diuji user.

## Kriteria selesai
- `make test` hijau, termasuk tes baru: migrasi film lama → adegan (urutan dan duplikat tetap), CRUD + batas ws (sweep id lintas workspace = 404), pewarisan adegan baru, `compose` (urutan gambar, pemangkasan, penolakan), estimasi = generate (jumlah gambar sama), keyframe/video menyimpan take dengan `scene_id`, hapus latar/baju/klip/karakter tidak merusak adegan, hapus workspace membersihkan tabel baru, render episode memakai video terpilih.
- `cd frontend && npm run build` hijau.
- Frontend diuji manual oleh user (daftar alur ditulis di dokumen implementasi).

## Pertanyaan terbuka
1. **AI penulis adegan?** Ketik sinopsis episode → LLM murah (lewat OpenRouter, ± $0.001 per episode) mengusulkan daftar adegan (latar, pemeran, aksi) yang bisa diedit. Usulan: plan terpisah setelah ini. Mau dimasukkan ke plan ini?
2. **Budget spike** compose maksimal $0.50: setuju?
3. **Batas 3 pemeran per adegan** (karena batas 5 gambar input di kebanyakan model): cukup untuk v1? Adegan ramai tetap bisa lewat deskripsi teks tanpa gambar.
4. Satu adegan = satu klip video utama. Kalau butuh beberapa shot (sudut kamera berbeda) dalam satu adegan, sementara dibuat sebagai adegan terpisah. Oke?

## Revisi 1: Edit Foto terpisah, baju = tampilan karakter, latar bisa dibuat dari teks
Asal: user "prompt edit foto ya buat edit foto aja nanti bisa di masukan ke dalam karakter jadi section untuk edit foto dan pilih karakter beda, sisanya coba pikirkan solusinya dulu".

Bagian ini menggantikan desain compose dan lemari baju di atas bila bertentangan.

1. **Edit Foto tidak diubah.** Prompt dan alur plan 06 tetap khusus Edit Foto. Storyboard tidak memanggil `build_prompt`. Yang ditambah di Edit Foto hanya tombol pada hasil: **"Simpan ke karakter…"** → pilih karakter → simpan sebagai **tampilan/baju** (beri nama, mis. "Kebaya merah") atau sebagai sudut sheet.
2. **Baju = tampilan karakter**, bukan foto baju lepas. Satu tampilan = satu gambar karakter yang **sudah memakai** baju itu (dibuat di Edit Foto, atau diunggah). Tabel `outfits(id, character_id, name, description, image_id NOT NULL)`. Tampilan bawaan = gambar sumber karakter.
   - Akibatnya, tiap pemeran cukup diwakili **satu** gambar. Risiko "foto baju membawa wajah orang lain" hilang, dan jumlah input turun.
3. **Bagian berbeda, tugas berbeda**: Edit Foto = membuat/menyunting gambar karakter. Karakter = identitas + lemari tampilan. Storyboard = memilih latar, pemeran + tampilan, dan aksi. Storyboard tidak pernah menyunting identitas.
4. **Latar selalu punya gambar.** Latar baru bisa dari library/unggah, atau **"Buat dari deskripsi"** (text-to-image: `/images` OpenRouter dengan `input_references` kosong; estimasi kind baru `location_image`, alur biaya sama). Keyframe hanya bisa dibuat bila latar adegan punya gambar. Bila tidak ada, tombolnya berbunyi "Buat/pilih gambar latar dulu". Masalah "tidak ada gambar dasar" (grill no. 2, 3) selesai di sini.
5. **Prompt adegan modul sendiri** `backend/app/sceneprompt.py` (murni, tanpa DB): `scene_inputs()` + `scene_prompt()` + `video_prompt()`. Urutan gambar: 1 = latar, 2..n = tampilan tiap pemeran (urut pemeran). Gambar sheet "front" ditambahkan per pemeran hanya bila masih muat dalam batas model. Maks input = 1 + 3 pemeran = 4 (≤ 5 di kebanyakan model).
6. **Dua cara menyusun keyframe**, dipilih di inspector, keduanya memakai modul yang sama:
   - **Sekaligus** (bawaan): 1 panggilan, semua pemeran masuk.
   - **Bertahap**: 1 panggilan per pemeran. Tiap panggilan = hasil sebelumnya sebagai gambar 1 + satu tampilan pemeran. Lebih mahal (N panggilan, terlihat di estimasi sebagai satu total), tapi tiap langkah hanya mengurus satu wajah. Gunanya saat "sekaligus" membuat karakter tertukar. Bila satu langkah gagal, langkah sebelumnya tetap tersimpan sebagai take antara, dan biaya yang sudah terpakai tercatat.
   - Spike menentukan mana yang jadi bawaan per model.
7. **Spike diperkecil**: (a) text-to-image latar di 2 model murah, (b) 1 pemeran, (c) 2 pemeran sekaligus vs bertahap. ± 10–12 panggilan model murah. Usulan budget maksimal **$0.30** (menunggu persetujuan).
8. Langkah kerja jadi: 0 spike → 1 data/CRUD/migrasi → 2 "Simpan ke karakter" di Edit Foto + lemari tampilan → 3 `sceneprompt` + latar dari teks + keyframe (sekaligus/bertahap) + video → 4 pembersihan → 5–6 frontend → 7 dokumen.

## Riwayat
- 2026-10-20: draft pertama.
- 2026-10-20: revisi setelah grill (`docs/grill/08-episode-scene-storyboard-grill.md`). Keputusan grill berlaku di atas isi plan bila bertentangan:
  - compose = fungsi terpisah di `editprompt.py`. `build_prompt` plan 06 tidak diubah.
  - Sumber keyframe: gambar latar → gambar baju → foto karakter, ditolak 422 bila tidak ada satu pun.
  - Tambahan kolom `films.aspect_ratio` (rasio episode, bawaan 16:9) dipakai semua adegan.
  - `POST /films/{id}/scenes` menerima `clip_id`. "Tambah ke storyboard" (`App.tsx`) dipindah ke endpoint ini. `clip_ids` di `PUT /films/{id}` → 422.
  - Take baru otomatis dipilih hanya bila pilihan sekarang kosong, gagal, atau terhapus.
  - `PUT /api/scenes/{id}` parsial. `scene-order` harus berisi himpunan adegan yang sama persis (409 bila tidak).
  - `delete_image` menolak gambar yang dipakai latar/baju. Take keyframe yang dihapus dikosongkan dari adegan.
  - Dialog hanya catatan, tidak dikirim ke AI. Batas panjang per field.
  - `Workspaces.jobs` tidak diubah (koreksi bagian "Data").
  - Nomor episode diedit manual, tanpa drag.
  - Pertanyaan terbuka 1, 3, 4 memakai usulan bawaan (user lanjut tanpa menjawab). Budget spike (no. 2) **belum disetujui**: compose menunggu angka dari user. Langkah 1 dan 3 (tanpa biaya) boleh jalan duluan.
- 2026-10-20: user "oke go" setelah spike: usulan di entri berikut **disetujui dan diimplementasi** (lihat Revisi 1 di `docs/implementation/08-episode-scene-storyboard-implementation.md`). Tambahan di luar plan awal atas permintaan user: **durasi rencana per adegan** (`scenes.planned_seconds`, total per episode, jadi durasi bawaan video) dan **daftar take** (`images.scene_id`/`clips.scene_id`, migrasi v10).
- 2026-10-20: spike dijalankan dengan budget $0,50 dari user, terpakai $0,2413 (`docs/implementation/08-episode-scene-storyboard-spike.md`). Usulan perubahan desain (menunggu persetujuan): mode "bertahap" dihapus dari v1 (tidak lebih baik, 2× biaya); keyframe satu panggilan "sekaligus" untuk 1-3 pemeran; model bawaan Seedream 5.0 flash; `films.aspect_ratio` dikirim eksplisit ke model (Seedream default 1:1); latar dari teks terbukti jalan di 3 model.
- 2026-10-20: Revisi 1 (bagian "Revisi 1" di atas): Edit Foto tetap terpisah + "Simpan ke karakter", baju = tampilan karakter berbasis gambar, latar dari teks, modul `sceneprompt.py`, mode sekaligus/bertahap, spike diperkecil ke usulan $0.30. Digrill di bagian "Grill revisi 1" dokumen grill.
