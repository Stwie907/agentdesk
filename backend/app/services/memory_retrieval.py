"""Deterministic keyword ranking shared by Runtime and the read-only preview."""

from dataclasses import dataclass
import re
import unicodedata

from sqlalchemy.orm import Session

from app.crud.memory import get_memories_by_agent
from app.models.memory import Memory


STOP_WORDS = {
    "a", "an", "the", "is", "are", "am", "was", "were", "be", "been", "being",
    "do", "does", "did", "what", "which", "who", "whom", "where", "when", "why",
    "how", "to", "of", "in", "on", "at", "for", "from", "with", "about", "and", "or", "s",
}
CHINESE_STOP_PAIRS = {
    "用户", "我的", "我们", "你们", "关于", "什么", "如何", "喜欢", "偏好",
    "告诉", "请问", "知道", "我叫", "我喜", "我想",
}
CHINESE_STOP_CHARACTERS = set("我你他她它的了是在和与吗呢啊请")
HAN = r"[\u3400-\u4dbf\u4e00-\u9fff]"
TOKENS = re.compile(r"[a-z0-9_]+(?:[.'-][a-z0-9_]+)*(?:\+\+|#)?|" + HAN + "+")


@dataclass(frozen=True)
class MemoryMatch:
    memory: Memory
    score: int
    matched_terms: tuple[str, ...]


def tokenize_memory_text(text: str, *, include_single_chinese: bool = False) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold().replace("\u2019", "'")
    terms = set()
    for token in TOKENS.findall(normalized):
        if re.fullmatch(HAN + "+", token):
            if len(token) == 1 or include_single_chinese:
                terms.update(char for char in token if char not in CHINESE_STOP_CHARACTERS)
            terms.update(token[index:index + 2] for index in range(len(token) - 1)
                         if token[index:index + 2] not in CHINESE_STOP_PAIRS)
        elif token not in STOP_WORDS:
            terms.add(token)
    return terms


def rank_agent_memories(db: Session, agent_id: int, query: str, limit: int = 5) -> list[MemoryMatch]:
    if limit <= 0:
        return []
    query_terms = tokenize_memory_text(query)
    if not query_terms:
        return []
    include_single = any(re.fullmatch(HAN, term) for term in query_terms)
    matches = []
    for memory in get_memories_by_agent(db, agent_id):
        content_terms = tokenize_memory_text(memory.content, include_single_chinese=include_single)
        overlap = tuple(sorted(query_terms & content_terms))
        if overlap:
            matches.append(MemoryMatch(memory, len(overlap), overlap))
    matches.sort(key=lambda match: (match.score, match.memory.id), reverse=True)
    return matches[:limit]
