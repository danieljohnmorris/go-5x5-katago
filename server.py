"""
KataGo HTTP wrapper for 5x5 Go.

Spawns KataGo's analysis engine as a subprocess at startup and forwards
move requests to it. KataGo speaks JSON over stdin/stdout: one JSON line
in, one JSON line out per query.
"""

import json
import os
import subprocess
import threading
import uuid
from queue import Queue, Empty

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

KATAGO_BIN = os.environ.get("KATAGO_BIN", "katago")
KATAGO_MODEL = os.environ.get("KATAGO_MODEL", "/app/network.bin.gz")
KATAGO_CONFIG = os.environ.get("KATAGO_CONFIG", "/app/analysis.cfg")
ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "https://go-5x5-katago.danieljohnmorris.com,http://localhost:8765,http://localhost:8000",
).split(",")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


class _KataGo:
    """Lifetime-of-process wrapper around `katago analysis`."""

    def __init__(self) -> None:
        # stderr is left attached to the container so KataGo's startup messages
        # (model load, GPU/Eigen backend, etc.) and any crash trace show up in
        # `docker logs`. KataGo writes a lot to stderr but it's worth seeing.
        self.proc = subprocess.Popen(
            [KATAGO_BIN, "analysis", "-model", KATAGO_MODEL, "-config", KATAGO_CONFIG],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            bufsize=1,
            text=True,
        )
        self._lock = threading.Lock()
        self._responses: dict[str, Queue] = {}
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            qid = msg.get("id")
            if qid in self._responses:
                self._responses[qid].put(msg)

    def query(self, payload: dict, timeout: float = 30.0) -> dict:
        qid = uuid.uuid4().hex
        payload["id"] = qid
        q: Queue = Queue()
        self._responses[qid] = q
        line = json.dumps(payload) + "\n"
        with self._lock:
            assert self.proc.stdin is not None
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        try:
            return q.get(timeout=timeout)
        except Empty:
            raise HTTPException(status_code=504, detail="KataGo timeout")
        finally:
            self._responses.pop(qid, None)


_engine: _KataGo | None = None
_engine_lock = threading.Lock()
_engine_error: str | None = None


def _get_engine() -> _KataGo:
    """Lazily start KataGo on first move request so /healthz works during boot."""
    global _engine, _engine_error
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is not None:
            return _engine
        try:
            _engine = _KataGo()
        except Exception as e:
            _engine_error = repr(e)
            raise
    return _engine


@app.get("/healthz")
def healthz() -> dict:
    alive = _engine is not None and _engine.proc.poll() is None
    return {"ok": True, "engine_started": _engine is not None, "alive": alive, "error": _engine_error}


# Coordinate translation between (x, y) where (0, 0) is top-left and KataGo's
# letter-number scheme where A1 is bottom-left and the letter "I" is skipped.
_LETTERS = "ABCDEFGHJKLMNOPQRST"  # 19 columns max, no I
N = 5


def xy_to_kata(x: int, y: int) -> str:
    return f"{_LETTERS[x]}{N - y}"


class MoveRequest(BaseModel):
    moves: list[list[str]]  # e.g. [["B", "C3"], ["W", "B2"]]
    next_player: str  # "B" or "W"
    komi: float = 2.5
    max_visits: int = 32


@app.post("/move")
def get_move(req: MoveRequest) -> dict:
    try:
        engine = _get_engine()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"engine failed to start: {e}")
    payload = {
        "initialStones": [],
        "moves": req.moves,
        "rules": "chinese",
        "komi": req.komi,
        "boardXSize": N,
        "boardYSize": N,
        "analyzeTurns": [len(req.moves)],
        "maxVisits": req.max_visits,
    }
    msg = engine.query(payload)
    move_infos = msg.get("moveInfos", [])
    if not move_infos:
        return {"move": "pass", "winrate": None}
    # KataGo returns moves sorted by playSelectionValue descending.
    top = move_infos[0]
    return {
        "move": top["move"],  # "pass" or "C3"
        "winrate": top.get("winrate"),
        "score_lead": top.get("scoreLead"),
        "visits": msg.get("rootInfo", {}).get("visits"),
    }
