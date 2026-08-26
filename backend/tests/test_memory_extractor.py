from app.services.memory_extractor import extract_memories


def test_extract_name_memory():
    memories = extract_memories(
        "My name is Tom"
    )

    assert memories == [
        "User's name is Tom."
    ]


def test_extract_chinese_name_memory():
    memories = extract_memories(
        "我叫小明"
    )

    assert memories == [
        "User's name is 小明."
    ]


def test_extract_preference_memory():
    memories = extract_memories(
        "I like Python"
    )

    assert memories == [
        "User likes Python."
    ]


def test_extract_no_memory():
    memories = extract_memories(
        "What time is it?"
    )

    assert memories == []
