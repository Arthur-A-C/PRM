import uuid

from app.services.catalog_matching import MatchOffer, match_catalogs, normalize_brand, normalize_text


def offer(
    company_code: str,
    name: str,
    *,
    brand: str | None = None,
    manufacturer_code: str | None = None,
) -> MatchOffer:
    return MatchOffer(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        company_code=company_code,
        company_name=company_code,
        external_code=str(uuid.uuid4()),
        name=name,
        brand=brand,
        manufacturer_code=manufacturer_code,
        reference=None,
        description=None,
        category=None,
    )


def test_normalization_is_case_and_accent_insensitive() -> None:
    assert normalize_text("Módulo de Automação") == "modulo de automacao"


def test_reviewed_brand_aliases_share_the_same_identity() -> None:
    assert normalize_brand("ELFIN") == "elfin"
    assert normalize_brand("New Elfin S.R.L.") == "elfin"


def test_matching_prefers_shared_model_and_brand() -> None:
    competitor = offer("eco", "CLP Siemens SIMATIC S7-1200 6ES7214-1AG40-0XB0", brand="Siemens")
    expected = offer(
        "portwell",
        "CPU SIMATIC S7-1200",
        brand="SIEMENS",
        manufacturer_code="6ES7214-1AG40-0XB0",
    )
    unrelated = offer("choice", "Fonte de alimentação 24V", brand="Siemens")

    matches = match_catalogs([competitor], [unrelated, expected], minimum_score=0.2)

    assert matches[0].own_offer_id == expected.id
    assert "6es72141ag400xb0" in matches[0].reasons["shared_model_tokens"]
    if len(matches) > 1:
        assert matches[0].score > matches[-1].score


def test_matching_does_not_treat_measurement_as_model_identifier() -> None:
    competitor = offer("eco", "Fonte chaveada 24V 10A", brand="Marca A")
    unrelated = offer("portwell", "Relé industrial 24V 10A", brand="Marca B")

    matches = match_catalogs([competitor], [unrelated])

    assert matches == []


def test_same_brand_and_similar_name_without_model_stays_candidate() -> None:
    competitor = offer("eco", "Bloco de contato NA 030FA", brand="ELFIN")
    own = offer("choice", "020E01 bloco de contato NF", brand="NEW ELFIN SRL")

    matches = match_catalogs([competitor], [own], minimum_score=0.2)

    assert matches
    assert matches[0].reasons["brand_equal"] is True
    assert matches[0].suggested is False
