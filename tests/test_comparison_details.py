from copy import deepcopy
from types import SimpleNamespace

from app.services.refined_catalog_database import current_comparison
from app.routers.pages import templates


def a(code, value, scope='unspecified', state='known'):
    return {'attribute_code': code, 'raw_name': code, 'raw_value': value, 'normalized_value': value,
            'configuration_scope': scope, 'knowledge_state': state, 'unit': None}


def matrix(left, right):
    items = [{'item_id': str(i), 'source_id': 'portwell' if i == 0 else 'eco',
              'sku': 'test', 'title_display': 'Produto', 'record_key': 'test',
              'classification': {'family_label': 'PC'}, 'quality_issues': [],
              'commercial': {'prices': []}, 'attribute_observations': attrs}
             for i, attrs in enumerate([left, right])]
    original = deepcopy(items)
    result = current_comparison(items)
    assert items == original
    return result


def test_screenshot_single_memory_row_partial_without_installed_maximum_confusion():
    result = matrix([a('compute.ram', '8GB'), a('compute.ram.type', 'DDR5 SODIMM')],
                    [a('compute.ram', '2 x SO-DIMM DDR5 4800 MHz (até 64 GB)')])
    assert len(result['display_rows']) == 1
    row = result['display_rows'][0]
    assert row['label'] == 'Memória'
    cell = row['cells']['1']
    assert cell['status']['code'] == 'partial'
    facets = {d['label']: d for d in cell['details']}
    assert facets['Tecnologia']['status']['code'] in {'equal', 'equivalent'}
    assert facets['Formato']['status']['code'] == 'equivalent'
    assert not facets['Capacidade informada']['values']
    assert facets['Capacidade máxima']['values'][0]['raw'] == '64 GB'
    assert facets['Slots informados']['values'][0]['normalized'] == '2'
    assert 'Descrição complementar' not in facets
    html = templates.get_template('_current_comparison.html').render(current_comparison=result, user=SimpleNamespace(role='vendedor'))
    assert html.count('<th scope="row">Memória</th>') == 1
    assert 'Correspondência parcial' in html and '4800 MHz' in html and 'Dados originais e origem' not in html
    admin_html = templates.get_template('_current_comparison.html').render(current_comparison=result, user=SimpleNamespace(role='desenvolvedor'))
    assert 'Dados originais e origem' in admin_html


def test_storage_combined_vs_split_and_real_differences():
    left = [a('compute.storage', '512GB'), a('compute.storage.type', 'SSD SATA 2.5"')]
    right = [a('compute.storage', '512 GB SSD SATA 2.5"')]
    row = matrix(left, right)['display_rows'][0]
    assert row['label'] == 'Armazenamento' and row['cells']['1']['status']['code'] == 'equivalent'
    changed = matrix(left, [a('compute.storage', '256GB SSD SATA 2.5"')])['display_rows'][0]
    assert changed['cells']['1']['status']['code'] == 'different'


def test_capacity_only_does_not_prove_complete_memory_equivalence():
    row = matrix([a('compute.ram', '8GB'), a('compute.ram.type', 'DDR5 SODIMM')],
                 [a('compute.ram', '8 GB')])['display_rows'][0]
    assert row['cells']['1']['status']['code'] == 'partial'


def test_limits_ranges_and_module_counts_not_misread_as_installed_capacity():
    for raw in ['2 x 8GB DDR5', '8GB~64GB DDR5', '8-64 GB DDR5']:
        row = matrix([a('compute.ram', '8GB')], [a('compute.ram', raw)])['display_rows'][0]
        facet = next(d for d in row['cells']['1']['details'] if d['label'] == 'Capacidade informada')
        assert facet['values'] == []
        assert row['cells']['1']['status']['code'] == 'insufficient'


def test_conflicts_and_controller_context_preserved():
    row = matrix([a('compute.ram', '8GB')], [a('compute.ram', '8GB', state='conflicting')])['display_rows'][0]
    assert row['cells']['1']['status']['code'] == 'conflict'
    result = matrix([a('compute.ram', '8GB'), a('control.memory', '8MB')], [a('unmapped.memoria', '8GB')])
    assert len(result['display_rows']) == 2
    assert result['display_rows'][0]['cells']['1']['status']['code'] == 'insufficient'


def test_all_other_attributes_use_one_row_with_scoped_details():
    row = matrix([a('electrical.voltage.input', '24 V', 'installed'), a('electrical.voltage.input', '12 V', 'optional')],
                 [a('electrical.voltage.input', '24 V', 'installed')])['display_rows'][0]
    assert row['cells']['1']['status']['code'] == 'partial'
    assert len(row['cells']['1']['details']) == 2


def test_usb_details_and_unspecified_generation():
    row = matrix([a('ports.usb', '2x USB 2.0, 4x USB 3.2')],
                 [a('ports.usb', '2x USB 2.0 Type-A, 4x USB 3.2 Gen2 Type-A')])['display_rows'][0]
    assert row['cells']['1']['status']['code'] == 'partial'
    assert sum(d['status']['code'] == 'equal' for d in row['cells']['1']['details']) == 2
