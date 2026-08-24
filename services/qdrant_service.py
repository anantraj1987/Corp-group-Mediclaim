from __future__ import annotations
import uuid
import time
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from config.settings import (
    OPENAI_API_KEY,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    QDRANT_DIR,
    QDRANT_COLLECTION_NAME,
    settings,
)

client = OpenAI(api_key=OPENAI_API_KEY)

# Global singleton instance to prevent storage folder locks
_qdrant_client_instance: QdrantClient | None = None

def infer_metadata(filename: str) -> dict:
    """Infers business metadata from document filename."""
    fn = filename.lower()
    
    if "census" in fn:
        source = "census"
        department = "HR"
    elif "corporate_accounts" in fn:
        source = "corporate_accounts"
        department = "Policy"
    elif "master_sla" in fn:
        source = "SLA"
        department = "SLA"
    else:
        source = "others"
        department = "others"

    contract = filename.rsplit("_gmc_master_sla", 1)[0]
    contract = contract.replace("_", " ").strip().title()

        

    return {
        "source_data": source,
        "department": department,
        "contract": contract,
    }

def get_qdrant_client() -> QdrantClient:
    """Returns a singleton QdrantClient instance."""
    global _qdrant_client_instance
    if _qdrant_client_instance is None:
        QDRANT_DIR.mkdir(parents=True, exist_ok=True)
        _qdrant_client_instance = QdrantClient(path=str(QDRANT_DIR))
    return _qdrant_client_instance

def get_embedding(text: str) -> list[float]:
    text = text.replace("\n", " ")
    response = client.embeddings.create(
        input=[text],
        model=EMBEDDING_MODEL
    )
    return response.data[0].embedding

def init_qdrant_collection(q_client: QdrantClient, force_recreate: bool = False):
    collections = [c.name for c in q_client.get_collections().collections]
    
    if QDRANT_COLLECTION_NAME in collections and force_recreate:
        q_client.delete_collection(QDRANT_COLLECTION_NAME)
        collections.remove(QDRANT_COLLECTION_NAME)

    if QDRANT_COLLECTION_NAME not in collections:
        q_client.create_collection(
            collection_name=QDRANT_COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE)
        )

def index_chunks_to_qdrant(q_client: QdrantClient, chunks: list[dict]) -> float:
    """Indexes chunks to Qdrant and returns latency time in seconds."""
    start_time = time.time()
    init_qdrant_collection(q_client, force_recreate=True)

    points = []
    for chunk in chunks:
        vector = get_embedding(chunk["content"])
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk["chunk_id"]))
        
        payload = {
            "file": chunk["filename"],
            "department": chunk["department"],
            "source": chunk["source"],
            "contract": chunk.get("contract", "Unknown"),
            "clause": chunk.get("clause", "Unspecified"),
            "clause_title": chunk.get("clause_title"),
            "chunk_id": chunk["chunk_id"],
            "text": chunk["content"],
            "token_count": chunk.get("token_count", 0)
        }
        
        points.append(PointStruct(id=point_id, vector=vector, payload=payload))

    q_client.upsert(collection_name=QDRANT_COLLECTION_NAME, points=points)
    elapsed_time = round(time.time() - start_time, 2)
    return elapsed_time


def ensure_policy_index(q_client: QdrantClient) -> None:
    """Create the local policy collection and index it when it is missing."""
    collections = [collection.name for collection in q_client.get_collections().collections]
    if QDRANT_COLLECTION_NAME in collections:
        return

    documents = [
        {"filename": path.name, "content": path.read_text(encoding="utf-8")}
        for path in settings.POLICY_DIR.glob("*.txt")
    ]
    if not documents:
        return

    from services.chunking import process_documents

    chunks, _ = process_documents(documents)
    index_chunks_to_qdrant(q_client, chunks)

def search_qdrant(
    q_client: QdrantClient, 
    query: str, 
    department_filter: str | None = None, 
    doc_type_filter: str | None = None, 
    corporate_account: str | None = None,
    top_k: int = 5,
    policy_only: bool = True,
) -> tuple[list[dict], float]:
    """Runs query using query_points API with fallback to search API."""
    start_time = time.time()
    query_vector = get_embedding(query)
    
    must_conditions = []
    if department_filter and department_filter.upper() != "ALL":
        must_conditions.append(FieldCondition(key="department", match=MatchValue(value=department_filter)))
        
    if doc_type_filter and doc_type_filter.upper() != "ALL":
        must_conditions.append(FieldCondition(key="source", match=MatchValue(value=doc_type_filter)))
    elif policy_only:
        must_conditions.append(FieldCondition(key="source", match=MatchValue(value="SLA")))

    if corporate_account and corporate_account.upper() != "ALL":
        must_conditions.append(
            FieldCondition(key="contract", match=MatchValue(value=corporate_account.title()))
        )

    qdrant_filter = Filter(must=must_conditions) if must_conditions else None

    # Compatible with newer qdrant-client (>=1.12.0) and older versions
    if hasattr(q_client, "query_points"):
        response = q_client.query_points(
            collection_name=QDRANT_COLLECTION_NAME,
            query=query_vector,
            query_filter=qdrant_filter,
            limit=top_k
        )
        search_result = response.points
    else:
        search_result = q_client.search(
            collection_name=QDRANT_COLLECTION_NAME,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=top_k
        )

    elapsed_time = round(time.time() - start_time, 3)

    results = []
    for hit in search_result:
        results.append({
            "score": hit.score,
            "file": hit.payload.get("file"),
            "department": hit.payload.get("department"),
            "source": hit.payload.get("source"),
            "contract": hit.payload.get("contract"),
            "clause": hit.payload.get("clause", "Unspecified"),
            "clause_title": hit.payload.get("clause_title"),
            "chunk_id": hit.payload.get("chunk_id"),
            "content": hit.payload.get("text"),
            "token_count": hit.payload.get("token_count", 0)
        })

    return results, elapsed_time
