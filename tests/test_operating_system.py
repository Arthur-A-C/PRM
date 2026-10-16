from app.services.operating_system import os_families
from app.services.refined_catalog import normalize_record, load_policy
from app.services.refined_catalog_database import current_comparison
from app.services.catalog_attribute_analysis import AttributeAnalysis


def observation(raw, scope='unspecified', state='known'):
    return dict(attribute_code='compute.os', raw_name='ATR_Sistema_Operacional', raw_value=raw,
                normalized_value=raw, configuration_scope=scope, knowledge_state=state, unit=None)


def test_screenshot_uses_union_and_ignores_edition_scope_and_lexical_conflict():
    items = [{'item_id': 'own', 'attribute_observations': [observation('Suporta Linux, Suporta Windows', 'supported')]},
             {'item_id': 'eco', 'attribute_observations': [observation('Windows 10 IoT | Linux', state='conflicting'), observation('Windows 10 IoT', state='conflicting')]}]
    row = current_comparison(items)['display_rows'][0]
    assert len(row['cells']['eco']['details']) == 1
    assert row['cells']['eco']['status']['code'] == 'equivalent'
    assert row['values']['eco'][0]['state'] == 'conflicting'  # evidence intact


def test_negation_and_absence_are_not_positive_support():
    assert os_families('Não suporta Windows') is None
    assert os_families('sem Windows, Linux') is None
    assert os_families('Windows / ChromeOS') != os_families('Windows')
    assert os_families('sem sistema operacional') != os_families('Windows')
    assert os_families('-') is None
    assert os_families('Windows 11 Pro') == os_families('Suporta Windows')


def test_pipeline_does_not_mark_overlapping_os_lists_as_conflict():
    record = {'position': 1, 'issues': [], 'error': None, 'raw': {'Codigo_ECO': 'X', 'Nome_Original': 'Box PC',
              'ATR_Sistema_Operacional': 'Windows 10 IoT | Linux', 'Atributos_PRM': 'sistema_operacional=Windows 10 IoT'}}
    item, attrs = normalize_record(record, 'eco', load_policy(), 'test')
    assert len(attrs) == 2 and all(a['knowledge_state'] == 'known' for a in attrs)
    assert 'divergent_attribute_observations' not in item['quality_issues']


def test_metrics_require_visible_own_same_family_and_explicit_denominators():
    audit = AttributeAnalysis()
    def observe(source, family, os, public=True):
        audit.observe({'source_id': source, 'classification': {'family_id': family}, 'public_catalog': public},
                      [observation(os)] if os else [])
    observe('portwell', 'box_pc', 'Suporta Windows, Suporta Linux')
    observe('choice', 'hmi', 'Android', False)
    observe('eco', 'box_pc', 'Windows 10 IoT | Linux')
    observe('eco', 'box_pc', 'Android')
    observe('eco', 'hmi', 'Android')
    observe('eco', 'unknown', 'Windows')
    observe('eco', 'box_pc', None)
    report = audit.summary()['competitors'][0]
    assert (report['equivalent'], report['different'], report['inconclusive'], report['missing_os']) == (1, 1, 2, 1)
    assert report['equivalent_percent_total'] == 20
    assert report['equivalent_percent_assessed'] == 50


def test_dashboard_attribute_panel_has_denominators_and_handles_empty_sources():
    from app.routers.pages import templates
    from types import SimpleNamespace
    audit = AttributeAnalysis()
    audit.counts['eco']['total'] = 10
    html = templates.get_template('_attribute_analysis.html').render(current_analysis=SimpleNamespace(attribute_analysis=audit.summary()))
    assert '10 sem informação de SO' in html
    assert 'Não disponível' in html
    assert 'não confirma equivalência do produto inteiro' in html
