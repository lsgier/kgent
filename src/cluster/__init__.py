from models import Person
from cluster.embed import embed_persons
from cluster.faiss_cluster import cluster


def cluster_persons(
    persons: list[Person],
    api_url: str,
    api_key: str,
    model: str,
    k: int = 20,
    threshold: float = 0.95,
) -> list[list[Person]]:
    """Embed and cluster persons. Returns clusters (singletons excluded)."""
    embeddings = embed_persons(persons, api_url, model=model, api_key=api_key)
    index_clusters = cluster(embeddings, k=k, threshold=threshold)
    return [[persons[i] for i in idxs] for idxs in index_clusters]