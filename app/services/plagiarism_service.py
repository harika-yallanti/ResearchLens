
import os
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from dotenv import load_dotenv


load_dotenv()

OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY")

OPENALEX_BASE_URL = "https://api.openalex.org"


def reconstruct_abstract(inverted_index):
    if not inverted_index:
        return ""

    words = []

    for word, positions in inverted_index.items():
        for position in positions:
            words.append((position, word))

    words.sort(key=lambda item: item[0])

    return " ".join(word for _, word in words)


def search_openalex(query, per_page=5):
    if not OPENALEX_API_KEY:
        raise RuntimeError(
            "OPENALEX_API_KEY is missing from the .env file."
        )

    if not query or not query.strip():
        return []

    params = {
        "search": query.strip(),
        "per_page": min(max(per_page, 1), 10),
        "select": (
            "id,doi,title,publication_year,"
            "open_access,abstract_inverted_index,type"
        ),
    }

    url = (
        f"{OPENALEX_BASE_URL}/works?"
        f"{urlencode(params)}"
    )

    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {OPENALEX_API_KEY}",
            "Accept": "application/json",
            "User-Agent": "ResearchLens/1.0",
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))

        results = []

        for work in data.get("results", []):
            abstract = reconstruct_abstract(
                work.get("abstract_inverted_index")
            )

            open_access = work.get("open_access") or {}

            results.append({
                "openalex_id": work.get("id"),
                "title": work.get("title"),
                "doi": work.get("doi"),
                "publication_year": work.get("publication_year"),
                "abstract": abstract,
                "is_open_access": open_access.get("is_oa", False),
                "type": work.get("type"),
            })

        return results

    except HTTPError as error:
        if error.code == 403:
            raise RuntimeError(
                "OpenAlex rejected the API key. "
                "Check whether your key is activated."
            ) from error

        if error.code == 401:
            raise RuntimeError(
                "OpenAlex API key is invalid."
            ) from error

        if error.code == 429:
            raise RuntimeError(
                "OpenAlex rate limit reached. Try again later."
            ) from error

        raise RuntimeError(
            f"OpenAlex API request failed with status {error.code}."
        ) from error

    except URLError as error:
        raise RuntimeError(
            "Could not connect to OpenAlex. Check your internet connection."
        ) from error

    except TimeoutError as error:
        raise RuntimeError(
            "OpenAlex request timed out. Please try again."
        ) from error


import re
from collections import Counter


def clean_text(text):
    if not text:
        return ""

    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def create_passages(text, passage_size=100, overlap=30):
    words = text.split()

    if not words:
        return []

    passages = []
    step = passage_size - overlap

    for start in range(0, len(words), step):
        passage_words = words[start:start + passage_size]

        if len(passage_words) < 20:
            continue

        passages.append(" ".join(passage_words))

        if start + passage_size >= len(words):
            break

    return passages


def create_ngrams(text, n=4):
    words = clean_text(text).split()

    if len(words) < n:
        return Counter()

    return Counter(
        tuple(words[index:index + n])
        for index in range(len(words) - n + 1)
    )


def calculate_similarity(text1, text2):
    ngrams1 = create_ngrams(text1)
    ngrams2 = create_ngrams(text2)

    if not ngrams1 or not ngrams2:
        return 0.0, 0

    common = ngrams1 & ngrams2
    common_count = sum(common.values())

    total_unique = len(set(ngrams1) | set(ngrams2))

    if total_unique == 0:
        return 0.0, 0

    similarity = (
        len(set(ngrams1) & set(ngrams2))
        / total_unique
    ) * 100

    return round(similarity, 2), common_count


def get_search_queries(title, abstract, keywords, passages):
    queries = []
    seen = set()

    candidates = []

    if title:
        candidates.append(title)

    if abstract:
        sentences = re.split(r"(?<=[.!?])\s+", abstract)

        candidates.extend(sentences[:2])

    if keywords:
        if isinstance(keywords, list):
            candidates.append(" ".join(keywords))
        else:
            candidates.append(str(keywords))

    candidates.extend(passages[:2])

    for candidate in candidates:
        cleaned = " ".join(candidate.split())

        if len(cleaned) < 15:
            continue

        cleaned = cleaned[:250]
        normalized = cleaned.casefold()

        if normalized not in seen:
            queries.append(cleaned)
            seen.add(normalized)

        if len(queries) == 4:
            break

    return queries


def check_paper_similarity(
    paper_text,
    title=None,
    abstract=None,
    keywords=None,
):
    if not paper_text or len(paper_text.split()) < 30:
        raise ValueError(
            "The uploaded paper does not contain enough text "
            "for similarity checking."
        )

    passages = create_passages(paper_text)

    queries = get_search_queries(
        title,
        abstract,
        keywords,
        passages,
    )

    if not queries:
        raise ValueError(
            "Could not create search queries from the paper."
        )

    discovered_sources = {}

    for query in queries:
        results = search_openalex(
            query,
            per_page=5,
        )

        for source in results:
            source_id = source.get("openalex_id")

            if source_id:
                discovered_sources[source_id] = source

    comparable_sources = []
    matched_passages = []

    for source in discovered_sources.values():
        source_abstract = source.get("abstract", "")

        if len(source_abstract.split()) < 20:
            continue

        best_similarity = 0.0
        best_passage = ""
        best_common_count = 0

        for passage in passages:
            similarity, common_count = calculate_similarity(
                passage,
                source_abstract,
            )

            if similarity > best_similarity:
                best_similarity = similarity
                best_passage = passage
                best_common_count = common_count

        comparable_sources.append({
            "title": source.get("title"),
            "doi": source.get("doi"),
            "openalex_id": source.get("openalex_id"),
            "publication_year": source.get("publication_year"),
            "similarity": best_similarity,
            "is_open_access": source.get("is_open_access"),
        })

        if best_similarity >= 5 and best_common_count >= 3:
            matched_passages.append({
                "source_title": source.get("title"),
                "source_doi": source.get("doi"),
                "similarity": best_similarity,
                "matched_text": best_passage[:1200],
                "source_abstract_excerpt": source_abstract[:1200],
            })

    comparable_sources.sort(
        key=lambda item: item["similarity"],
        reverse=True,
    )

    matched_passages.sort(
        key=lambda item: item["similarity"],
        reverse=True,
    )

    highest_similarity = (
        comparable_sources[0]["similarity"]
        if comparable_sources
        else 0.0
    )

    return {
        "status": "completed",
        "similarity_score": highest_similarity,
        "plagiarism_summary": (
            f"Compared the uploaded paper against "
            f"{len(comparable_sources)} OpenAlex records "
            f"with accessible abstracts. "
            f"{len(matched_passages)} potential text-overlap "
            f"matches were identified."
        ),
        "similarity_sources": comparable_sources,
        "matched_passages": matched_passages,
        "sources_checked": len(comparable_sources),
        "sources_discovered": len(discovered_sources),
        "comparison_type": "abstract_based",
    }
