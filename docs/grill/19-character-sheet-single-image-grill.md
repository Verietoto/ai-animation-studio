# Grill 19 — Lembar karakter 1 gambar

| # | Temuan | Mitigasi |
|---|---|---|
| 1 | Model gambar bisa menggambar < 4 panel, menambah teks/label, atau mengubah wajah antar panel. | Prompt eksplisit (jumlah panel, urutan, tanpa teks); hasil tetap draf di library, user menilai. Tidak ada validasi otomatis (tidak bisa diverifikasi tanpa vision). |
| 2 | Sudut belakang dikarang (tidak ada di sumber). | Dicatat; user menyetujui tetap disertakan. |
| 3 | Rasio 16:9 tidak didukung model tertentu → galat. | Rasio dikirim hanya bila user memilih atau model mendukung (`_aspect_option`); jika tidak didukung, tanpa rasio dan model memakai bawaannya. |
| 4 | Gambar lebar sebagai referensi lain (motion anchor, edit lock) memakan token/ukuran lebih. | Tidak ada perubahan; satu gambar lebar lebih ringan dari empat. |
| 5 | Tes lama mengasumsikan 4 gambar/4 panggilan. | Ditulis ulang, bukan dilonggarkan. |
| 6 | Karakter lama (4 gambar) dan salinan workspace. | Tidak disentuh; tes `has_sheet` tetap. |
| 7 | Biaya: estimasi harus turun, konfirmasi basi tetap ditolak. | `estimate_sheet(n_views=1)`; `authorize` tidak berubah. |
