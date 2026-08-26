import re


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
    match = re.search(
        r"我叫\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)",
        text,
    )

    if match:
        name = match.group(1)

        memories.append(
            f"User's name is {name}."
        )

    # English: My name is Tom
    match = re.search(
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
    match = re.search(
        r"我喜欢\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)",
        text,
    )

    if match:
        preference = match.group(1)

        memories.append(
            f"User likes {preference}."
        )

    # English: I like Python
    match = re.search(
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
