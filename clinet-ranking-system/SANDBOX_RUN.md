# Sandbox Run Guide (Local-Only)

This project is now safe to run in a restricted sandbox without system-wide installs.

## 1) Create local venv

```bash
python3 -m venv .venv
```

## 2) Install minimal dependencies in the local venv

```bash
./.venv/bin/python -m pip install -r requirements.txt
```

Optional advanced semantic embeddings (heavy):

```bash
./.venv/bin/python -m pip install -r requirements-ml.txt
```

## 3) Run pipeline in offline sandbox mode

```bash
CRS_OFFLINE_MODE=1 EMBEDDING_LOCAL_ONLY=1 ./.venv/bin/python main.py
```

## 4) Run API in offline sandbox mode

```bash
CRS_OFFLINE_MODE=1 EMBEDDING_LOCAL_ONLY=1 ./.venv/bin/python api/app.py
```

## 5) Run tests

```bash
./.venv/bin/python -m pytest -q
```

## Notes

- `CRS_OFFLINE_MODE=1` disables external crawl/LLM internet dependencies.
- `EMBEDDING_LOCAL_ONLY=1` avoids remote model downloads.
- No package is installed globally; everything stays inside `.venv`.
