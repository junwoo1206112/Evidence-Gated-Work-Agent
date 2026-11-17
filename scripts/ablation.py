"""Small, honest retrieval ablation over the checked-in demo corpus.

This is not a benchmark. It isolates two design choices on 18 hand-written
queries: Korean particle stripping and syllable bigrams. The same corpus and
gold document IDs are used for every variant.
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.corpus import load_corpus
from app.services.retrieval import STOPWORDS, Retriever, korean_bigrams, strip_particle
from app.textutil import words

CORPUS_PATH = ROOT / "data" / "public_corpus" / "documents.json"
OUTPUT = ROOT / "docs" / "retrieval-ablation.md"

QUERIES = [
    ("계약보증금 징수 기준", ["pps-facility-contract-guarantee"]),
    ("지연배상금 산정", ["pps-facility-contract-delay"]),
    ("물가변동 사전검토 자료", ["pps-price-change"]),
    ("입찰참가자격 등록 서류", ["pps-registration-team"]),
    ("비축물자 공급 신청", ["pps-stockpile-operation"]),
    ("외자구매 입찰 절차", ["pps-foreign-purchase"]),
    ("적격심사 평가 항목", ["pps-facility-qualification"]),
    ("설계공모 심사위원", ["pps-design-competition"]),
    ("안전점검 수행기관 지정", ["pps-facility-safety"]),
    ("가격조사 예정가격", ["pps-price-survey"]),
    (
        "물품 계약보증금 비율",
        ["fixture-goods-guarantee-10", "fixture-goods-guarantee-5"],
    ),
    ("무효 URL 테스트 조항", ["fixture-missing-url"]),
    (
        "계약보증금과 지연배상금을 확인",
        ["pps-facility-contract-guarantee", "pps-facility-contract-delay"],
    ),
    ("물가변동으로", ["pps-price-change"]),
    ("비축물자의 공급을", ["pps-stockpile-operation"]),
    ("외자구매를", ["pps-foreign-purchase"]),
    ("설계공모를", ["pps-design-competition"]),
    ("안전점검을", ["pps-facility-safety"]),
]


def base_terms(query: str, *, strip: bool) -> list[str]:
    terms: list[str] = []
    for token in words(query):
        if len(token) < 2:
            continue
        if strip:
            token = strip_particle(token)
        if len(token) < 2 or token in STOPWORDS:
            continue
        if token not in terms:
            terms.append(token)
    return terms


def bm25_rank(corpus, query: str, *, strip: bool, bigrams: bool, top_k: int = 5) -> list[str]:
    def tokens(text: str) -> list[str]:
        result: list[str] = []
        for token in words(text):
            if len(token) < 2:
                continue
            result.append(token)
            if bigrams:
                result.extend(korean_bigrams(token))
        return result

    docs = list(corpus.documents)
    texts = [f"{doc.title} {doc.section} {doc.content}" for doc in docs]
    doc_tokens = [tokens(text) for text in texts]
    counts = [Counter(item) for item in doc_tokens]
    lengths = [len(item) for item in doc_tokens]
    avg = sum(lengths) / max(len(lengths), 1)
    total = len(docs)

    query_terms = base_terms(query, strip=strip)
    query_tokens: list[str] = []
    for term in query_terms:
        query_tokens.append(term)
        if bigrams:
            query_tokens.extend(korean_bigrams(term))
    df = Counter(token for item in doc_tokens for token in set(item))
    scores: list[tuple[float, str]] = []
    for index, doc in enumerate(docs):
        score = 0.0
        for term in set(query_tokens):
            frequency = counts[index][term]
            if frequency == 0:
                continue
            idf = math.log(1 + (total - df[term] + 0.5) / (df[term] + 0.5))
            length = lengths[index]
            score += idf * frequency * 2.5 / (frequency + 1.5 * (1 - 0.75 + 0.75 * length / max(avg, 1)))
        if score > 0:
            scores.append((score, doc.document_id))
    scores.sort(key=lambda item: (-item[0], item[1]))
    return [document_id for _, document_id in scores[:top_k]]


def current_rank(corpus, query: str, top_k: int = 5) -> list[str]:
    retriever = Retriever(corpus)
    return [hit.document.document_id for hit in retriever.search(query, top_k)]


def score(ranked: list[str], gold: list[str], k: int = 3) -> tuple[float, float]:
    top = ranked[:k]
    recall = sum(1 for item in gold if item in top) / max(len(gold), 1)
    reciprocal = 0.0
    for index, item in enumerate(top, start=1):
        if item in gold:
            reciprocal = 1.0 / index
            break
    return recall, reciprocal


def main() -> int:
    corpus = load_corpus(
        CORPUS_PATH,
        allowed_hosts=("law.go.kr", "www.law.go.kr", "example.com"),
        min_excerpt_chars=40,
    )
    variants = {
        "word_exact": lambda query: bm25_rank(corpus, query, strip=False, bigrams=False),
        "particle": lambda query: bm25_rank(corpus, query, strip=True, bigrams=False),
        "particle+bigram (current)": lambda query: current_rank(corpus, query),
    }
    rows = []
    totals = {name: [0.0, 0.0] for name in variants}
    for query, gold in QUERIES:
        row = {"query": query, "gold": ", ".join(gold)}
        for name, ranker in variants.items():
            ranked = ranker(query)
            recall, reciprocal = score(ranked, gold)
            totals[name][0] += recall
            totals[name][1] += reciprocal
            row[name] = (recall, reciprocal, ranked[:3])
        rows.append(row)

    lines = [
        "# 한국어 검색 소규모 ablation",
        "",
        f"> {len(QUERIES)}개 수작업 질의·동일 코퍼스·동일 gold 문서 ID. 성능 벤치마크가 아니라 설계 선택의 회귀 근거다.",
        "",
        f"- 코퍼스: `{CORPUS_PATH.name}` (14문서, SHA-256 `{corpus.sha256}`)",
        "- 지표: Recall@3, MRR@3",
        "- `word_exact`: 조사 제거 없음, 단어 BM25만",
        "- `particle`: 조사 제거, 단어 BM25만",
        "- `particle+bigram (current)`: 조사 제거 + 음절 bigram BM25 + 절대 coverage",
        "",
        "## 요약",
        "",
        "| 변형 | Recall@3 | MRR@3 |",
        "|---|---:|---:|",
    ]
    for name, (recall, mrr) in totals.items():
        lines.append(f"| {name} | {recall / len(QUERIES):.3f} | {mrr / len(QUERIES):.3f} |")

    lines.extend(["", "## 질의별 결과", "", "| 질의 | gold | word_exact | particle | current |", "|---|---|---|---|---|"])
    for row in rows:
        def cell(name: str) -> str:
            recall, mrr, top = row[name]
            return f"R@3={recall:.2f}, MRR={mrr:.2f}<br>`{', '.join(top)}`"

        lines.append(
            f"| {row['query']} | {row['gold']} | {cell('word_exact')} | {cell('particle')} | {cell('particle+bigram (current)')} |"
        )

    lines.extend(
        [
            "",
            "## 해석과 한계",
            "",
            "- 이 표는 같은 14문서 안에서 두 구현 선택이 gold 문서를 top-3에 올리는지 비교한 것이다.",
            "- 코퍼스가 작아 ID/paths가 기억되기 쉽고, 실제 조달 질의 분포를 대표하지 않는다.",
            f"- `particle+bigram`은 조사가 붙은 한국어 질의에서 단어 exact match보다 높은 Recall을 보이도록 설계했지만, 이 {len(QUERIES)}개 질의에서는 차이가 작을 수 있다.",
            "- LLM/RAG 품질, 문서 수가 큰 환경의 성능, 법적 정확성을 주장하지 않는다.",
        ]
    )
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")
    for name, (recall, mrr) in totals.items():
        print(f"{name}: Recall@3={recall / len(QUERIES):.3f} MRR@3={mrr / len(QUERIES):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
