from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from app.services.corpus import Corpus, CorpusDocument
from app.textutil import korean_bigrams, normalize_text, words

# Grammatical particles and request-only verbs. Content words such as "계약",
# "보증금", "이행" are deliberately kept so the coverage score cannot be
# inflated by removing too much of the query.
STOPWORDS = frozenset(
    {
        "및",
        "의",
        "를",
        "을",
        "에",
        "에서",
        "와",
        "과",
        "로",
        "으로",
        "가",
        "이",
        "은",
        "는",
        "도",
        "만",
        "대한",
        "관련",
        "해줘",
        "해주세요",
        "알려줘",
        "부탁해",
        "정리해",
        "확인해",
        "작성해",
        "준비해",
        "정리해줘",
        "확인해줘",
        "작성해줘",
        "준비해줘",
        "초안",
        "작성",
        "알림",
        "준비",
        "통보",
        "공지",
        "메일",
        "문서",
        "공문",
        "보고서",
        "확인",
        "정리",
        "것",
        "수",
        "등",
        "그",
        "저",
    }
)

# Longest first so "으로" wins over "로" and "에서" over "에".
_PARTICLES = (
    "으로",
    "에서",
    "에게",
    "까지",
    "부터",
    "보다",
    "처럼",
    "만큼",
    "이라",
    "라고",
    "이다",
    "을",
    "를",
    "은",
    "는",
    "이",
    "가",
    "과",
    "와",
    "로",
    "에",
    "의",
    "도",
    "만",
)


def strip_particle(token: str) -> str:
    if not token or not token[0].isalpha():
        return token
    for suffix in _PARTICLES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            return token[: -len(suffix)]
    return token


@dataclass(frozen=True)
class RetrievalHit:
    document: CorpusDocument
    score: float
    coverage: float
    bm25: float
    matched_terms: tuple[str, ...]


class Retriever:
    """Deterministic Korean-aware lexical retrieval.

    Scoring is absolute (not min-max normalized) so a thin corpus cannot make
    every candidate look perfect:

    - coverage: IDF-weighted share of query terms that match the document
    - bm25: standard BM25 over words + Korean syllable bigrams, squashed to 0..1
    - score: 0.85 * coverage + 0.15 * bm25_signal
    """

    def __init__(self, corpus: Corpus) -> None:
        self.corpus = corpus
        self._docs: list[CorpusDocument] = list(corpus.documents)
        self._texts = [normalize_text(f"{doc.title} {doc.section} {doc.content}") for doc in self._docs]
        self._tokens = [self._tokenize_for_index(text) for text in self._texts]
        self._token_counts = [Counter(tokens) for tokens in self._tokens]
        self._lengths = [len(tokens) for tokens in self._tokens]
        self._avg_length = sum(self._lengths) / max(len(self._lengths), 1)
        self._df_tokens: Counter[str] = Counter(
            token for tokens in self._tokens for token in set(tokens)
        )
        self._doc_token_sets = [set(tokens) for tokens in self._tokens]

    @staticmethod
    def _tokenize_for_index(text: str) -> list[str]:
        tokens: list[str] = []
        for token in words(text):
            if len(token) < 2:
                continue
            tokens.append(token)
            tokens.extend(korean_bigrams(token))
        return tokens

    @staticmethod
    def query_terms(query: str) -> list[str]:
        terms: list[str] = []
        for token in words(query):
            if len(token) < 2:
                continue
            token = strip_particle(token)
            if len(token) < 2 or token in STOPWORDS:
                continue
            if token not in terms:
                terms.append(token)
        return terms

    def _matches(self, term: str, doc_index: int) -> bool:
        text = self._texts[doc_index]
        if term in text:
            return True
        # Query words often carry a particle ("계약보증금과"). A document word
        # that is a substring of the query word is a match, but single-syllable
        # document words are excluded to avoid the classic "제" false positive.
        return any(len(token) >= 2 and token in term for token in self._doc_token_sets[doc_index])

    def _idf(self, term: str) -> float:
        df = sum(1 for index in range(len(self._docs)) if self._matches(term, index))
        total = max(len(self._docs), 1)
        return math.log(1 + (total - df + 0.5) / (df + 0.5))

    def _bm25(self, query_tokens: list[str], doc_index: int) -> float:
        k1, b = 1.5, 0.75
        counts = self._token_counts[doc_index]
        length = self._lengths[doc_index]
        total = max(len(self._docs), 1)
        score = 0.0
        for term in set(query_tokens):
            frequency = counts[term]
            if frequency == 0:
                continue
            df = self._df_tokens[term]
            idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
            denominator = frequency + k1 * (1 - b + b * length / max(self._avg_length, 1))
            score += idf * frequency * (k1 + 1) / denominator
        return score

    def search(self, query: str, top_k: int = 5) -> list[RetrievalHit]:
        terms = self.query_terms(query)
        if not terms:
            return []

        total_idf = sum(self._idf(term) for term in terms) or 1.0
        query_tokens = self._tokenize_for_index(query)
        hits: list[RetrievalHit] = []
        for index, doc in enumerate(self._docs):
            matched = tuple(term for term in terms if self._matches(term, index))
            if not matched:
                continue
            coverage = sum(self._idf(term) for term in matched) / total_idf
            bm25 = self._bm25(query_tokens, index)
            bm25_signal = min(1.0, bm25 / 12.0)
            score = round(0.85 * coverage + 0.15 * bm25_signal, 4)
            hits.append(
                RetrievalHit(
                    document=doc,
                    score=score,
                    coverage=round(coverage, 4),
                    bm25=round(bm25, 4),
                    matched_terms=matched,
                )
            )

        hits.sort(key=lambda hit: (-hit.score, -hit.coverage, hit.document.document_id))
        return hits[: max(1, top_k)]
