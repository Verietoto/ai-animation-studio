# 14 - Adegan mentah (blockout 3D) dengan three.js untuk Storyboard (Plan)

- Status: draft, menunggu persetujuan
- Tanggal: 2026-10-26

## Tujuan
Permintaan user: "okay aku butuh plan baru untuk generate scen mentah dengan three.js untuk storyboard".

Tafsiran saya (dikonfirmasi di pertanyaan terbuka): per adegan Storyboard, user menyusun **blockout 3D kasar** di browser: lantai/dinding/kotak sebagai properti, manekin untuk tiap pemeran, dan kamera (posisi, arah, lensa). Hasil render-nya:
1. jadi gambar pratinjau komposisi adegan (gratis, tanpa AI), dan
2. bisa dipakai sebagai **panduan komposisi** saat membuat keyframe AI, supaya sudut kamera dan posisi tokoh mengikuti susunan user, bukan tebakan model dari teks "Camera: …".

## Keadaan sekarang
- Keyframe adegan (`scenes.keyframe_plan` / `keyframe`, plan 08): satu panggilan edit gambar. Gambar 1 = latar, gambar 2..n = tampilan pemeran (maks 3), prompt dari `sceneprompt.keyframe_prompt`. Komposisi hanya dari teks `camera` dan aksi.
- Adegan menyimpan `location_id`, `time_of_day`, `camera`, `dialogue`, `extra_prompt`, `keyframe_image_id`, `clip_id`, pemeran di `scene_cast` (karakter, tampilan, aksi, urutan).
- Preseden: sketsa pose di Edit Foto (`editprompt.make_pose_sketch`) sudah memakai gambar panduan bentuk yang dikirim ke model edit gambar.
- `three` belum terpasang. Halaman Storyboard sudah di-lazy-load.

## Ruang lingkup
Termasuk:
- **Editor blockout** (frontend, three.js) di inspector adegan, dibuka sebagai panel/modal "Susun adegan 3D":
  - Lantai dengan grid; properti primitif: kotak, silinder, bidang (dinding), dengan geser/putar/skala (TransformControls).
  - Satu manekin per pemeran adegan (otomatis dari `scene_cast`), berwarna berbeda dan berlabel nama. Pose preset: berdiri, duduk, berjalan, berbaring (dari primitif, bukan rig tulang). Arah hadap bisa diputar.
  - Kamera: posisi + target, lensa (mm → FOV), rasio mengikuti rasio film. Preset cepat dari teks kamera adegan (wide / medium / close-up / dari atas / dari bawah) sebagai titik awal.
  - Tampilan "lihat dari kamera" vs "kamera bebas" (OrbitControls) untuk menyusun.
- **"Generate" susunan awal otomatis (gratis, deterministik):** dari data adegan yang ada: manekin pemeran dijejer di depan kamera, kamera diatur dari preset yang cocok dengan teks `camera`. User lalu merapikan.
- **Simpan:**
  - Susunan disimpan sebagai JSON di kolom baru `scenes.blockout` (migrasi `user_version` 11), divalidasi server (ukuran, jumlah objek, angka finite).
  - Render dari sudut kamera diunggah sebagai gambar `kind = "blockout"` dan ditunjuk dari `scenes.blockout_image_id`.
- **Keyframe dengan panduan:** opsi "Pakai susunan 3D sebagai panduan komposisi" di panel keyframe. Bila aktif, render blockout menjadi gambar input terakhir, dan prompt menambahkan peran gambar itu ("rough layout: follow camera angle, framing and positions; ignore its grey look"). Estimasi biaya ikut menghitung input tambahan lewat `keyframe_plan` yang sama.
- Kartu adegan menampilkan render blockout bila belum ada keyframe.

Tidak termasuk (usul tahap berikutnya):
- Animasi kamera / previs video dari three.js.
- Pose manekin per sendi (rig), impor model 3D (GLB), tekstur.
- Susunan dibuat AI dari naskah (LLM menghasilkan JSON), lihat pertanyaan terbuka 2.
- Blockout untuk Gambar → Video atau Tiru Gerakan.

## Desain / pendekatan
- **Frontend:**
  - `three` (versi pasti, sudah ≥ 2 minggu) + `@types/three`; OrbitControls/TransformControls dari `three/examples/jsm`.
  - File baru `frontend/src/storyboard/Blockout.tsx` di-import dinamis supaya three.js hanya dimuat saat editor dibuka.
  - Susunan = data murni `{version, camera:{pos,target,mm}, actors:[{character_id,pos,rot,pose}], props:[{type,pos,rot,scale,color}]}`; scene three dibangun ulang dari data ini. Satu fungsi `buildScene(layout)` dipakai editor dan render.
  - Render: `WebGLRenderer` offscreen ukuran sesuai rasio film (sisi panjang ±1280), `toBlob` → `POST /api/images` (endpoint unggah yang ada) lalu `PUT` adegan.
- **Backend:**
  - Migrasi v11: `scenes.blockout TEXT` dan `scenes.blockout_image_id TEXT`.
  - `SCENE_FIELDS` + validasi di `Scenes.update`: JSON ≤ 64 KB, ≤ 50 properti, aktor hanya karakter yang ada di `scene_cast`, angka finite dalam batas wajar.
  - `kind = "blockout"` untuk gambar: diperlakukan seperti gambar lain (Library, hapus lunak, workspace). `delete_image` mengosongkan `scenes.blockout_image_id` seperti keyframe.
  - `keyframe_plan(…, use_blockout=False)`: bila aktif dan ada render, render ditambahkan sebagai input terakhir; `sceneprompt.keyframe_prompt` menambah peran gambar layout. Batas input model tetap diperiksa `_validate_image_params` (1 latar + 3 pemeran + 1 layout = 5).
  - Pengunci: adegan dalam film yang sedang dirender tetap tidak bisa diubah (`_editable`).

## Risiko awal (bahan grill)
- **Belum terbukti model edit gambar mau mengikuti render abu-abu sebagai komposisi** tanpa ikut menyalin tampilan abu-abunya. Perlu spike berbayar kecil (perkiraan 4-6 gambar, ≤ $0.20) sebelum fitur keyframe-dengan-panduan dianggap layak.
- Input ke-5 melewati batas sebagian model; model dengan batas lebih kecil harus menolak dengan pesan jelas, bukan memotong diam-diam.
- Ukuran bundel: three.js ±600 KB; harus lazy-load.
- WebGL tidak tersedia (browser/GPU tertentu): editor menampilkan pesan, Storyboard lain tetap jalan.
- Susunan basi: pemeran dihapus dari adegan setelah blockout dibuat.
- Pengujian 3D di browser dilakukan user (aturan proyek); logika data (validasi, build layout awal) dibuat murni supaya bisa dites tanpa browser.

## Langkah kerja
1. Grill plan ini.
2. Spike berbayar (setelah disetujui user, dengan batas biaya): 2-3 adegan, keyframe tanpa vs dengan render blockout; dinilai komposisi dan apakah tampilan abu-abu bocor.
3. Backend: migrasi, validasi blockout, `kind = "blockout"`, `keyframe_plan` + prompt, test.
4. Frontend: editor, susunan awal otomatis, render + unggah, opsi di panel keyframe, kartu adegan.
5. Dokumen implementation 14 dan daftar uji manual untuk user.

## Kriteria selesai
- `make test` hijau dengan test baru; `npm run build` hijau; three.js tidak ada di bundel utama.
- Susunan tersimpan dan terbuka lagi sama persis; render tersimpan sebagai gambar adegan.
- Keyframe dengan panduan terbukti di spike mengikuti komposisi lebih baik daripada tanpa panduan (dinilai user), atau fitur panduan ditunda bila tidak.

## Pertanyaan terbuka
1. Tafsiran saya benar? "Scene mentah" = blockout 3D kasar (manekin + properti + kamera) yang dirender jadi gambar panduan untuk keyframe. Atau maksudmu lain (mis. previs video bergerak dari three.js)?
2. "Generate"-nya cukup susunan awal otomatis dari data adegan (gratis), atau mau AI menyusun dari naskah (LLM menulis posisi tokoh dan kamera; biaya kecil per adegan)?
3. Pose manekin cukup preset (berdiri, duduk, berjalan, berbaring), atau perlu pose per sendi?
4. Boleh spike berbayar untuk menguji keyframe dengan panduan, batas $0.20?

## Riwayat
- 2026-10-26: draft awal.
- 2026-10-26: **Revisi 1**, jawaban user atas 4 pertanyaan terbuka: "previs video bergerak tapi ga detail aja, AI yg susun, pose per sendi, boleh". Bagian di atas yang bertentangan dengan revisi ini (gambar diam saja, susunan awal deterministik, pose preset saja, pose per sendi di luar ruang lingkup) **digantikan** oleh rincian di bawah.

### Revisi 1: previs bergerak, disusun AI, pose per sendi
**Hasil utama** sekarang **video previs kasar** per adegan (manekin abu-abu/berwarna, properti primitif, kamera bergerak), sepanjang `planned_seconds` adegan (maks 15 dtk). Render diam (frame pertama) tetap dibuat untuk kartu adegan dan panduan keyframe.

**Data susunan** (`scenes.blockout`, JSON, `version: 1`), semua waktu dalam detik:
- `duration`, `camera.keys: [{t, pos, target, mm}]`.
- `actors: [{character_id, keys: [{t, pos, facing, pose: {sendi: [x, y, z] derajat}}]}]`.
- `props: [{type: box|cylinder|plane, pos, rot, scale, color}]` (statis).
- Antar-key: posisi linear, rotasi slerp. Bila aktor berpindah posisi tanpa key pose di antaranya, siklus jalan prosedural ditambahkan otomatis (supaya AI tidak perlu menulis setiap langkah).

**Manekin dengan sendi:** hierarki `Object3D` dari primitif: panggul (akar), perut, dada, leher, kepala, bahu-siku-pergelangan kiri/kanan, pinggul-lutut-pergelangan kaki kiri/kanan (15 sendi). Batas putar per sendi (mis. lutut hanya menekuk ke belakang) diterapkan saat memuat data, supaya pose dari AI tidak patah. Pustaka pose (berdiri, duduk, jalan, lari, menunjuk, melambai, berbaring) jadi titik awal; AI boleh memakai nama pose plus penyesuaian sendi.

**AI menyusun** (berbayar, kecil):
- Endpoint `POST /api/scenes/{id}/blockout/generate`. Server mengirim konteks adegan (nama/deskripsi latar, pemeran + deskripsi + aksi, teks kamera, dialog, `planned_seconds`, rasio film) ke model teks lewat OpenRouter chat completions, meminta JSON sesuai skema di atas.
- `openrouter.py` belum punya panggilan model teks: method baru.
- Hasil divalidasi dan dipangkas server (jumlah key, batas angka, `character_id` hanya pemeran adegan). JSON yang rusak → error jelas, bukan susunan setengah.
- Lewat alur biaya plan 04: estimasi dari panjang prompt × harga model, dialog konfirmasi, batas per job dan harian. Perkiraan < $0.01 per adegan; model dipilih di grill dari katalog.
- Hasil tidak langsung menimpa susunan yang ada: editor membukanya sebagai draf; user menyimpan atau membuang.

**Editor (tidak detail):** viewport three.js, timeline dengan scrub dan putar, tambah/hapus key di waktu sekarang untuk kamera atau aktor, pilih sendi lalu putar dengan gizmo. Tidak ada kurva easing, tidak ada multi-pilih.

**Render video previs:**
- Di browser: tiap frame digambar pada waktu tetap (24 fps) ke canvas, direkam dengan `MediaRecorder` (WebM), lalu diunggah.
- Server mentranskode ke MP4 dengan ffmpeg (sudah dipakai `media.py`) dan menyimpannya sebagai baris `refs` (video referensi yang sudah ada), ditunjuk dari `scenes.previs_ref_id`. Ditambah `scenes.blockout_image_id` untuk frame pertama.
- Jadi previs langsung bisa dipilih sebagai **video referensi di Tiru Gerakan**. Manekin tidak foto-realistik, jadi mode "Animasikan gambar" (Seedance reference) seharusnya tidak kena moderasi orang nyata. Alur ini yang diuji di spike. Unggahan referensi ke model tetap butuh hosting publik (S3/R2 atau tunnel, plan 10).

**Spike berbayar** (disetujui user, batas **$0.20**):
1. AI menyusun 2 adegan (< $0.02).
2. Satu previs 3-5 dtk dipakai di Seedance reference bersama gambar karakter; dinilai apakah gerak dan komposisi mengikuti previs. Biaya pasti dihitung dari estimasi sebelum dikirim; bila estimasi melebihi sisa batas, langkah ini tidak dijalankan dan dilaporkan.
3. Bila sisa cukup: keyframe dengan vs tanpa render blockout sebagai panduan.

**Migrasi:** `user_version` 11 menambah `scenes.blockout`, `scenes.blockout_image_id`, `scenes.previs_ref_id`.

**Tetap tidak termasuk:** impor GLB/tekstur, easing, fisika, suara, previs yang langsung dijadikan klip di film tanpa lewat model video.

**Pertanyaan terbuka setelah revisi:** tidak ada yang menghalangi grill. Model teks untuk penyusun dipilih di grill (murah, mendukung keluaran JSON).
- 2026-10-26: user menyetujui revisi 1 ("ok"). Setelah grill (rincian di grill 14):
  - Model teks Haiku 5.5; tabel `text_jobs` supaya biayanya masuk `committed_today`.
  - Previs 1280×720 / 720×1280 (Seedance minimal 854×480); previs > 10 dtk harus dipotong sebelum jadi referensi.
  - Previs lama dibersihkan saat render ulang; batas sendi hanya di frontend.
  - Urutan: spike AI penyusun → backend + editor → user merender satu previs → satu uji Seedance Mini 480p 4 dtk ($0.177). Perbandingan keyframe dengan panduan tidak muat di batas $0.20.
