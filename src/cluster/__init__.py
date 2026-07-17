from models import Person
from cluster.embed import embed_persons
from cluster.faiss_cluster import cluster


def cluster_persons(
    persons: list[Person],
    api_url: str,
    api_key: str,
    model: str,
    k: int,
    threshold: float,
    batch_size: int,
    concurrency: int,
) -> list[list[Person]]:
    """Embed and cluster persons. Returns clusters (singletons excluded)."""
    embeddings = embed_persons(persons, api_url, api_key=api_key, model=model,
                               batch_size=batch_size, concurrency=concurrency)
    index_clusters = cluster(embeddings, k=k, threshold=threshold)
    return [[persons[i] for i in idxs] for idxs in index_clusters]