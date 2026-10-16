# ai-animation-studio

Studio untuk membuat video pendek dengan AI lewat [OpenRouter](https://openrouter.ai).

Fitur iterasi 1: gambar → video dengan prompt, extend klip (frame terakhir + ffmpeg), library klip, gabung rantai extend, edit foto dengan prompt (hasilnya bisa langsung jadi video).
Belum ada: salin gerakan + suara, proyek berepisode. Lihat `docs/`.

## Cara kerja dengan agent
Setiap fitur melewati `docs/plan` → `docs/grill` → `docs/implementation` (aturan di `CLAUDE.md`).

## Menjalankan
Butuh Python 3.11+, Node 20+, dan ffmpeg/ffprobe.

```bash
cp .env.example .env            # isi OPENROUTER_API_KEY
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm install && npm run build)
set -a; . ./.env; set +a
.venv/bin/uvicorn --app-dir backend app.main:app_factory --factory --host 127.0.0.1 --port 8000
```
Buka http://127.0.0.1:8000. Server hanya untuk dipakai lokal (tidak ada login); jangan diekspos ke internet apa adanya.

Pengembangan frontend: `cd frontend && npm run dev` (proxy `/api` ke port 8000).

## Tanpa API key
```bash
PYTHONPATH=. .venv/bin/uvicorn scripts.fake_openrouter:app --port 9000
OPENROUTER_API_KEY=fake OPENROUTER_BASE_URL=http://127.0.0.1:9000/api/v1 .venv/bin/uvicorn --app-dir backend app.main:app_factory --factory --port 8000
```

## Tes
```bash
.venv/bin/python -m pytest backend
```
`scripts/smoke_openrouter.py` memverifikasi asumsi kontrak API dengan key sungguhan (default hanya membaca daftar model).
