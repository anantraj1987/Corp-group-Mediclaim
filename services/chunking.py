from __future__ import annotations
import re
import tiktoken
from services.qdrant_service import infer_metadata
# Initialize tokenizer for text-embedding-3-small
tokenizer = tiktoken.get_encoding("cl100k_base")
CLAUSE_PATTERN = re.compile(r"\bClause\s+([0-9]+(?:\.[0-9]+)*)\b(?:\s+-\s+([^\n]+))?", re.IGNORECASE)

def count_tokens(text: str) -> int:
    """Returns exact token count for string using OpenAI tokenizer."""
    return len(tokenizer.encode(text))


# --- Recursive Character Chunking, tuned for clause-structured GMC documents ---
class RecursiveChunker:
    """Splits GMC master wordings, endorsement schedules, and HR rulebooks along their
    natural clause/section boundaries, falling back to smaller separators only when a
    section still exceeds chunk_size."""


    # Ordered from most to least semantically meaningful boundary.
    DEFAULT_SEPARATORS = ["\n\nClause ", "\n\n", "\n", ". ", " ", ""]

        
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150,
                 separators: list[str] | None = None):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or self.DEFAULT_SEPARATORS

    def chunk(self, text: str) -> list[str]:
        raw_chunks = self._split_text(text.strip(), self.separators)
        merged = self._merge_with_overlap(raw_chunks)
        return [c.strip() for c in merged if c.strip()]

    def _split_text(self, text: str, separators: list[str]) -> list[str]:
        if not text:
            return []

        separator = separators[-1]
        remaining_separators = separators
        for i, s in enumerate(separators):
            if s == "" or s in text:
                separator = s
                remaining_separators = separators[i:]
                break

        splits = text.split(separator) if separator != "" else list(text)
        final_chunks = []
        good_splits = []

        for s in splits:
            if len(s) < self.chunk_size:
                good_splits.append(s)
                continue
            if good_splits:
                final_chunks.append(separator.join(good_splits))
                good_splits = []
            if remaining_separators[1:]:
                final_chunks.extend(self._split_text(s, remaining_separators[1:]))
            else:
                final_chunks.append(s)

        if good_splits:
            final_chunks.append(separator.join(good_splits))

        return final_chunks

    def _merge_with_overlap(self, chunks: list[str]) -> list[str]:
        """Re-merges adjacent small chunks up to chunk_size, carrying chunk_overlap
        characters of trailing context forward so clause references aren't split blind."""
        merged: list[str] = []
        buffer = ""

        for chunk in chunks:
            candidate = f"{buffer}\n\n{chunk}" if buffer else chunk
            if len(candidate) <= self.chunk_size or not buffer:
                buffer = candidate
            else:
                merged.append(buffer)
                overlap_tail = buffer[-self.chunk_overlap:] if self.chunk_overlap else ""
                buffer = f"{overlap_tail}\n\n{chunk}" if overlap_tail else chunk

        if buffer:
            merged.append(buffer)

        return merged

def process_documents(
    documents: list[dict],
    chunk_size: int = 800,
    chunk_overlap: int = 150,
) -> tuple[list[dict], dict]:
    """Recursively chunks GMC master wordings, endorsement schedules, and HR
    rulebooks, returning enriched chunks plus aggregate metrics."""
    chunker = RecursiveChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    all_chunks = []

    for doc in documents:
        raw_text = doc["content"]
        meta_info = infer_metadata(doc["filename"])
        # Keep each contract clause together so retrieval metadata identifies the
        # clause that actually contains the answer.
        clause_sections = re.split(r"(?=\n\nClause\s+[0-9]+(?:\.[0-9]+)*)", raw_text.strip(), flags=re.IGNORECASE)
        text_chunks = []
        for section in clause_sections:
            text_chunks.extend(chunker.chunk(section))

        for idx, chunk_text in enumerate(text_chunks):
            clause_match = CLAUSE_PATTERN.search(chunk_text)
            clause_number = clause_match.group(1) if clause_match else None
            clause_title = clause_match.group(2).strip() if clause_match and clause_match.group(2) else None
            all_chunks.append({
                "chunk_id": f"{doc['filename']}_recursive_{idx}",
                "filename": doc["filename"],
                "content": chunk_text,
                "source": meta_info["source_data"],
                "department": meta_info["department"],
                "contract": meta_info["contract"],
                "clause": f"Clause {clause_number}" if clause_number else "Unspecified",
                "clause_title": clause_title,
                "token_count": count_tokens(chunk_text)
            })

    total_chunks = len(all_chunks)
    total_tokens = sum(c["token_count"] for c in all_chunks)
    avg_tokens = (total_tokens / total_chunks) if total_chunks > 0 else 0

    metrics = {
        "strategy": "Recursive",
        "total_chunks": total_chunks,
        "total_tokens": total_tokens,
        "avg_tokens_per_chunk": round(avg_tokens, 2),
        "chunk_size_setting": chunk_size,
        "overlap_setting": chunk_overlap,
    }

    return all_chunks, metrics
