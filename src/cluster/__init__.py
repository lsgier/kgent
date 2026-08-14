import numpy as np

from models import Person
from cluster.embed import embed_persons
from cluster.faiss_cluster import cluster
from cluster.idf import compute_name_idf


def cluster_persons(
    persons: list[Person],
    api_url: str,
    api_key: str,
    model: str,
    k: int,
    threshold: float,
    batch_size: int,
    concurrency: int,
    name_similarity_penalty: float = 0.0,
) -> list[list[Person]]:
    """Embed and cluster persons. Returns clusters (singletons excluded)."""
    embeddings = embed_persons(persons, api_url, api_key=api_key, model=model,
                               batch_size=batch_size, concurrency=concurrency)
    idf = None
    if name_similarity_penalty:
        name_idf = compute_name_idf(persons)
        idf = np.array([name_idf[p.name] for p in persons], dtype=np.float32)
    index_clusters = cluster(embeddings, k=k, threshold=threshold, idf=idf,
                             name_similarity_penalty=name_similarity_penalty)
    return [[persons[i] for i in idxs] for idxs in index_clusters]