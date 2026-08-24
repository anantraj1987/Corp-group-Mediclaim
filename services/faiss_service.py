from __future__ import annotations
import json
import faiss
import numpy as np
from pathlib import Path
from openai import OpenAI
from config.settings import OPENAI_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIMENSION, FAISS_DIR

client = OpenAI(api_key=OPENAI_API_KEY)

INDEX_FILE = FAISS_DIR / "index.faiss"
METADATA_FILE = FAISS_DIR / "metadata.json"

def get_embedding(text: str) -> list[float]:
    """
    Fetches embedding vector from OpenAI API.
    """
    text = text.replace("\n", " ")
    response = client.embeddings.create(
        input=[text],
        model=EMBEDDING_MODEL
    )
    return response.data[0].embedding

def build_faiss_index(chunks: list[dict]) -> tuple[faiss.Index, list[dict]]:
    """
    Generates embeddings for all chunks, constructs a FAISS IndexFlatIP, and saves to disk.
    """
    FAISS_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"\n⏳ Generating embeddings for {len(chunks)} chunk(s) via OpenAI...")
    embeddings = []
    metadata = []

    for chunk in chunks:
        vector = get_embedding(chunk["content"])
        embeddings.append(vector)
        metadata.append({
            "filename": chunk["filename"],
            "content": chunk["content"],
            "source": chunk.get("source", "SLA"),
            "contract": chunk.get("contract", "Unknown contract"),
            "clause": chunk.get("clause", "Unspecified"),
            "clause_title": chunk.get("clause_title"),
            "documentType": chunk.get("documentType", ""),
            "corporateAccount": chunk.get("corporateAccount", ""),
        })

    # Convert vectors to float32 numpy array
    vectors_np = np.array(embeddings, dtype=np.float32)

    # Normalize vectors to L2 unit length so Inner Product equals Cosine Similarity
    faiss.normalize_L2(vectors_np)

    # Create IndexFlatIP (Inner Product)
    index = faiss.IndexFlatIP(EMBEDDING_DIMENSION)
    index.add(vectors_np)

    # Save Index and Metadata to disk
    faiss.write_index(index, str(INDEX_FILE))
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"✅ FAISS Index created with {index.ntotal} vectors!")
    print(f"💾 Index saved to: {INDEX_FILE}\n")
    return index, metadata

def load_faiss_index() -> tuple[faiss.Index | None, list[dict]]:
    """
    Loads saved FAISS index and metadata mapping from disk if present.
    """
    if not INDEX_FILE.exists() or not METADATA_FILE.exists():
        return None, []

    index = faiss.read_index(str(INDEX_FILE))
    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    return index, metadata

def search_faiss(
    query: str,
    index: faiss.Index,
    metadata: list[dict],
    top_k: int = 5,
    corporate_account: str | None = None,
) -> list[dict]:
    """
    Converts query string to vector, runs Top-K search in FAISS, and maps back to text chunks.
    """
    query_vector = get_embedding(query)
    query_np = np.array([query_vector], dtype=np.float32)
    faiss.normalize_L2(query_np)

    # Search a wider candidate set when filtering by corporate.
    search_k = min(index.ntotal, max(top_k * 5, top_k))
    distances, indices = index.search(query_np, search_k)

    results = []
    for score, idx in zip(distances[0], indices[0]):
        if idx != -1 and idx < len(metadata):
            meta = metadata[idx]
            if corporate_account and corporate_account.lower() not in meta.get("contract", "").lower():
                continue
            results.append({
                "filename": meta["filename"],
                "score": float(score),
                "content": meta["content"],
                "source": meta.get("source", "SLA"),
                "contract": meta.get("contract", "Unknown contract"),
                "clause": meta.get("clause", "Unspecified"),
                "clause_title": meta.get("clause_title"),
            })

    return results
