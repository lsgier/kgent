import faiss
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components


def cluster(embeddings: np.ndarray, k: int = 20, threshold: float = 0.95) -> list[list[int]]:
    """Return clusters as lists of indices into embeddings. Singletons excluded."""
    n = len(embeddings)
    norms  = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-10
    normed = (embeddings / norms).astype(np.float32)

    index = faiss.IndexFlatIP(normed.shape[1])
    index.add(normed)
    sims, indices = index.search(normed, k + 1)

    rows, cols = [], []
    for i in range(n):
        for pos in range(1, k + 1):
            j = int(indices[i, pos])
            if j != i and float(sims[i, pos]) >= threshold:
                rows.append(i)
                cols.append(j)

    if not rows:
        return []

    graph = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    _, labels = connected_components(graph, directed=False)
    sizes = np.bincount(labels)

    clusters: dict[int, list[int]] = {}
    for i, label in enumerate(labels):
        if sizes[label] > 1:
            clusters.setdefault(int(label), []).append(i)

    return list(clusters.values())