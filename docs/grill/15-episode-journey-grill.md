# 15 - Alur pembuatan episode per langkah (Episode Journey) (Grill)

Plan terkait: `docs/plan/15-episode-journey-plan.md`
Tanggal: 2026-10-26. Sumber:
- Kode: `main.py` (route karakter/latar, `FilmUpdateIn`), `service.py` (`create_character`, `delete_character`), `scenes.py` (`_check_cast`, `add`, `delete_location`, `_loc_values`, `keyframe`), `workspaces.py` (hapus permanen), `films.py`.
- DB lokal dibaca hanya-baca: jumlah karakter/latar dan nama yang memakai `[`/`]`.

## Temuan yang mengubah plan
1. **Karakter tidak bisa diganti nama.** Tidak ada `PUT /api/characters/{id}`; hanya latar yang punya `PUT /api/locations/{id}` (`update_location`). "Tulis ulang mention saat rename" di plan hanya relevan untuk latar sekarang, dan untuk karakter bila nanti endpoint ganti nama ditambahkan.
2. **Nama tidak unik.** Tidak ada batasan unik pada `characters.name` maupun `locations.name`. Dua "Rani" di satu workspace membuat `@[Rani]` ambigu.
3. **Penghapusan tidak tahu tabel baru.** `delete_character` menghapus `scene_cast`, `outfits`, `character_images`; `delete_location` mengosongkan `scenes.location_id`; hapus workspace permanen (`workspaces.py`) menghapus daftar tabel tetap. Ketiganya harus ikut membersihkan `film_characters` / `film_locations`, kalau tidak episode menunjuk entitas yang sudah tidak ada.
4. **Keyframe dibuat sinkron.** `Scenes.keyframe` memanggil model gambar di dalam permintaan HTTP (puluhan detik per adegan, di bawah `_lock`). Aksi massal "buat semua keyframe" dalam satu permintaan server akan melewati batas waktu dan menahan `_lock` lama. Video berbeda: submit cepat, lalu dipoll.
5. **Pemecahan naskah bisa melebihi batas token keluaran.** 50 adegan × ±150 token ≈ 7.500 token, di atas `max_tokens` 6000 yang dipakai blockout.
6. **Pemeran adegan bisa diisi lewat Mode lanjutan** dengan karakter di luar daftar episode (`_check_cast` hanya memeriksa workspace).

## Lubang pada plan
1. Draf pecahan naskah disimpan di browser lalu dikirim ke `split/apply`; pemeran/latar episode bisa berubah di antara dua langkah itu. Server harus memvalidasi ulang saat apply, bukan percaya draf.
2. Tanda "naskah berubah" butuh definisi: hash naskah saat apply dibandingkan dengan naskah sekarang. Mengubah adegan manual tidak boleh memicu tanda ini.
3. Sorot mention di textarea: teknik lapisan cermin di belakang textarea rentan meleset (font, wrap, scroll). Belum dibuktikan.
4. Batas 3 pemeran per adegan vs naskah yang menyebut 5 tokoh di satu momen: AI harus memecah atau memilih; plan belum menyebut perilakunya.
5. Episode lama: backfill pemeran/latar dari adegan; cukup dari `scene_cast.character_id` dan `scenes.location_id`.
6. Aksi massal memakai model dan parameter tunggal (model keyframe, model video, durasi); plan belum menyebut sumbernya.

## Risiko
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| Mention ambigu (nama ganda) | Adegan memakai tokoh salah | Sedang | Di dalam satu episode nama pemeran/latar harus unik (tanpa beda huruf besar-kecil); menambah yang bernama sama ditolak dengan pesan "ganti nama dulu". |
| Nama memuat `[`/`]` | Mention putus | Rendah (0 di DB lokal) | Nama baru karakter/latar menolak `[` dan `]`; yang lama ditandai tidak bisa di-mention. |
| Entitas terhapus tetap di episode | Data basi, error | Pasti (bila tidak ditangani) | `delete_character`, `delete_location`, dan hapus workspace ikut membersihkan tabel baru. Test untuk ketiganya. |
| Aksi massal keyframe macet | Request timeout, `_lock` tertahan | Pasti di satu request | Dijalankan berurutan oleh browser: satu konfirmasi total, lalu satu permintaan per adegan dengan estimasinya sendiri; server tetap `authorize` tiap job. Berhenti bila 402/409 dan melaporkan sisanya. Menutup tab menghentikan sisa batch (dicatat). |
| AI menimpa kerja manual | Kehilangan teks adegan | Sedang | Bawaan "tambah di akhir"; "ganti semua" hanya bila tidak ada adegan dengan keyframe/video/blockout, dan tetap minta konfirmasi. |
| AI mengarang tokoh/latar | Adegan rusak | Sedang | AI menerima id; keluaran dengan id di luar daftar dibuang per pemeran (adegan tetap) dan dilaporkan sebagai peringatan. |
| Keluaran AI terpotong (batas token) | JSON rusak, biaya terbuang | Sedang | `max_tokens` 12.000 untuk pemecahan (≈ $0.006 di Haiku 5.5); naskah > 20.000 karakter ditolak sebelum biaya. JSON rusak → 502, biaya tetap tercatat (pola plan 14). |
| Sorot mention meleset | Tampilan membingungkan | Sedang | Sorot di pratinjau di bawah editor (bukan lapisan di belakang textarea); autocomplete tetap di textarea. |

## Edge case
- Episode tanpa pemeran: langkah 2–3 tetap bisa; AI pemecah membuat adegan tanpa pemeran.
- Mention tokoh yang ada di workspace tapi belum di episode: ditandai, tombol "tambahkan ke episode".
- Mengeluarkan karakter dari episode saat dipakai adegan: 409 dengan daftar nomor adegan; opsi "lepas dari adegan itu juga".
- Naskah kosong: "Pecah naskah" nonaktif.
- Lebih dari 50 adegan hasil AI: dipotong 50 dengan peringatan.
- Durasi adegan AI di luar 1–120: dipaksa ke rentang.
- Lebih dari 3 pemeran disebut di satu adegan: prompt meminta maks 3 dan memecah adegan; sisanya dibuang dengan peringatan.
- Film sedang dirender: semua perubahan struktur (cast, apply, aksi massal) ditolak oleh `_editable`.
- Karakter lewat Mode lanjutan di luar daftar episode: otomatis ditambahkan ke daftar episode saat adegan disimpan (bukan ditolak), supaya data tetap konsisten tanpa memblokir alur lama.

## Potensi bug
1. Backfill v12 dijalankan dua kali: pakai `INSERT OR IGNORE` dengan primary key `(film_id, character_id)`.
2. Urutan pemeran episode (`position`) setelah hapus/tambah: dinomori ulang di satu transaksi.
3. `split/apply` menambah adegan melewati batas 50: dicek sebelum menulis apa pun.
4. Mention dengan spasi dan huruf besar-kecil: pencocokan `casefold()` di Python, `toLocaleLowerCase()` di TS; nama dengan huruf non-Latin diuji.
5. Ganti nama latar menulis ulang naskah: hanya `#[Nama lama]` persis (tanpa beda huruf besar-kecil), tidak menyentuh teks biasa yang kebetulan sama.

## Asumsi yang belum terbukti
- Haiku 5.5 bisa memecah naskah 10–30 adegan dengan id yang benar. Diuji dengan spike kecil di fase B (< $0.02, butuh persetujuan).
- Lima langkah tidak terasa berat. Hanya bisa dinilai user lewat uji manual.

## Keputusan setelah grilling (perubahan pada plan)
- Nama pemeran dan latar unik di dalam satu episode; nama baru tidak boleh memuat `[`/`]`.
- Ganti nama dengan tulis ulang mention: latar sekarang. Ganti nama karakter **tidak termasuk** fase ini (belum ada endpoint-nya); bisa jadi tambahan.
- Hapus karakter/latar/workspace membersihkan `film_characters`/`film_locations`.
- Aksi massal dijalankan berurutan oleh browser (satu konfirmasi total, satu request per adegan), bukan satu request server. Model dan parameter diambil dari pilihan di panel produksi (bawaan: model keyframe/video yang sama dengan panel adegan; durasi dari `planned_seconds`, dibulatkan ke yang didukung).
- `split/apply` memvalidasi ulang draf terhadap daftar episode saat itu; id di luar daftar dibuang per pemeran dengan peringatan.
- Pemecahan memakai `max_tokens` 12.000; naskah maks 20.000 karakter.
- Sorot mention ditampilkan di pratinjau, bukan lapisan di belakang textarea.
- Karakter yang ditambahkan ke adegan lewat Mode lanjutan otomatis masuk daftar episode.
- Pertanyaan terbuka plan dijawab user dengan "oke grill"; saya anggap **bawaan di plan disetujui** (sintaks `@[…]`/`#[…]`, tambah-vs-ganti, satu konfirmasi total, Mode lanjutan dipertahankan, Haiku 5.5, fase A → B → C dengan persetujuan antar fase). Dikonfirmasi ulang di laporan.

## Riwayat
- 2026-10-26: grill awal.
