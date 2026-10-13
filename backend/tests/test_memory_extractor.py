from app.services.memory_extractor import extract_memories
import pytest


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


@pytest.mark.parametrize("text", [
    "What do I like about Python?", "What do I like about Python",
    "Do I like Python?", "If I like Python, what should I learn?",
    "I like Python?", "我喜欢什么", "我喜欢什么吗？", "我叫什么名字？",
])
def test_questions_and_hypotheticals_do_not_create_facts(text):
    assert extract_memories(text) == []


def test_explicit_statements_in_mixed_messages_still_extract():
    assert extract_memories("Hi, my name is Tom. I like Python. What do I like about it?") == [
        "User's name is Tom.", "User likes Python.",
    ]
    assert extract_memories("我喜欢Python，请问现在几点？") == ["User likes Python."]
