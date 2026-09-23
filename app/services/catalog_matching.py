import re
import unicodedata
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher


ALGORITHM_VERSION = "lexical-v1.2.1"
BRAND_ALIAS_KEYS = {
    "new elfin": "elfin",
    "new elfin srl": "elfin",
    "elfin srl": "elfin",
}
STOPWORDS = {
    "para", "com", "sem", "por", "uma", "das", "dos", "produto", "industrial",
    "modulo", "modular", "sistema", "serie", "modelo", "unidade", "kit", "the",
    "and", "from", "automation", "automacao", "eletrico", "eletrica",
}
MEASUREMENT_TOKEN = re.compile(
    r"^(?:ip\d{2,3}[a-z]?|\d+(?:[.,]\d+)?(?:v(?:cc|ca|dc|ac|cacc|acdc)?|a|w|kw|kvar|ma|m|mm|cm|hz|khz|mhz|db|gb|mb|tb|pol))$"
)
COMPOSITE_MEASUREMENT_TOKEN = re.compile(
    r"^(?:\d+(?:x\d+)+(?:mm|cm|m)?|m\d+x\d+(?:[.,]\d+)?|\d+v(?:cc|ca|dc|ac|cacc)?\d+a)$"
)
GENERIC_MODEL_TOKENS = {"ethernet", "modbus", "profinet", "profibus", "rs232", "rs485"}


@dataclass(frozen=True)
class MatchOffer:
    id: uuid.UUID
    company_id: uuid.UUID
    company_code: str
    company_name: str
    external_code: str
    name: str
    brand: str | None
    manufacturer_code: str | None
    reference: str | None
    description: str | None
    category: str | None


@dataclass(frozen=True)
class PreparedOffer:
    offer: MatchOffer
    normalized_name: str
    normalized_brand: str
    name_tokens: frozenset[str]
    content_tokens: frozenset[str]
    model_tokens: frozenset[str]


@dataclass(frozen=True)
class MatchCandidate:
    competitor_offer_id: uuid.UUID
    own_offer_id: uuid.UUID
    score: float
    rank: int
    suggested: bool
    reasons: dict


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-zA-Z0-9]+", " ", ascii_value).lower().split())


def text_tokens(value: str | None) -> frozenset[str]:
    return frozenset(
        token
        for token in normalize_text(value).split()
        if len(token) >= 3 and token not in STOPWORDS
    )


def normalize_brand(value: str | None) -> str:
    normalized = normalize_text(value.replace(".", "") if value else value)
    return BRAND_ALIAS_KEYS.get(normalized, normalized)


def model_tokens(value: str | None) -> frozenset[str]:
    ascii_value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower()
    candidates = re.findall(r"[a-z0-9]+(?:[-_/.][a-z0-9]+)+|[a-z0-9]+", ascii_value)
    return frozenset(
        compact
        for token in candidates
        if (compact := re.sub(r"[^a-z0-9]", "", token))
        and len(compact) >= 5
        and any(character.isalpha() for character in token)
        and any(character.isdigit() for character in token)
        and not MEASUREMENT_TOKEN.fullmatch(compact)
        and not COMPOSITE_MEASUREMENT_TOKEN.fullmatch(compact)
        and compact not in GENERIC_MODEL_TOKENS
    )


def prepare_offer(offer: MatchOffer) -> PreparedOffer:
    name_tokens = text_tokens(offer.name)
    identifiers = " ".join(
        value for value in (offer.manufacturer_code, offer.reference) if value
    )
    content = " ".join(
        value
        for value in (
            offer.name,
            offer.manufacturer_code,
            offer.reference,
            offer.description,
            offer.category,
        )
        if value
    )
    return PreparedOffer(
        offer=offer,
        normalized_name=normalize_text(offer.name),
        normalized_brand=normalize_brand(offer.brand),
        name_tokens=name_tokens,
        content_tokens=text_tokens(content),
        model_tokens=model_tokens(
            f"{offer.name} {identifiers} {(offer.description or '')[:2000]}"
        ),
    )


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _coverage(query: frozenset[str], candidate: frozenset[str]) -> float:
    return len(query & candidate) / len(query) if query else 0.0


def score_pair(competitor: PreparedOffer, own: PreparedOffer) -> tuple[float, dict]:
    shared_models = competitor.model_tokens & own.model_tokens
    model_score = (
        len(shared_models) / min(len(competitor.model_tokens), len(own.model_tokens))
        if competitor.model_tokens and own.model_tokens
        else 0.0
    )
    name_similarity = SequenceMatcher(
        None, competitor.normalized_name, own.normalized_name, autojunk=False
    ).ratio()
    name_jaccard = _jaccard(competitor.name_tokens, own.name_tokens)
    content_coverage = _coverage(competitor.name_tokens, own.content_tokens)
    brand_equal = bool(
        competitor.normalized_brand
        and competitor.normalized_brand == own.normalized_brand
    )

    if shared_models:
        score = (
            0.50 * model_score
            + 0.20 * name_jaccard
            + 0.15 * name_similarity
            + 0.10 * float(brand_equal)
            + 0.05 * content_coverage
        )
    else:
        score = (
            0.45 * name_jaccard
            + 0.30 * name_similarity
            + 0.15 * float(brand_equal)
            + 0.10 * content_coverage
        )
    reasons = {
        "shared_model_tokens": sorted(shared_models),
        "model_score": round(model_score, 4),
        "name_token_similarity": round(name_jaccard, 4),
        "name_text_similarity": round(name_similarity, 4),
        "name_content_coverage": round(content_coverage, 4),
        "brand_equal": brand_equal,
        "competitor_brand_normalized": competitor.normalized_brand or None,
        "own_brand_normalized": own.normalized_brand or None,
    }
    return round(score, 5), reasons


def match_catalogs(
    competitor_offers: list[MatchOffer],
    own_offers: list[MatchOffer],
    *,
    candidate_limit: int = 3,
    minimum_score: float = 0.38,
    suggested_score: float = 0.68,
) -> list[MatchCandidate]:
    prepared_own = [prepare_offer(offer) for offer in own_offers]
    token_index: dict[str, list[int]] = defaultdict(list)
    model_index: dict[str, list[int]] = defaultdict(list)
    brand_index: dict[str, list[int]] = defaultdict(list)
    for index, offer in enumerate(prepared_own):
        for token in offer.name_tokens:
            token_index[token].append(index)
        for token in offer.model_tokens:
            model_index[token].append(index)
        if offer.normalized_brand:
            brand_index[offer.normalized_brand].append(index)

    results = []
    for raw_competitor in competitor_offers:
        competitor = prepare_offer(raw_competitor)
        candidate_weights: Counter[int] = Counter()
        for token in competitor.model_tokens:
            postings = model_index.get(token, [])
            if len(postings) <= 500:
                for index in postings:
                    candidate_weights[index] += 8
        for token in competitor.name_tokens:
            postings = token_index.get(token, [])
            if len(postings) <= 300:
                weight = 4 if any(character.isdigit() for character in token) else 1
                for index in postings:
                    candidate_weights[index] += weight
        same_brand = brand_index.get(competitor.normalized_brand, [])
        if len(same_brand) <= 250:
            for index in same_brand:
                candidate_weights[index] += 1

        ranked_pool = [index for index, _ in candidate_weights.most_common(400)]
        scored = []
        for index in ranked_pool:
            score, reasons = score_pair(competitor, prepared_own[index])
            if score >= minimum_score:
                scored.append((score, prepared_own[index], reasons))
        scored.sort(
            key=lambda value: (
                -value[0],
                value[1].offer.company_name.casefold(),
                value[1].offer.name.casefold(),
            )
        )
        for rank, (score, own, reasons) in enumerate(scored[:candidate_limit], start=1):
            results.append(
                MatchCandidate(
                    competitor_offer_id=competitor.offer.id,
                    own_offer_id=own.offer.id,
                    score=score,
                    rank=rank,
                    suggested=(
                        score >= suggested_score
                        and bool(reasons["shared_model_tokens"])
                    ),
                    reasons=reasons,
                )
            )
    return results
