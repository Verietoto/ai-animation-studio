# ai-animation-studio

Tool untuk membuat film pendek menggunakan AI.

## Aturan wajib: setiap fitur melalui 3 tahap

Sebelum menulis kode untuk fitur apa pun, agent HARUS menyelesaikan tiga tahap berikut secara berurutan. Tidak boleh melompati tahap.

| # | Tahap | Folder | Tujuan |
|---|-------|--------|--------|
| 1 | Planning | `docs/plan/` | Tujuan, ruang lingkup, desain, langkah kerja, kriteria selesai |
| 2 | Grilling | `docs/grill/` | Mencari lubang, risiko, edge case, dan potensi bug pada plan |
| 3 | Implementation | `docs/implementation/` | Catatan implementasi: apa yang dibangun, keputusan, hasil tes |

### Aturan penamaan

- Format: `NN-judul-kebab-case.md`, contoh `01-architecture-plan.md`.
- `NN` adalah nomor urut dua digit **per folder**, mulai dari `01`.
- Satu fitur memakai judul dasar yang sama di ketiga folder, supaya mudah dilacak:
  - `docs/plan/02-scene-generator-plan.md`
  - `docs/grill/02-scene-generator-grill.md`
  - `docs/implementation/02-scene-generator-implementation.md`
- Nomor fitur sama di ketiga folder. Cek nomor terakhir dengan `ls docs/plan` sebelum membuat fitur baru.
- Gunakan template di `docs/_templates/`.

### Alur kerja

1. **Plan**: tulis `docs/plan/NN-...-plan.md`. Berhenti dan minta persetujuan user.
2. **Grill**: bersikap skeptis terhadap plan sendiri. Tulis `docs/grill/NN-...-grill.md` berisi lubang, risiko, bug potensial, asumsi yang belum terbukti, beserta mitigasinya. Perbarui plan bila temuan mengubah desain.
3. **Implement**: baru boleh menulis kode setelah plan dan grill ada dan disetujui. Tulis `docs/implementation/NN-...-implementation.md` selama/ setelah pengerjaan. Isinya: file yang diubah, keputusan yang menyimpang dari plan, temuan grill yang sudah ditangani, hasil tes.

### Larangan

- Jangan menulis kode fitur sebelum `plan` dan `grill` untuk fitur itu ada.
- Jangan menandai fitur selesai tanpa file `implementation` dan bukti tes yang benar-benar dijalankan.
- Jangan menghapus atau menulis ulang dokumen lama; tambahkan revisi di bagian "Riwayat" pada dokumen itu.
- **Pengujian frontend dilakukan user sendiri.** Agent (termasuk `implementer`) tidak boleh membuka browser, menjalankan dev server untuk uji manual, mengambil screenshot, atau mengklik-klik UI. Cukup `cd frontend && npm run build` (tsc + vite) dan, untuk backend, `make test`. Di file `implementation`, bagian uji frontend ditulis sebagai "diuji manual oleh user" (daftar alur yang perlu dicoba), bukan hasil yang diklaim agent.

Sub-agent khusus tahap ada di `.claude/agents/` (`planner`, `grill`, `implementer`).
