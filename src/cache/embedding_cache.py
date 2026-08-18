from pathlib import Path

import numpy as np


def load_embedding_cache(path: Path) -> dict[str, np.ndarray]:
    if not path.exists():
        return {}
    data = np.load(path)
    return dict(zip(data["keys"], data["vectors"]))


def save_embedding_cache(cache: dict[str, np.ndarray], path: Path) -> None:
    keys = np.array(list(cache.keys()))
    vectors = np.stack(list(cache.values()))
    np.savez(path, keys=keys, vectors=vectors)
