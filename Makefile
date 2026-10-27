.PHONY: be fe dev test

# backend: http://127.0.0.1:8000 (butuh .env berisi OPENROUTER_API_KEY)
be:
	set -a; . ./.env; set +a; .venv/bin/uvicorn --app-dir backend app.main:app_factory --factory --host 127.0.0.1 --port 8000

# frontend dev server (proxy /api ke port 8000)
fe:
	cd frontend && npm run dev

# jalankan keduanya; Ctrl+C mematikan keduanya
dev:
	$(MAKE) -j2 be fe

test:
	.venv/bin/python -m pytest backend
