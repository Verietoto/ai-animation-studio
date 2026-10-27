# 08 - Storyboard per episode dan adegan (Grill)

Plan terkait: `docs/plan/08-episode-scene-storyboard-plan.md`

Keparahan: **T** tinggi, **S** sedang, **R** rendah. Temuan bertanda (kode) sudah dicek di repo.

Catatan: user membalas "lanjut grill" tanpa menjawab 4 pertanyaan terbuka plan. Grill ini memakai usulan bawaan plan (AI penulis = plan terpisah, maks 3 pemeran, 1 adegan = 1 video utama). **Budget spike tidak dianggap disetujui**: tidak ada panggilan berbayar sebelum user menyebut angka.

## Lubang pada plan
1. **(T) Prompt edit sekarang salah untuk adegan (kode).** `editprompt.build_prompt` selalu membuka dengan "Image 1 provides the character's identity, outfit, background and lighting". Di mode compose, gambar 1 adalah **latar**. Bila compose dibuat sebagai cabang di dalam `build_prompt`, perilaku plan 06 ikut berisiko berubah.
   - Mitigasi: fungsi terpisah `compose_inputs()` + `compose_prompt()` di `editprompt.py`, berbagi helper `_imgs`/`Entry` saja. `build_prompt`/`plan_inputs` tidak disentuh. Tes plan 06 harus lulus tanpa diubah.
2. **(T) Tidak ada gambar sumber sama sekali (kode).** Edit wajib punya gambar sumber (`_run_edit` membaca `source["path"]`), dan tidak ada text-to-image. Adegan dengan latar tanpa gambar dan tanpa pemeran tidak bisa dibuat keyframenya.
   - Mitigasi: urutan sumber = gambar latar → gambar baju pemeran pertama (bila foto karakter memakai baju) → gambar sumber karakter pertama. Bila tidak ada satu pun: tombol keyframe nonaktif dengan alasan "pilih gambar latar atau tambahkan karakter". Server mengembalikan 422 dengan pesan yang sama.
3. **(T) Gambar karakter membawa latarnya sendiri.** Bila sumber = foto karakter (latar tanpa gambar), model cenderung mempertahankan background foto itu, bukan latar yang dideskripsikan.
   - Mitigasi: prompt compose mengatakan eksplisit "replace the background with: <deskripsi latar>" pada kasus ini, dan "use only the person from image N, ignore its background" untuk gambar karakter lain. Diuji di spike (kasus "latar tanpa gambar").
4. **(T) Tombol "Tambah ke storyboard" ikut rusak (kode).** `App.tsx:131-132` memakai `api.updateFilm(film.id, { clip_ids: [...] })`. Plan menghapus `clip_ids` dari `PUT /api/films/{id}`.
   - Mitigasi: `POST /api/films/{id}/scenes` menerima `clip_id` opsional (adegan dari klip jadi; keyframe = `source_image_id` klip itu bila masih ada). `App.tsx` dipindah ke endpoint ini. `PUT` yang masih mengirim `clip_ids` → 422 dengan pesan jelas (bukan diabaikan diam-diam).
5. **(T) Take mana yang otomatis terpilih.** Bila video baru selalu menggantikan pilihan, take yang sudah bagus tertimpa job yang nanti gagal. Bila tidak pernah otomatis, adegan pertama tidak pernah punya video terpilih tanpa klik.
   - Mitigasi: take baru otomatis dipilih hanya bila pilihan sekarang kosong, gagal, atau sudah dihapus. Selain itu, take baru hanya muncul di daftar take dengan penanda "baru". Berlaku sama untuk keyframe.
6. **(T) Rasio aspek tidak konsisten antar adegan.** Tiap keyframe/video memilih rasio sendiri. Render episode lalu memberi bar hitam (`ASPECT_TOLERANCE` di `films.py`).
   - Mitigasi: kolom `films.aspect_ratio` (bawaan `16:9`) = rasio episode. Keyframe dan video adegan memakai rasio ini, dan di inspector rasio tidak bisa diubah per adegan (cukup diubah di episode). Model yang tidak mendukung rasio itu ditandai di pemilih model.
7. **(S) Autosave + PUT seluruh adegan = data hilang.** Debounce 600 ms yang mengirim seluruh objek adegan bisa menimpa field yang baru diubah di tab lain atau oleh request sebelumnya yang datang terlambat.
   - Mitigasi: `PUT /api/scenes/{id}` parsial (hanya field yang dikirim). `cast` dikirim utuh hanya saat daftar pemeran berubah. Respons yang datang untuk versi lama diabaikan (nomor urut request per adegan). Simpan langsung (tanpa menunggu debounce) saat pindah adegan, ganti halaman, dan `visibilitychange`.
8. **(S) Urutan adegan dari dua tab.** `scene-order` dengan daftar dari tab basi bisa menghilangkan adegan baru.
   - Mitigasi: server menolak (409) bila himpunan `scene_ids` tidak sama persis dengan adegan episode itu. UI memuat ulang lalu menampilkan pesan. Sisip/hapus/urut memberi nomor ulang `position` dalam satu `transaction()`.
9. **(S) Gambar latar/baju dihapus dari library (kode).** `delete_image` sudah menolak (409) gambar yang dipakai karakter. Gambar latar/baju belum dijaga, sehingga compose akan 404 di tengah generate.
   - Mitigasi: `delete_image` juga menolak gambar yang dipakai latar/baju ("gambar dipakai latar \"Sawah\""). Gambar yang hanya menjadi **take keyframe** boleh dihapus: `scenes.keyframe_image_id` yang menunjuknya dikosongkan. `compose` memeriksa semua id lewat `get_image(ws)` sebelum estimasi (pola `plan_edit`).
10. **(S) Hapus karakter (kode).** `delete_character` menghapus baris permanen. `scene_cast` dan `outfits` miliknya akan menjadi yatim.
    - Mitigasi: dihapus dalam satu transaksi bersama karakter. Bila karakter dipakai di adegan, dialog hapus di UI menyebut jumlah adegan yang terkena ("dipakai di 4 adegan, akan dilepas dari adegan itu").
11. **(S) `detach_clip` diganti (kode).** `delete_clip` memanggil `films.detach_clip` yang menolak saat film sedang dirender. Dengan adegan, klip dihapus → `scenes.clip_id` dikosongkan. Penolakan saat render tetap diperlukan.
    - Mitigasi: `detach_clip` membaca `scenes` (episode berstatus rendering + memakai klip itu → 409), lalu mengosongkan `clip_id`. Adegan tetap ada (naskahnya tidak hilang).
12. **(S) Panjang prompt.** Compose dengan 3 pemeran + deskripsi latar + baju + aksi + teks tambahan bisa melewati 4000 karakter (`edit_image` dan `create_clip` menolak).
    - Mitigasi: batas per field (deskripsi latar/baju 300, aksi 200, kamera 120, teks tambahan 500, dialog tidak masuk prompt). Maksimum terhitung < 4000. Tetap ada pemeriksaan prompt akhir dengan pesan "ringkas deskripsi".
13. **(S) Dialog.** Plan tidak jelas apakah dialog dikirim ke model video. Model dengan audio mungkin mencoba "mengucapkannya" dengan hasil acak, dan biayanya berbeda.
    - Mitigasi: v1 dialog **hanya catatan**, tidak masuk prompt. Label di UI: "Dialog/catatan (tidak dikirim ke AI)".
14. **(S) Pembersihan workspace dan salin karakter (kode).** `Workspaces.delete` menghapus baris per tabel di satu transaksi, dan `copy` menyalin `character_images`.
    - Mitigasi: `delete` ditambah `scenes`, `scene_cast`, `locations`, `outfits`. `copy` karakter ikut menyalin `outfits` + gambarnya. Tes hapus workspace memeriksa tidak ada baris yatim. `Workspaces.jobs` **tidak** perlu diubah (take video tetap baris `clips`). Bagian plan yang menyebut `jobs` dicoret.
15. **(R) Nomor episode.** Mengurut nomor dengan drag menambah UI tanpa banyak nilai.
    - Mitigasi: nomor bisa diedit (angka), episode baru = nomor terbesar + 1, daftar diurut nomor. Duplikat nomor tidak ditolak, cukup diberi peringatan kecil.
16. **(R) Take keyframe memenuhi Library.** Semua take masuk `images` sehingga Library ramai.
    - Mitigasi: Library menampilkan label "Ep 3 · Adegan 4" pada gambar/klip yang punya `scene_id` (dari respons server). Filter "sembunyikan take adegan" ditunda sampai benar terasa mengganggu.

## Risiko (dampak, kemungkinan, mitigasi)
- **Kualitas compose** (dampak tinggi, kemungkinan sedang): wajah berubah, baju tidak mengikuti, dua karakter tertukar. Mitigasi: spike sebelum kode compose. Bila 2 karakter gagal di semua model murah, batas v1 diturunkan ke 1 pemeran bergambar (pemeran lain lewat teks), dan ini diputuskan bersama user.
- **Biaya tak terduga** (tinggi, rendah): setiap tombol berbayar lewat `useConfirmedRun`. Estimasi `scene_keyframe` memakai daftar gambar dari `compose_inputs` yang sama dengan generate. Tes "estimasi = generate" seperti plan 06.
- **Halaman terlalu berat**: UI Storyboard bertambah dari 184 baris menjadi ±6 komponen. Mitigasi: dipecah per file sesuai plan dan tetap lazy-load seperti sekarang (`Suspense` di `App.tsx`).
- **Migrasi gagal setengah jalan**: migrasi v9 berjalan dalam satu commit di `_migrate` (pola v2–v8). Tes migrasi memakai DB v8 berisi film dengan klip duplikat dan klip yang sudah dihapus. Klip yang sudah dihapus tetap menjadi adegan tanpa video, naskah kosong.

## Edge case
- Episode kosong → Papan menampilkan satu kartu "+ adegan pertama". Render nonaktif.
- Adegan baru di episode kosong tidak punya pendahulu untuk diwarisi: semua field kosong.
- Pemeran tanpa baju terpilih → pakai gambar sumber karakter, dan prompt bilang "keep the outfit from the character image".
- Karakter yang sama dua kali di satu adegan → ditolak oleh PK, dan karakter itu tidak muncul lagi di dropdown.
- Episode sedang dirender → urut/hapus adegan dan pilih take ditolak (409). Mengedit teks naskah tetap boleh (tidak memengaruhi render).
- Pindah workspace di tengah autosave → simpan dipaksa sebelum remount (`key={wsId}`), dan request membawa header workspace lama dari `call()`.
- Model yang hanya menerima 1 input (tanpa referensi) → compose hanya bisa memakai gambar sumber. Pemeran lain lewat teks, dengan peringatan di inspector.

## Potensi bug
- `position` bentrok setelah sisip → selalu nomori ulang 0..n-1 dalam transaksi, jangan pernah `position + 1` sebagian.
- Kunci React kartu adegan memakai `scene.id` (bukan id klip seperti `toScenes` sekarang). `toScenes` dibuang.
- Status "video diproses" dihitung dari `useClips()`: klip adegan yang lebih lama dari 200 klip terbaru tidak ada di daftar itu. Server menyertakan status klip terpilih di respons episode, jadi tidak bergantung pada daftar klip.
- `scene_id` di `images`/`clips` harus ikut dikosongkan saat adegan dihapus. Kalau tidak, Library menampilkan label adegan yang sudah tidak ada.
- `rendered_ids` sekarang dibandingkan dengan `clip_ids`. Setelah migrasi, `stale` harus dibandingkan dengan daftar `clip_id` adegan, bukan kolom lama.

## Asumsi yang belum terbukti
- Model gambar murah bisa memakai gambar 1 sebagai latar sambil memasukkan karakter dari gambar lain (spike).
- Referensi baju (foto baju saja) diikuti tanpa menyalin wajah orang di foto itu (spike, mirip temuan "pose bocor ekspresi" di plan 06).
- Model video i2v mempertahankan 2–3 karakter dari keyframe selama klip. Belum diuji, dicatat sebagai risiko di dokumen implementasi.

## Keputusan setelah grilling (perubahan pada plan)
1. Compose = fungsi terpisah, `build_prompt` plan 06 tidak diubah (no. 1).
2. Urutan sumber latar → baju → karakter, tolak bila kosong (no. 2, 3).
3. `POST /films/{id}/scenes` menerima `clip_id`, dan `App.tsx` "Tambah ke storyboard" dipindah ke sana. `clip_ids` di PUT → 422 (no. 4).
4. Aturan auto-pilih take (no. 5).
5. `films.aspect_ratio` sebagai rasio episode (no. 6).
6. PUT adegan parsial, simpan paksa saat pindah, `scene-order` harus himpunan sama (no. 7, 8).
7. `delete_image` menjaga gambar latar/baju, take keyframe dikosongkan (no. 9).
8. Hapus karakter/klip/adegan membersihkan tabel adegan dalam transaksi (no. 10, 11, potensi bug).
9. Batas panjang field, dialog tidak dikirim ke AI (no. 12, 13).
10. `Workspaces.jobs` tidak diubah, `delete`/`copy` diubah (no. 14).
11. Nomor episode diedit manual, tanpa drag (no. 15).
12. Spike menunggu angka budget dari user. Tanpa spike, langkah 1 (data + CRUD + UI naskah) tetap bisa dikerjakan karena tidak berbayar. Compose dikerjakan setelah spike.

## Grill revisi 1 (Edit Foto terpisah, tampilan karakter, latar dari teks)
Revisi 1 plan menyelesaikan no. 1 (Edit Foto tidak disentuh sama sekali), no. 2 dan 3 (latar selalu punya gambar), serta risiko "foto baju membawa wajah". Lubang barunya:

17. **(T) Text-to-image belum terbukti (kode).** `openrouter.edit_image` selalu mengirim `input_references`. Belum dicek apakah model menerima daftar kosong, dan apakah estimator menerima `n_inputs=0`.
    - Mitigasi: spike (a). Fungsi klien `generate_image` terpisah yang tidak mengirim `input_references` sama sekali bila kosong. Pemilih model "Buat latar" hanya menampilkan model yang lolos (daftar dari hasil spike, disimpan di kode sebagai daftar kecil yang terlihat, bukan tebakan). Tes estimator untuk 0 input.
18. **(S) Tampilan wajib bergambar terlalu kaku.** User yang hanya ingin menulis "memakai jas hujan kuning" terpaksa membuat gambar dulu di Edit Foto.
    - Mitigasi: `image_id` boleh kosong **bila** `description` diisi. Pemeran dengan tampilan teks memakai gambar sumber karakter + kalimat "change the outfit to: …". UI memberi label "teks saja, kurang konsisten antar adegan" dan tombol pintas "Buat gambar tampilan di Edit Foto". Koreksi atas `image_id NOT NULL` di revisi 1.
19. **(S) Gambar tampilan membawa latarnya sendiri.** Foto karakter dari Edit Foto punya background yang bisa ikut tercampur ke latar.
    - Mitigasi: prompt adegan menyebut "use only the person from image N; ignore its background". Diuji di spike (b). Bila tetap bocor, opsi berikutnya (bukan v1): potong latar otomatis.
20. **(T) Mode bertahap menahan kunci server lama (kode).** `edit_image` memegang `self._lock` selama panggilan ke OpenRouter. Tiga langkah berurutan = puluhan detik semua request lain menunggu.
    - Mitigasi: total estimasi dikonfirmasi sekali di awal (`confirmed_cost` = jumlah N langkah). Lalu tiap langkah: `authorize` + kirim di bawah kunci seperti edit biasa, dan kunci dilepas di antara langkah. Bila anggaran harian habis di tengah, proses berhenti. Hasil sampai langkah terakhir tetap tersimpan sebagai take antara dan pesan menyebut langkah yang tidak jalan. Tiap langkah dicatat sebagai baris `images` sendiri dengan biaya dan estimasinya, jadi batas harian tetap akurat.
21. **(S) Bertahap butuh urutan pemeran yang stabil.** Hasil langkah 2 bisa mengubah wajah pemeran dari langkah 1.
    - Mitigasi: tiap langkah setelah yang pertama juga mengirim tampilan pemeran sebelumnya bila masih muat dalam batas input, dengan peran "keep this person unchanged". Diuji di spike (c). Bila tetap berubah, bertahap tidak dijadikan bawaan.
22. **(S) "Simpan ke karakter" dari Edit Foto.** Gambar bisa milik workspace lain (tab lain) atau sudah dihapus, dan karakter bisa sudah dihapus.
    - Mitigasi: endpoint baru `POST /api/characters/{id}/outfits {image_id, name}` memakai `get_image(ws)` + `get_character(ws)` (404 lintas workspace, masuk tes sweep plan 07). Jalur sudut sheet memakai `add_character_image` yang sudah ada.
23. **(R) Identitas tampilan sudah melenceng sejak Edit Foto.** Storyboard tidak bisa memperbaikinya.
    - Mitigasi: tidak dicegah. Lemari tampilan menampilkan gambar tampilan di samping gambar sumber supaya user bisa membandingkan sebelum memakainya.

### Keputusan tambahan
13. `generate_image` terpisah untuk latar. Model hanya dari daftar yang lolos spike (no. 17).
14. Tampilan boleh teks saja dengan label "kurang konsisten" (no. 18).
15. Bertahap: konfirmasi sekali, kunci per langkah, berhenti rapi bila anggaran habis (no. 20).
16. Spike (usulan maks $0.30) mencakup: latar dari teks, kebocoran background tampilan, sekaligus vs bertahap dengan 2 pemeran. **Masih menunggu persetujuan budget dari user.**

## Riwayat
- 2026-10-20: grill pertama.
- 2026-10-20: grill revisi 1 (no. 17–23, keputusan 13–16).
