import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
import numpy as np

from cache.embedding_cache import load_embedding_cache, save_embedding_cache
from models import Person

log = logging.getLogger(__name__)


def _text(p: Person, fields: list[str]) -> str:
    parts = []
    for field in fields:
        value = getattr(p, field)
        if value:
            parts.append(value)
    return " ".join(parts)


# Content-addressed: a person whose embedded text and model haven't changed always
# maps to the same key, so the cache self-invalidates instead of needing to be cleared.
def _cache_key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\x00{text}".encode()).hexdigest()


def embed_persons(persons: list[Person], api_url: str, api_key: str, model: str,
                  batch_size: int, concurrency: int, fields: list[str],
                  cache_path: Path) -> np.ndarray:
    texts = [_text(p, fields) for p in persons]
    keys  = [_cache_key(model, t) for t in texts]

    cache = load_embedding_cache(cache_path)
    missing = [i for i, k in enumerate(keys) if k not in cache]
    log.info("Embedding cache: %d/%d persons already cached, embedding %d new",
             len(persons) - len(missing), len(persons), len(missing))

    if missing:
        missing_texts = [texts[i] for i in missing]
        batches = [missing_texts[i: i + batch_size] for i in range(0, len(missing_texts), batch_size)]
        results: dict[int, list] = {}

        def fetch(idx: int) -> tuple[int, list]:
            batch = batches[idx]
            for attempt in range(6):
                try:
                    resp = httpx.post(
                        api_url,
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={"model": model, "input": batch},
                        timeout=180,
                    )
                    resp.raise_for_status()
                    data = sorted(resp.json()["data"], key=lambda x: x["index"])
                    return idx, [d["embedding"] for d in data]
                except (httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError) as e:
                    time.sleep(2 ** attempt)
                except httpx.HTTPStatusError as e:
                    wait = float(e.response.headers.get("Retry-After", 0)) or (10 * (2 ** attempt)) if e.response.status_code == 429 else 2 ** attempt
                    time.sleep(wait)
            raise RuntimeError(f"Embedding batch {idx} failed after 6 attempts")

        total = len(batches)
        next_log_pct = 10
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for future in as_completed(pool.submit(fetch, i) for i in range(len(batches))):
                idx, embs = future.result()
                results[idx] = embs
                pct = len(results) * 100 // total
                if pct >= next_log_pct:
                    log.info("Embedded %d/%d batches (%d%%)", len(results), total, pct)
                    next_log_pct += 10

        new_embs = [emb for idx in sorted(results) for emb in results[idx]]
        for i, emb in zip(missing, new_embs):
            cache[keys[i]] = np.array(emb, dtype=np.float32)
        save_embedding_cache(cache, cache_path)

    return np.stack([cache[k] for k in keys])