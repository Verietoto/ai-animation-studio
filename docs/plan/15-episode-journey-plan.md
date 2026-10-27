# 15 - Alur pembuatan episode per langkah (Episode Journey) (Plan)

- Status: draft, menunggu persetujuan
- Tanggal: 2026-10-26

## Tujuan
Permintaan user: alur UX pembuatan episode yang berjalan per langkah: (1) tentukan karakter yang muncul di episode ini, (2) latarnya, (3) tulis naskah yang bisa me-mention latar dan karakter, (4) langkah berikutnya: timeline, bisa manual atau dibantu AI, (5) bila timeline sudah ada, opsional membuat animasi kasar di three.js dulu, (6) baru ke animasi sesungguhnya.

Sekarang halaman Storyboard adalah kumpulan tab (Papan, Naskah per adegan, Timeline, Latar) tanpa urutan kerja. User harus tahu sendiri bahwa pemeran dipilih per adegan, latar dibuat di tab lain, dan blockout 3D ada di inspector adegan. Episode tidak punya daftar pemeran atau latar sendiri, dan tidak punya naskah utuh.

## Keadaan sekarang (dicek 2026-10-26)
- Episode = baris `films` (judul, nomor, sinopsis, rasio). Adegan (`scenes`) menyimpan latar, waktu, kamera, dialog, teks tambahan, pemeran (`scene_cast`: karakter, tampilan, aksi), keyframe, klip, `planned_seconds`, blockout/previs (plan 14).
- `Storyboard.tsx` punya tampilan: board, script (formulir per adegan), timeline (render akhir), locations. Inspector adegan memuat latar, pemeran, keyframe, video, previs 3D.
- Karakter dan latar adalah aset workspace (`characters`, `locations`), bukan per episode.
- Infrastruktur AI teks sudah ada dari plan 14: `OpenRouterClient.chat_json`, tabel `text_jobs` (masuk anggaran harian), alur estimasi → konfirmasi → `authorize`.
- Batas yang berlaku: maks 3 pemeran per adegan (batas input gambar model), maks 50 adegan per episode, durasi rencana adegan 1–120 dtk.

## Ruang lingkup
Alur lima langkah di atas satu episode, dengan penanda langkah (stepper) di bagian atas. Langkah tidak mengunci: user boleh loncat, dan episode lama dibuka di langkah yang sesuai datanya.

**Langkah 1 - Pemeran & latar.** Pilih karakter dan latar yang muncul di episode ini dari library workspace (daftar episode, lebih panjang dari batas 3 per adegan). Buat karakter atau latar baru dari sini (latar: nama, deskripsi, gambar opsional; karakter: tautan ke halaman Karakter). Menampilkan kesiapan tiap item: karakter tanpa lembar tampilan, latar tanpa gambar (diperlukan untuk keyframe).

**Langkah 2 - Naskah.** Editor teks utuh per episode dengan mention `@[Nama karakter]` dan `#[Nama latar]` (autocomplete saat mengetik `@` atau `#`, hanya dari pemeran/latar langkah 1; tampil berwarna). Mention yang tidak dikenal ditandai dengan tombol "tambahkan ke episode". Opsional: "Bantu tulis naskah" (AI menulis dari sinopsis + daftar pemeran/latar).

**Langkah 3 - Timeline.** Naskah menjadi daftar adegan, dua cara:
- Manual: papan adegan yang sudah ada (tambah, urut, atur latar/pemeran/aksi/durasi), kini dengan latar dan pemeran terbatas pada pilihan episode.
- Dibantu AI: "Pecah naskah jadi adegan" membaca naskah + pemeran + latar + rasio dan menghasilkan draf adegan (latar, waktu, kamera, pemeran + aksi, dialog, durasi). Draf ditinjau dulu, lalu ditambahkan atau menggantikan. Total durasi ditampilkan terhadap target episode.
- Penanda "naskah berubah sejak adegan dibuat" bila naskah diedit setelah dipecah.

**Langkah 4 - Previs 3D (opsional).** Daftar adegan dengan status blockout/previs masing-masing; buka editor plan 14 per adegan; "Susun semua dengan AI" (satu konfirmasi biaya untuk seluruh adegan yang belum punya susunan); tombol "Lewati langkah ini".

**Langkah 5 - Animasi.** Keyframe dan video per adegan (panel yang sudah ada), ditambah ringkasan produksi episode: berapa adegan punya keyframe/video, perkiraan biaya yang tersisa, dan aksi massal "Buat semua keyframe yang belum ada" / "Buat semua video yang belum ada" dengan satu konfirmasi total. Render episode akhir (timeline yang sudah ada) ada di langkah ini. Adegan yang punya previs menawarkan pemakaiannya sebagai referensi gerak (Tiru Gerakan).

Tidak termasuk:
- Impor naskah dari berkas, versi/riwayat naskah, kolaborasi.
- Pemeran berbeda per versi naskah, sub-episode/musim.
- Generate video massal tanpa konfirmasi biaya.
- Mengubah tab lama: tetap tersedia sebagai "Mode lanjutan" supaya tidak ada fungsi yang hilang.

## Desain / pendekatan
**Data (migrasi v12):**
- `film_characters(film_id, character_id, position)` dan `film_locations(film_id, location_id, position)`.
- `films.script TEXT` (maks 20.000 karakter), `films.script_split_hash TEXT` (hash naskah saat terakhir dipecah), `films.previs_skipped INTEGER`.
- `scenes.script_excerpt TEXT` (potongan naskah asal adegan, opsional, untuk ditampilkan di inspector).
- Isi awal (backfill) untuk episode lama: pemeran dan latar diambil dari adegan yang sudah memakainya.

**Backend:**
- Modul murni `script.py`: parser mention (`@[…]`, `#[…]`), pencocokan nama tanpa peduli huruf besar-kecil, daftar mention tak dikenal. Sintaks tunggal supaya frontend dan backend tidak menyimpang.
- `PUT /api/films/{id}` menerima `script`; `PUT /api/films/{id}/cast` menerima `{character_ids, location_ids}`. Validasi: milik workspace yang sama, tanpa duplikat, batas jumlah. Menghapus karakter/latar dari episode ditolak (409) bila masih dipakai adegan episode itu, atau diberi pilihan melepas dari adegan.
- AI (Haiku 5.5, lewat `chat_json` dan `text_jobs`): `kind` estimasi baru `episode_script` dan `episode_split`; `POST /api/films/{id}/script/draft` dan `POST /api/films/{id}/split` menghasilkan **draf** (tidak disimpan). `POST /api/films/{id}/split/apply` menerapkan draf: mode tambah atau ganti. Keluaran divalidasi ketat: latar dan karakter harus ada di daftar episode, maks 3 pemeran/adegan, maks 50 adegan, durasi 1–120 dtk, teks dipotong sesuai batas kolom.
- Mengganti nama karakter/latar menulis ulang mention di naskah episode-episode workspace itu, supaya mention tidak putus.
- Ringkasan kemajuan episode (untuk stepper) dihitung server dari data: pemeran/latar terisi, naskah terisi, jumlah adegan, jumlah adegan dengan blockout/previs, keyframe, video, siap render.

**Frontend:**
- Komponen `Journey` di `pages/Storyboard.tsx`: stepper (5 langkah, tanda selesai/opsional/perlu perhatian), tombol "Lanjut" yang menyebut apa yang kurang tanpa memblokir, pembuka otomatis di langkah yang sesuai (episode lama dengan adegan → langkah 3 atau 5).
- Berkas baru di `frontend/src/storyboard/journey/`: `StepCast.tsx`, `StepScript.tsx` (textarea + lapisan sorot mention + autocomplete), `StepTimeline.tsx` (membungkus papan dan inspector yang ada + panel AI), `StepPrevis.tsx`, `StepProduce.tsx`. Latar memakai `LocationsView` yang ada.
- Tab lama dipindah ke "Mode lanjutan" di langkah mana pun.

**Pengiriman bertahap** (tiap fase: grill singkat bila ada temuan baru, test, build, dokumen implementation):
- Fase A: migrasi, pemeran/latar episode, naskah dengan mention, stepper, timeline manual.
- Fase B: AI "bantu tulis naskah" dan "pecah naskah jadi adegan".
- Fase C: langkah previs dan produksi (aksi massal, ringkasan biaya, kemajuan).

## Risiko awal (bahan grill)
- Mention berbasis nama rapuh: ganti nama, nama ganda, nama dengan tanda baca. Mitigasi di atas (tulis ulang saat rename, nama unik per workspace dicek).
- Naskah dan adegan menyimpang: user mengedit adegan manual setelah dipecah, lalu memecah ulang dan menimpa kerja manual. Mode ganti harus melindungi adegan yang sudah punya keyframe/video.
- AI mengarang karakter/latar di luar daftar: ditolak/dibuang saat validasi, bukan menciptakan entitas baru.
- Biaya aksi massal: puluhan keyframe/video sekaligus. Satu konfirmasi total, tetap tunduk pada batas per job dan harian; berhenti di tengah bila batas tercapai dan melaporkan sisanya.
- Beban kognitif: lima langkah terasa wajib. Stepper tidak mengunci dan setiap langkah bisa dilewati.
- Episode lama tanpa pemeran/latar episode: backfill harus benar dan idempoten.
- Ukuran: ini fitur terbesar sejauh ini; fase dan batas jelas supaya tidak melebar.

## Langkah kerja
1. Grill plan ini (UX, data, AI, regresi mode lanjutan).
2. Fase A → B → C, masing-masing: backend + test, frontend + build, dokumen implementation (satu dokumen `15-episode-journey-implementation.md` dengan bagian per fase).
3. Daftar uji manual untuk user di akhir tiap fase.

## Kriteria selesai
- `make test` hijau dengan test baru; `npm run build` hijau.
- Episode baru bisa dibuat dari langkah 1 sampai render akhir tanpa membuka tab lama; episode lama tetap berfungsi tanpa kehilangan data.
- Pemecahan naskah oleh AI tidak pernah menghasilkan adegan dengan karakter/latar di luar episode, dan tidak menimpa adegan yang sudah punya hasil tanpa konfirmasi.
- Biaya AI dan aksi massal tercatat di anggaran harian dan lewat konfirmasi.

## Pertanyaan terbuka
1. Sintaks mention `@[Rani]` dan `#[Warung kopi]` dengan autocomplete: setuju? (Kurung siku dipilih supaya nama berspasi aman.)
2. Saat AI memecah naskah dan episode sudah punya adegan: bawaan "tambahkan di akhir", dan "ganti semua" hanya boleh bila tidak ada adegan yang sudah punya keyframe/video. Setuju?
3. Aksi massal produksi (langkah 5): satu konfirmasi untuk total, dijalankan berurutan, berhenti bila batas harian tercapai. Setuju, atau lebih suka per adegan saja?
4. Tab lama dipertahankan sebagai "Mode lanjutan". Setuju, atau stepper sepenuhnya menggantikan?
5. Model teks untuk naskah/pemecahan: Haiku 5.5 (murah, ± $0.01 per episode), bisa diganti lewat `.env`. Cukup?
6. Urutan pengerjaan fase A → B → C dengan persetujuan di antara fase: setuju?

## Riwayat
- 2026-10-26: draft awal.
- 2026-10-26: user: "oke grill". Bawaan pertanyaan terbuka dianggap disetujui (dikonfirmasi ulang di laporan). Setelah grill (rincian di grill 15):
  - Karakter belum bisa diganti nama (tidak ada endpoint); tulis ulang mention saat ganti nama hanya untuk latar di fase ini.
  - Nama pemeran/latar unik di dalam episode; nama baru tanpa `[`/`]`.
  - Hapus karakter/latar/workspace ikut membersihkan tabel episode baru.
  - Aksi massal dijalankan berurutan dari browser (keyframe sinkron dan lama), satu konfirmasi total, berhenti saat batas tercapai.
  - Pemecahan naskah: `max_tokens` 12.000, validasi ulang saat apply, id asing dibuang per pemeran.
  - Sorot mention di pratinjau, bukan di belakang textarea.
  - Karakter yang dipakai lewat Mode lanjutan otomatis masuk daftar episode.
- 2026-10-26: user: "oke langsung aja sampai fase c" (menyetujui fase A, B, dan C berurutan tanpa jeda persetujuan). Tambahan di fase C (usul saya, diterima): per adegan ada pilihan **"Buat video dari previs"** (Seedance reference: video previs + gambar pemeran/latar, hasil menjadi take adegan; hanya gaya kartun, butuh tunnel/S3), dan daftar referensi di Tiru Gerakan. Uji berbayar nyata hanya yang kecil (spike AI naskah/pemecahan, batas total $0.05); uji Seedance dengan previs asli tidak dijalankan agent (butuh previs dari browser dan batas biaya baru dari user).
