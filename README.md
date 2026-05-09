# go-5x5-katago (server)

KataGo analysis engine fronted by a small FastAPI HTTP server. Used by [go-5x5-katago.danieljohnmorris.com](https://go-5x5-katago.danieljohnmorris.com).

## Endpoints

- `GET /healthz` - returns `{ ok, alive }` indicating whether the KataGo subprocess is up.
- `POST /move` - body `{ moves: [["B", "C3"], ...], next_player: "W", komi: 2.5, max_visits: 32 }`. Returns `{ move, winrate, score_lead, visits }`. `move` is either a KataGo coordinate like `"C3"` or `"pass"`.

## Run locally

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
KATAGO_BIN=$(which katago) \
  KATAGO_MODEL=$PWD/katago-network.bin.gz \
  KATAGO_CONFIG=$PWD/analysis.cfg \
  uvicorn server:app --port 8088
```

## Files

- `server.py` - FastAPI wrapper, JSON-over-stdio bridge to `katago analysis`.
- `analysis.cfg` - tuned for 5x5: 32-64 visits, single thread.
- `katago-network.bin.gz` - 83 MB b20c256 network. Overkill for 5x5 but already on disk.
- `Dockerfile` - python:3.12-slim + KataGo eigenavx2 prebuilt binary.
