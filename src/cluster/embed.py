import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import numpy as np

from models import Person


def _text(p: Person) -> str:
    parts = [p.name]
    if p.bio:      parts.append(p.bio)
    if p.location: parts.append(p.location)
    if p.company:  parts.append(p.company)
    return " ".join(parts)


def embed_persons(persons: list[Person], api_url: str, api_key: str, model: str,
                  batch_size: int, concurrency: int) -> np.ndarray:
    texts   = [_text(p) for p in persons]
    batches = [texts[i: i + batch_size] for i in range(0, len(texts), batch_size)]
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

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for future in as_completed(pool.submit(fetch, i) for i in range(len(batches))):
            idx, embs = future.result()
            results[idx] = embs

    all_embs = [emb for idx in sorted(results) for emb in results[idx]]
    return np.array(all_embs, dtype=np.float32)