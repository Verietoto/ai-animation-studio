# Plan 19 — Lembar karakter: 1 gambar, beberapa sudut

## Latar
`Studio.generate_sheet` (plan 03) memanggil model 4 kali dan menyimpan 4 gambar terpisah (front, side, three_quarter, full_body). Koreksi user: konsepnya salah. Yang benar: **satu gambar** yang memuat beberapa sudut karakter sekaligus (turnaround / model sheet), bukan beberapa foto berbeda sudut.

## Tujuan
Satu permintaan → satu gambar lembar karakter berisi beberapa tampilan berdampingan, konsisten wajah, rambut, pakaian, warna.

## Desain
- `generate_sheet`: **1 panggilan** `_run_edit` dari gambar sumber karakter dengan prompt turnaround: satu baris panel berdampingan pada latar abu terang polos: depan, tiga-perempat, samping, belakang; semuanya seluruh badan, berdiri, pose netral, proporsi dan skala sama; wajah dan detail identik dengan gambar acuan; tanpa teks dan label.
- Rasio bawaan lembar **16:9** (lebar, supaya 4 panel muat) bila user tidak memilih; tetap bisa diganti; divalidasi lewat `_validate_image_params` seperti sekarang.
- Disimpan sebagai satu gambar `kind="sheet"`, label `sheet` di `character_images`. `has_sheet` tetap benar (sumber + lembar = 2 gambar).
- **Estimasi biaya 1 gambar** (turun ±4× dari sekarang). Alur konfirmasi biaya tidak berubah. `/api/estimate` kind `character_sheet` memakai 1 tampilan.
- Karakter lama dengan 4 gambar terpisah **tidak diubah atau dihapus**; tetap sah sebagai referensi. Membuat lembar lagi menambah satu gambar (tidak menimpa).
- Teks UI "tambah ke sheet" dan tooltip disesuaikan ("lembar tampilan"); tampilan lembar di kartu karakter memakai gambar lebar apa adanya.

## Di luar lingkup
Storyboard v2 tetap memakai gambar sumber/tampilan karakter sebagai `@image_N` (bukan lembar), supaya video tidak meniru tata letak panel. Bisa diubah bila user mau.

## Kriteria selesai
- Satu panggilan ke penyedia per lembar (tes menghitung request `/images`).
- Estimasi = 1 gambar; konfirmasi tetap wajib (409 tanpa konfirmasi).
- Prompt memuat semua sudut dan larangan teks; rasio 16:9 terkirim bila model mendukung.
- Karakter lama (4 gambar) tetap terbaca; `make test` hijau; `npm run build` hijau.
- `docs/implementation/19-…` dengan hasil tes; uji UI manual oleh user.

## Riwayat
- Dibuat atas koreksi user: "bukan generate beberapa foto beda angle tapi generate 1 foto dengan beberapa angle".
