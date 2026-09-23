from sqlalchemy import text

from app.db import get_engine


QUERIES = {
    "companies": """
        SELECT code, company_type FROM companies
        ORDER BY CASE WHEN company_type = 'nossa' THEN 0 ELSE 1 END, name
    """,
    "imports": """
        SELECT c.code, i.status, i.total_rows, i.inserted_count, i.updated_count,
               i.unchanged_count, i.warning_count, i.rejected_count
        FROM catalog_imports i JOIN companies c ON c.id = i.company_id
        ORDER BY c.code
    """,
    "offers": """
        SELECT c.code, count(*) AS offers,
               count(*) FILTER (WHERE o.excluded_from_analytics) AS excluded
        FROM offers o JOIN companies c ON c.id = o.company_id
        GROUP BY c.code ORDER BY c.code
    """,
    "raw_rows": """
        SELECT c.code, count(*) AS raw_rows,
               count(*) FILTER (WHERE jsonb_array_length(r.errors) > 0) AS rejected
        FROM import_rows r
        JOIN catalog_imports i ON i.id = r.catalog_import_id
        JOIN companies c ON c.id = i.company_id
        GROUP BY c.code ORDER BY c.code
    """,
    "availability": """
        SELECT c.code, o.availability_state, count(*) AS quantity
        FROM offers o JOIN companies c ON c.id = o.company_id
        GROUP BY c.code, o.availability_state
        ORDER BY c.code, o.availability_state
    """,
    "prices": """
        SELECT c.code, p.modality, p.state, count(*) AS quantity
        FROM offer_prices p
        JOIN offer_observations ob ON ob.id = p.observation_id
        JOIN offers o ON o.id = ob.offer_id
        JOIN companies c ON c.id = o.company_id
        GROUP BY c.code, p.modality, p.state
        ORDER BY c.code, p.modality, p.state
    """,
    "totals": """
        SELECT (SELECT count(*) FROM catalog_imports) AS imports,
               (SELECT count(*) FROM offers) AS offers,
               (SELECT count(*) FROM import_rows) AS raw_rows,
               (SELECT count(*) FROM offer_observations) AS observations,
               (SELECT count(*) FROM offer_prices) AS prices,
               (SELECT count(*) FROM brands) AS brands,
               (SELECT count(*) FROM brand_aliases) AS brand_aliases,
               (SELECT count(*) FROM categories) AS categories,
               (SELECT count(*) FROM comparisons) AS comparisons,
               (SELECT count(*) FROM comparison_items) AS comparison_items,
               (SELECT count(*) FROM attribute_definitions) AS attribute_definitions,
               (SELECT count(*) FROM offer_attributes) AS offer_attributes,
               (SELECT count(*) FROM catalog_match_runs) AS catalog_match_runs,
               (SELECT count(*) FROM catalog_matches) AS catalog_matches,
               (SELECT count(*) FROM users) AS users,
               (SELECT count(*) FROM sessions) AS sessions
    """,
    "test_offer": """
        SELECT c.code, o.external_code, o.excluded_from_analytics, o.exclusion_reason
        FROM offers o JOIN companies c ON c.id = o.company_id
        WHERE c.code = 'eco-automacao' AND o.external_code = '4574'
    """,
}


def main() -> None:
    with get_engine().connect() as connection:
        for label, sql in QUERIES.items():
            rows = [dict(row._mapping) for row in connection.execute(text(sql))]
            print(label, rows)


if __name__ == "__main__":
    main()
