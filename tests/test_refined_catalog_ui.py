from types import SimpleNamespace

from app.routers.pages import templates
from app.services.refined_catalog import load_policy, normalize_record


def test_new_catalog_escapes_source_text_and_restricts_hidden_prices():
    raw = {"ID": "1", "SKU": "A1", "Nome": "Fonte de alimentação <script>alert('x')</script>",
           "Publicado": "1", "Visibilidade no catálogo": "visible", "Categorias": "Fontes",
           "Preço": "1234,56", "Metadado: _hide_product_price": "yes",
           "Nome do atributo 1": "Texto", "Valores do atributo 1": "<img src=x onerror=alert(1)>"}
    item, attrs = normalize_record({"raw": raw, "issues": []}, "choice", load_policy(), "batch")
    item["attribute_observations"] = attrs
    context = {"refined_catalog": {"items": [item], "search": "", "source": "choice", "family": "", "internal": False,
               "manifest": {"families": {}}, "total": 1, "page": 1, "pages": 1}, "refined_pagination": ""}
    template = templates.get_template("_refined_catalog.html")
    seller = template.render(**context, user=SimpleNamespace(role="vendedor"))
    manager = template.render(**context, user=SimpleNamespace(role="gestor"))
    assert "1234.56" not in seller and "1234.56" in manager
    assert "<img src=x" not in seller and "&lt;img" in seller
    assert "alert('x')" not in seller
    assert "100 por página" in seller


def test_new_analysis_does_not_report_zero_coverage_or_equivalence():
    summary = {"created_at": "2026-10-09", "run_id": "0" * 24, "rule_version": "test", "elapsed_seconds": 1,
               "ai_calls": 0, "inputs": [], "families": {}, "counts": {}}
    for source in ["portwell", "choice", "eco", "dimensional"]:
        summary["counts"][source] = {"received": 1, "accepted": 1, "public_catalog": 1, "with_attributes": 0,
                                     "conflicting_attributes": 0, "unknown_family": 1}
    rendered = templates.get_template("_refined_analysis.html").render(refined_analysis=summary, title="Comparador", user=SimpleNamespace(role="gestor"))
    assert "não avaliada" in rendered and "não 0%" in rendered
    assert "não ausência no portfólio" in rendered
    assert rendered.index("Portwell ·") < rendered.index("Choice ·") < rendered.index("ECO ·") < rendered.index("Dimensional ·")
