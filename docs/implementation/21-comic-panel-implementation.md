# 21 - Panel komik (Implementasi)

- Tanggal: 2026-10-27

## Yang dibangun
Backend:
- `db.py` migrasi **v20**: tabel `comic_panels` (lewat SCHEMA) + kolom `images.panel_id` (take panel). Asersi versi di tes dinaikkan ke 20.
- `comic_prompt.py` (murni): gaya (project/manga/western/webtoon), shot, sudut, gaya visual proyek, deskripsi, penomoran gambar (latar bergambar dulu, lalu karakter bergambar), aturan tetap "no text, no lettering, no speech bubbles". Teks balon tidak pernah masuk prompt.
- `comic.py`: CRUD + validasi (enum, maks 4 karakter berbeda, latar milik proyek, ≤ 20 balon, teks 1-300, balon di dalam panel, id balon unik, `image_id` harus take panel ini); `plan()` satu sumber untuk pratinjau, estimasi, dan generate; generate di bawah `Studio._lock`, edit-image bila ada gambar input, teks-ke-gambar bila tidak; take baru langsung dipakai. Referensi basi (karakter/latar/gambar dihapus) dibersihkan saat dibaca.
- `main.py`: `GET/POST /api/comic-panels`, `GET/PUT/DELETE /api/comic-panels/{id}`, `GET /api/comic-panels/{id}/preview?model=`, `POST /api/comic-panels/{id}/generate`; estimasi kind `comic_panel` (`panel_id`). `BubbleIn` dibatasi Pydantic (0..1, tanpa NaN, field asing ditolak).
- `workspaces.py`: hapus proyek ikut menghapus panelnya.

Frontend:
- Halaman **Komik** di sidebar (`pages/Comic.tsx`, dimuat lazy): tab panel, kanvas dengan balon yang bisa digeser/diubah ukuran/diarahkan ekornya (simpan otomatis 600 ms), inspector (judul, deskripsi, karakter, latar, shot, sudut, rasio, gaya, model gambar bawaan dari proyek, estimasi + dialog konfirmasi biaya, take, pratinjau prompt, editor balon, unduh PNG, hapus).
- `comic/draw.ts`: satu penggambar canvas untuk tampilan dan unduh PNG (balon bicara elips + ekor, pikiran + lingkaran, narasi kotak, SFX miring bergaris tebal; teks dibungkus dan dikecilkan otomatis).

## Menyimpang dari plan
- Font: font sistem bergaya komik, bukan Google Fonts.
- DELETE mengembalikan `{ok: true}` (pola klien `call()` membaca JSON).

## Temuan grill yang ditangani
1, 3, 4, 5, 6, 7, 8, 10, 11 ditangani di kode dan tes. 9 (canvas tainted/font): gambar dari origin sama, font sistem. 2 (model tetap menggambar teks) tidak bisa dijamin.

## Hasil tes
- `make test`: **443 lulus** (baru: `test_comic.py`, 7 tes: CRUD + validasi, per proyek, prompt tanpa teks balon, generate 409 tanpa konfirmasi + referensi latar/karakter + take otomatis + pilih take lama, teks-ke-gambar tanpa gambar input, terlalu banyak referensi ditolak, referensi basi dibersihkan, hapus proyek menghapus panel).
- `cd frontend && npm run build`: hijau.

## Batasan yang diketahui
- Edit balon di kanvas dan di inspector pada saat yang sama bisa saling menimpa (keduanya menyimpan daftar balon utuh).
- Kualitas gambar komik nyata belum dicoba (hanya OpenRouter palsu).

## Diuji manual oleh user
1. Restart `make dev` (migrasi v20). Buka **Komik** di sidebar, buat panel pertama.
2. Pilih karakter + latar, tulis deskripsi, pilih gaya; lihat pratinjau prompt dan estimasi biaya; buat gambar (dialog konfirmasi muncul).
3. Tambah balon bicara/pikiran/narasi/SFX; geser, ubah ukuran, arahkan ekor; ubah teks; reload halaman untuk memastikan tersimpan.
4. Buat take baru: gambar berganti ke yang terbaru; klik take lama untuk kembali.
5. Unduh PNG dan bandingkan dengan tampilan.
6. Hapus karakter yang dipakai panel; panel tetap ada tanpa karakter itu.
