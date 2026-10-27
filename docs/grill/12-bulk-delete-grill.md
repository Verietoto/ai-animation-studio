# 12 - Hapus banyak sekaligus di Library (Grill)

Plan terkait: `docs/plan/12-bulk-delete-plan.md`
Tanggal: 2026-10-21. Temuan dari membaca `service.py` (`delete_image`, `delete_clip`, `delete_character`, `_unlink`, `poll_once`, `_poll_clip`, `_download`), `films.py` (`detach_clip`), `db.py` (`committed_today`), `pages/Library.tsx` (mode pilih), dan sweep lintas workspace di `test_workspaces.py`.

## Lubang pada plan
1. **Pilihan yang tersembunyi filter.** Mode pilih bertahan saat user mengganti filter atau pencarian. "Hapus (N)" bisa menghitung item yang tidak terlihat, jadi user menghapus sesuatu yang tidak sedang dilihat. Ini risiko terbesar fitur ini.
2. **Pengulangan permintaan.** Bila permintaan dikirim ulang (klik ganda, jaringan putus lalu coba lagi), item yang sudah terhapus menjawab 404 "tidak ditemukan" dan akan tampil sebagai gagal, padahal tujuannya sudah tercapai.
3. **Sweep lintas workspace tidak mencakup endpoint ini.** `test_workspaces` hanya menyapu route yang punya parameter path id. `/api/bulk-delete` menaruh id di body, jadi isolasi workspace harus punya test sendiri.
4. **Karakter vs gambarnya.** Menghapus karakter tidak menghapus gambarnya; gambar yang tadinya "dipakai karakter" jadi bisa dihapus. Plan sudah mengurutkannya, tetapi dialog harus jelas bahwa gambar karakter yang tidak ikut dipilih tetap ada.
5. **Pesan "tidak bisa dikembalikan" belum akurat untuk semuanya.** Berkas hilang dari disk, tetapi baris tetap ada (hapus lunak) dan biaya tetap terhitung di anggaran harian (`committed_today` tidak memfilter `deleted_at`, sudah dicek). Pesannya harus menyebut keduanya.

## Risiko (dampak, kemungkinan, mitigasi)
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| Menghapus item yang tidak terlihat | Kehilangan berkas permanen | Sedang | Dialog menampilkan jumlah total dan berapa yang tersembunyi filter; pilihan dibersihkan dari id yang sudah tidak ada setelah muat ulang. |
| Hapus rantai extend sebagian | Gagal berantai | Sedang | Urut dari `chain_depth` terbesar; induk yang anaknya tidak ikut dipilih gagal dengan alasan "punya lanjutan". |
| Batch besar menahan generate lain | Aplikasi terasa macet | Rendah | Kunci per item, bukan per batch; maksimum 200 id. |
| Klip dipakai film yang sedang dirender | Render rusak | Rendah | `detach_clip` sudah menolak 409; bulk melaporkannya sebagai item gagal. |
| Berkas terhapus tetapi baris gagal ditulis | Baris menunjuk berkas hilang | Sangat rendah | Sudah ada di hapus satuan (`_unlink` sebelum update). Tidak diperburuk; dicatat. |

## Edge case
- Daftar kosong atau semua jenis kosong: 400, bukan 200 kosong.
- Id ganda dalam daftar: dihapus duplikatnya.
- Lebih dari 200 id: 422.
- Id dari workspace lain: dilaporkan "tidak ditemukan", bukan membocorkan keberadaan.
- Klip yang sedang diproses: ditolak, yang lain tetap diproses.
- Gambar yang dipakai latar atau tampilan: ditolak dengan pesan aslinya.
- Lightbox terbuka pada item yang baru terhapus: sudah ditangani (`item hilang dari daftar` mengembalikan null).
- Poller: hanya menulis klip berstatus aktif, dan klip aktif tidak bisa dihapus, jadi bulk tidak menambah balapan baru. Poller memang tidak memegang `_lock`, tetapi tidak menyentuh klip yang sudah selesai.

## Potensi bug
1. Mengurutkan klip terdalam-dulu memakai `chain_depth`; klip yang sudah dihapus lunak tidak ikut `get_clip`. Perlu test rantai tiga tingkat yang dipilih utuh, dan rantai yang hanya induknya dipilih.
2. `delete_image` mengosongkan `scenes.keyframe_image_id` diam-diam. Pada bulk, banyak adegan bisa kehilangan keyframe sekaligus. Dialog menyebut "keyframe adegan yang memakainya akan kosong".
3. Penghitungan "terpilih" di UI memakai kunci `type:id` dan klip sebelumnya dinonaktifkan di mode pilih (`disabled={selecting && e.type === "clip"}`); itu harus diubah, kalau tidak klip tak bisa dipilih.

## Asumsi yang belum terbukti
- 200 penghapusan per permintaan selesai dalam waktu wajar. Setiap penghapusan satu `unlink` dan beberapa UPDATE SQLite; diukur di test dengan 200 item kecil, bukan dengan berkas besar.

## Keputusan setelah grilling (perubahan pada plan)
- Respons: `{deleted: {images, clips, characters}, skipped, failed: [{type, id, reason}]}`. **404 dihitung `skipped`** ("sudah tidak ada"), bukan gagal.
- Daftar kosong 400; id ganda dibuang; maksimum 200 id (422).
- UI: dialog menampilkan total, rincian per jenis, dan jumlah yang tersembunyi filter; setelah muat ulang, pilihan dibersihkan dari id yang sudah tidak ada. "Pilih semua yang terlihat" hanya menambah yang terlihat.
- Dialog menyebut: berkas dihapus dari disk, biaya tetap terhitung, keyframe adegan terkait menjadi kosong, gambar karakter yang tidak ikut dipilih tetap ada.
- Test khusus isolasi workspace untuk endpoint ini.

## Riwayat
- 2026-10-21: grill awal.
