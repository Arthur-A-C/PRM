from copy import deepcopy
from app.services.refined_catalog_database import current_comparison


def attr(code, value, scope='unspecified', state='known', normalized=None, unit=''):
    return dict(attribute_code=code, raw_name=code, raw_value=value, configuration_scope=scope,
                knowledge_state=state, normalized_value=normalized, unit=unit)


def compare(left, right, third=None):
    items = [{'item_id': str(i), 'attribute_observations': a} for i,a in enumerate([left, right] + ([third] if third else []))]
    before = deepcopy(items)
    result = current_comparison(items)
    assert items == before
    return result


def status(left, right):
    return compare([left], [right])['rows'][0]['statuses']['1']['code']


def test_equal_equivalent_different_and_three_products():
    a = attr('compute.ram', '8GB')
    assert status(a, a) == 'equal'
    assert status(a, attr('compute.ram', '8 GB')) == 'equivalent'
    result = compare([a], [attr('compute.ram', '16GB')], [a])
    assert result['rows'][0]['statuses']['1']['code'] == 'different'
    assert result['rows'][0]['statuses']['2']['code'] == 'equal'
    assert status(attr('compute.storage', '1TB'), attr('compute.storage', '1000 GB')) == 'equivalent'
    assert status(attr('compute.storage', '1TB'), attr('compute.storage', '1024 GB')) == 'different'


def test_missing_conflicts_and_alternatives_are_not_equivalent():
    a = attr('compute.ram', '8GB')
    assert compare([a], [])['rows'][0]['statuses']['1']['code'] == 'insufficient'
    assert status(a, attr('compute.ram', '8GB', state='conflicting')) == 'conflict'
    assert status(a, attr('compute.ram', '8GB', state='unknown')) == 'insufficient'
    assert status(a, attr('compute.ram', '8GB, 16GB')) == 'insufficient'


def test_os_one_row_retains_scope_and_multiple_values():
    installed = attr('compute.os', 'Windows 11', 'installed')
    supported = attr('compute.os', 'Windows 11', 'supported')
    result = compare([installed, supported], [supported])
    assert len(result['rows']) == 1
    assert len(result['rows'][0]['values']['0']) == 2
    assert result['rows'][0]['statuses']['1']['code'] == 'equivalent'
    assert status(installed, supported) == 'equivalent'
    assert status(installed, attr('compute.os', 'Windows 11 Pro', 'installed')) == 'equivalent'


def test_grouping_does_not_merge_capacity_type_or_controller_memory():
    attrs = [attr('compute.ram', '8GB'), attr('compute.ram.type', 'DDR4'),
             attr('compute.storage', '256GB'), attr('compute.storage.type', 'SSD'),
             attr('control.memory', '8MB')]
    result = compare(attrs, attrs)
    assert len(result['rows']) == 5
    groups = {g['label']: g['rows'] for g in result['groups']}
    assert len(groups['Memória']) == len(groups['Armazenamento']) == 2
    assert groups['Outras características'][0]['code'] == 'control.memory'


def test_normalized_units_and_missing_unit_are_distinguished():
    assert status(attr('electrical.current.nominal', '500 mA', normalized='0.5', unit='A'),
                  attr('electrical.current.nominal', '0,5 A', normalized='0.5', unit='A')) == 'equivalent'
    result = compare([attr('electrical.current.nominal', '5', unit='')],
                     [attr('electrical.current.nominal', '5 A', unit='A')])
    assert all(r['statuses']['1']['code'] == 'insufficient' for r in result['rows'])


def test_grouped_template_renders_single_os_row_and_verdicts():
    from types import SimpleNamespace
    from app.routers.pages import templates
    result = compare([attr('compute.os', 'Windows 11', 'supported'), attr('compute.os', 'Linux')],
                     [attr('compute.os', 'Windows 11', 'supported')])
    for item in result['items']:
        item.update(source_id='portwell', title_display='<script>unsafe</script>', sku='A', record_key='A',
                    classification={'family_label': 'PC'}, commercial={'prices': []}, quality_issues=[])
    html = templates.get_template('_current_comparison.html').render(current_comparison=result, user=SimpleNamespace(role='vendedor'))
    assert html.count('data-scope="supported"') == 2
    assert 'comparison-verdict--different' in html
    assert 'Diferente' in html and '<script>unsafe</script>' not in html
