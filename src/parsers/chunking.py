"""Text chunking utilities."""


def sliding_window_chunks(
    text: str,
    chunk_size: int = 2000,
    overlap: int = 250,
) -> list[str]:
    """Split text into overlapping chunks of ~chunk_size chars.

    Args:
        text: The input text to chunk.
        chunk_size: Target size of each chunk in characters (default 2000, ~512 tokens).
        overlap: Number of characters to overlap between consecutive chunks (default 250, ~64 tokens).

    Returns:
        List of text chunks.
    """
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    step = chunk_size - overlap

    if step <= 0:
        raise ValueError(
            f"overlap ({overlap}) must be strictly less than chunk_size ({chunk_size})"
        )

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]
        chunks.append(chunk)
        start += step

    return chunks


def paragraph_chunks(
    paragraphs: list[str],
    chunk_size: int = 2000,
    overlap: int = 250,
) -> list[str]:
    """Group paragraphs into chunks, each ~chunk_size chars, with overlap.

    Args:
        paragraphs: List of paragraph strings.
        chunk_size: Target chunk size in characters.
        overlap: Overlap in characters (carried from end of previous chunk).

    Returns:
        List of merged paragraph groups as chunks.
    """
    if not paragraphs:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    carry = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_len = len(para)
        if current_len + para_len + 1 > chunk_size and current:
            text = carry + "\n\n".join(current)
            chunks.append(text)
            # Carry overlap: last ~overlap chars as prefix for next chunk
            if len(text) > overlap:
                carry = text[-overlap:] + "\n\n"
            else:
                carry = text + "\n\n"
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len + 1

    if current:
        text = carry + "\n\n".join(current)
        chunks.append(text)

    # Fallback: if chunks is empty but we have text, use sliding window
    if not chunks and paragraphs:
        joined = "\n".join(p.strip() for p in paragraphs if p.strip())
        chunks = sliding_window_chunks(joined, chunk_size, overlap)

    return chunks
