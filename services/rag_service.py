from __future__ import annotations
import time
from openai import OpenAI
from config.settings import OPENAI_API_KEY, LLM_MODEL
from services.qdrant_service import ensure_policy_index, get_qdrant_client, search_qdrant

client = OpenAI(api_key=OPENAI_API_KEY)

def generate_rag_answer(user_query: str, retrieved_chunks: list[dict], user_info: dict) -> tuple[str, float]:
    """
    Sends retrieved document chunks as context to OpenAI to synthesize a direct answer.
    Returns (answer_text, elapsed_response_time).
    """
    start_time = time.time()

    if not retrieved_chunks:
        return "I could not verify this answer from the retrieved corporate policy contract.", 0.0

    context_str = ""
    for idx, chunk in enumerate(retrieved_chunks, 1):
        source = chunk.get("file") or chunk.get("filename", "Unknown")
        contract = chunk.get("contract", "Unknown contract")
        clause = chunk.get("clause", "Unspecified")
        context_str += f"\n[Document {idx} | Contract: {contract} | Source: {source} | {clause}]\n"
        context_str += f"{chunk['content']}\n"

    system_prompt = (
        "You are an AI Enterprise  Corporate SLA & Policy Master. Your job is to ground all policy eligibility checks and HR benefit answers strictly in the retrieved corporate contract.\n\n"
        "Guidelines:\n"
        "1. Base your response ONLY on the provided context chunks.\n"
        "2. If the context does not contain enough information, state that clearly.\n"
        "3. Keep your tone professional, concise, and direct.\n"
        "4. Address the employee appropriately using their role if relevant.\n"
        "5. Cite every eligibility, limit, waiting-period, or deadline claim using exactly "
        "[Source: <filename> | Clause: <Clause X.Y>]. Use only clause references present in context.\n"
        "6. If the contract does not answer the question, do not infer or generalize."
    )

    user_prompt = (
        f"Employee Profile: {user_info.get('name', 'Employee')} "
        f"({user_info.get('role', 'Employee')} - {user_info.get('dept', 'General')})\n\n"
        f"Context Documents:\n{context_str}\n\n"
        f"Employee Question: {user_query}\n\n"
        f"Provide a helpful answer:"
    )

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2
    )

    elapsed_time = round(time.time() - start_time, 2)
    answer = response.choices[0].message.content.strip()

    return answer, elapsed_time


def answer_from_retrieved_chunks(
    user_query: str,
    retrieved_chunks: list[dict],
    user_info: dict | None = None,
) -> tuple[str, float]:
    """Generate a contract-grounded answer without choosing a vector backend."""
    return generate_rag_answer(user_query, retrieved_chunks, user_info or {})


def find_sla_reference(retrieved_chunks: list[dict], keyword: str) -> str | None:
    """Return an exact citation for the retrieved clause containing keyword."""
    normalized_keyword = keyword.lower()
    for chunk in retrieved_chunks:
        content = str(chunk.get("content", "")).lower()
        clause = str(chunk.get("clause", "")).strip()
        if normalized_keyword not in content and normalized_keyword not in clause.lower():
            continue
        filename = chunk.get("filename") or chunk.get("file")
        if filename and clause and clause.lower() != "unspecified":
            return f"[Source: {filename} | Clause: {clause}]"
    return None


def answer_policy_query(
    user_query: str,
    user_info: dict | None = None,
    *,
    q_client=None,
    corporate_account: str | None = None,
    top_k: int = 5,
) -> tuple[str, list[dict], float, float]:
    """Retrieve only corporate SLA clauses and answer with their citations.

    Returns ``(answer, retrieved_chunks, retrieval_seconds, generation_seconds)``.
    """
    client_for_search = q_client or get_qdrant_client()
    ensure_policy_index(client_for_search)
    chunks, retrieval_time = search_qdrant(
        client_for_search,
        user_query,
        corporate_account=corporate_account,
        top_k=top_k,
        policy_only=True,
    )
    answer, generation_time = generate_rag_answer(user_query, chunks, user_info or {})
    return answer, chunks, retrieval_time, generation_time
