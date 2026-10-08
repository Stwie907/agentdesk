import re


def _statement_match(pattern: str, text: str, flags: int = 0):
    """Skip questions/hypotheticals around the existing explicit fact patterns."""
    for match in re.finditer(pattern, text, flags):
        prefix = re.split(r"[,，.!?。！？;\n]", text[:match.start()])[-1].strip()
        if re.search(r"\b(what|which|who|where|when|why|how|whether|if)\b", prefix, re.IGNORECASE):
            continue
        if re.match(r"^(do|does|did|can|could|would|should|will|am|is|are)\b", prefix, re.IGNORECASE):
            continue
        if re.match(r"^[^,，.!?。！？;\n]*[?？]", text[match.end():]):
            continue
        if match.group(1) in {"什么", "什么名字", "什么呢", "什么吗"}:
            continue
        return match
    return None


def extract_memories(user_input: str) -> list[str]:
    """
    Extract simple long-term memories from user input.

    This first version uses deterministic rules so that:
    - tests are stable
    - CI does not require Ollama
    - memory writing behavior is predictable

    Later this can be upgraded to an LLM-based extractor.
    """

    memories = []

    text = user_input.strip()

    if not text:
        return memories

    # Chinese: 我叫 Tom
    match = _statement_match(
        r"我叫\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)",
        text,
    )

    if match:
        name = match.group(1)

        memories.append(
            f"User's name is {name}."
        )

    # English: My name is Tom
    match = _statement_match(
        r"\bmy name is\s+([A-Za-z0-9_\-]+)",
        text,
        re.IGNORECASE,
    )

    if match:
        name = match.group(1)

        memory = f"User's name is {name}."

        if memory not in memories:
            memories.append(memory)

    # Chinese: 我喜欢 Python
    match = _statement_match(
        r"我喜欢\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)",
        text,
    )

    if match:
        preference = match.group(1)

        memories.append(
            f"User likes {preference}."
        )

    # English: I like Python
    match = _statement_match(
        r"\bi like\s+([A-Za-z0-9_\-]+)",
        text,
        re.IGNORECASE,
    )

    if match:
        preference = match.group(1)

        memory = f"User likes {preference}."

        if memory not in memories:
            memories.append(memory)

    return memories
