# 16 - Karakter dari prompt, referensi opsional (Implementation)

Plan: `docs/plan/16-character-from-prompt-plan.md` · Grill: `docs/grill/16-character-from-prompt-grill.md`
Tanggal: 2026-10-26 · Status: backend selesai dan teruji (289 test); UI selesai dibangun (build hijau); spike kualitas dengan model nyata berhasil. **Menunggu uji manual oleh user.**

## Yang dibangun
### Backend
- `sceneprompt.py` `portrait_prompt(description)`: tampak depan, seluruh badan, pose netral, latar polos abu terang, cahaya merata, satu karakter, tanpa teks/label/watermark. Deskripsi dipotong 800 karakter. **Nama tidak dipakai** (model bisa menggambar teks dari nama).
- `service.py`:
  - `portrait_plan(model, description)`: satu sumber untuk estimasi dan pembuatan. Deskripsi wajib (422), maks 2000; rasio 3:4 dikirim hanya bila model mendukung (`Scenes._aspect_option`); model divalidasi sebelum biaya keluar.
  - `create_portrait(...)`: `authorize` → `generate_image` → simpan **satu** gambar `kind = "portrait"`. Tidak membuat karakter. Penolakan penyedia atau jawaban tanpa gambar tidak meninggalkan gambar maupun baris biaya.
- `main.py`: `POST /api/characters/portrait` (`description`, `model`, konfirmasi biaya); kind estimasi `character_portrait` (+ field `description`).
- Karakter tetap dibuat lewat `POST /api/characters` yang sudah ada dengan `source_image_id` (referensi atau potret).

### Frontend
- `characters/CharacterCreator.tsx` (baru): nama, deskripsi (dengan petunjuk menulis gaya), "Gambar karakter (referensi opsional)": strip unggah/pilih **dan** tombol "Buat gambar dari deskripsi" (model, estimasi, dialog biaya; satu gambar per klik, hasil langsung terpilih), hitungan "N potret belum dipakai", dan "Simpan karakter". Pilihan gambar bisa dikendalikan induk atau memakai state sendiri.
- `pages/Characters.tsx`: panel kanan diganti `CharacterCreator` (state form lama dihapus).
- Langkah 1 alur episode (`StepCast.tsx`): bagian "Karakter baru" memakai komponen yang sama dan karakter baru langsung masuk episode; tiap kartu latar punya "Deskripsi & gambar" (kolom deskripsi tersimpan otomatis + `LocationImagePanel` untuk membuat gambar dari deskripsi).
- `App.tsx` → `Storyboard` mendapat `reloadCharacters`; `api.ts` (`Img.kind` "portrait", `characterPortrait`, estimasi `character_portrait`); `lightbox.tsx` label "Potret".

## Spike kualitas (berbayar, batas $0.15 yang disetujui)
`scripts/spike_portrait.py`: 4 panggilan Seedream 5 Flash dengan `aspect_ratio=3:4`, **$0.018 per gambar, total $0.072** (sama dengan harga katalog).
| Deskripsi | Hasil |
|---|---|
| Gadis desa, kebaya merah, gaya anime | Bersih: seluruh badan, menghadap depan, kepang dua, kebaya dan kain batik, sandal jerami, latar abu polos. |
| Penjaga warung, kartun 2D | Bersih: kumis tipis, kaus putih, celemek cokelat; gaya kartun garis tegas. "Perut agak buncit" hampir tak terlihat. |
| Nenek, animasi 3D ramah anak | Bersih: rambut putih disanggul, kacamata bulat, kebaya hijau dan sarung, gaya 3D. |
| Wanita 28 tahun, foto-realistik | Bersih dan realistis; **jenis ini ditolak Seedance** di jalur video (peringatan di form). |

Semua: satu karakter, tanpa teks atau label, latar polos. Prompt tidak perlu diubah. Model kedua tidak diuji (tidak perlu).

## Temuan grill yang ditangani
| Grill | Penanganan |
|---|---|
| Nama bisa tergambar sebagai teks | Nama tidak dikirim. Test `test_creates_one_portrait_image_with_cost_and_kind`. |
| Penolakan penyedia / jawaban kosong | Tanpa gambar dan tanpa biaya. Test `test_provider_error_leaves_no_image_and_no_cost`, `test_empty_model_answer_is_422_without_image`. |
| Biaya dan batas | Konfirmasi wajib (409), batas harian (402), deskripsi kosong/terlalu panjang dan model tak dikenal ditolak sebelum biaya. |
| Label lightbox | "Potret" ditambah (tsc menangkap bila lupa). |
| Dua tempat memakai form | Satu komponen `CharacterCreator`. |
| Karakter baru dari Langkah 1 masuk episode | `onCreated` memanggil `setEpisodeCast`; bentrok nama ditampilkan sebagai galat. |
| Klik ganda | Tombol dikunci selama permintaan; tidak ada idempotensi server (dicatat). |

## Menyimpang dari plan
- Hitungan "potret belum dipakai" dihitung di klien dari daftar gambar dan karakter (sesuai grill).
- Panel "Karakter baru" di Langkah 1 berupa bagian yang dilipat, supaya daftar pemeran tetap ringkas.
- Tidak ada penyaringan kata di deskripsi; hanya petunjuk menulis gaya.

## Hasil tes
- `make test`: **289 passed** (278 → 289; 11 test baru di `backend/tests/test_portrait.py`: prompt, satu potret + biaya + `kind`, menjadi karakter lewat endpoint yang ada, konfirmasi wajib, deskripsi kosong/panjang, model tak dikenal, galat penyedia, jawaban kosong, batas harian, workspace, rasio 3:4 hanya bila didukung).
- `cd frontend && npm run build`: hijau.
- UI belum dijalankan (lihat bawah).

## Uji frontend: diuji manual oleh user
Restart backend dulu (`make dev`).
1. Karakter → panel kanan: isi nama dan deskripsi (tulis gayanya), klik "Buat gambar dari deskripsi": dialog biaya (± $0,018), lalu gambar muncul di strip dan terpilih. Klik lagi untuk variasi; hitungan "N potret belum dipakai" naik. "Simpan karakter": karakter muncul di daftar.
2. Dengan referensi: unggah atau pilih gambar, tanpa menekan tombol buat; "Simpan karakter" bekerja seperti sebelumnya.
3. Tombol buat nonaktif bila deskripsi kosong; model teks-saja memberi galat yang jelas.
4. Langkah 1 alur episode → "Karakter baru": buat karakter dengan dua cara di atas; karakter langsung tercentang di episode. Nama yang sama dengan karakter lain di episode menampilkan galat.
5. Langkah 1 → kartu latar → "Deskripsi & gambar": isi deskripsi (tersimpan otomatis), "Buat dari deskripsi": gambar latar muncul di kartu. Latar tanpa gambar bertanda "tanpa gambar" sampai dibuat.
6. Library: potret berlabel "Potret" di Lightbox; hapus yang tidak dipakai (bisa hapus massal).

## Riwayat
- 2026-10-26: implementasi awal.
