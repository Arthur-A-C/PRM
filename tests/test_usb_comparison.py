import pytest
from app.services.usb_comparison import compare_usb, parse_usb
from app.services.refined_catalog_database import current_comparison


@pytest.mark.parametrize('left,right,expected', [
    ('2x USB 2.0, 4x USB 3.2', '2 x USB 2.0 Type-A, 4 x USB 3.2 Gen2 Type-A', 'equivalent'),
    ('4x USB 3.2; 2x USB 2.0', '2 × USB 2.0 Tipo A + 4 x USB 3.2 Generation 2 Type-A', 'equivalent'),
    ('1x USB 2.0, 1x USB 2.0', '2x USB 2.0', 'equivalent'),
    ('2x USB 3.2 Gen1 Type-A', '2x USB 3.2 Gen2 Type-A', 'different'),
    ('2x USB 3.2 Type-A', '2x USB 3.2 Type-C', 'different'),
    ('2x USB 2.0, 4x USB 3.2', '4x USB 2.0, 2x USB 3.2', 'different'),
    ('2x USB 3.0', '2x USB 3.2', 'different'),
    ('2x USB 3.2', '3x USB 3.2', 'different'),
    ('2x USB 3.2', '2x USB 3.2 ou 4x USB 3.2', 'insufficient'),
    ('2x USB 3.2', '2x USB 3.2 interno', 'insufficient'),
    ('2x USB 3.2', 'USB 3.2', 'insufficient'),
    ('2x USB 3.2', '2x USB 3.2 Type-C OTG', 'insufficient'),
    ('2x USB 3.2', 'até 2x USB 3.2', 'insufficient'),
    ('1x USB 3.2, 1x USB 3.2 Type-A', '1x USB 3.2 Type-A, 1x USB 3.2 Type-C', 'equivalent'),
])
def test_usb_semantics(left, right, expected):
    assert compare_usb(left, right) == expected
    assert compare_usb(right, left) == expected


@pytest.mark.parametrize('value', ['-2x USB 2.0', '0x USB 2.0', '999999x USB 2.0', '2x USB 2.0 garbage', '2x USB 2.0/3.2'])
def test_full_parse_required(value):
    assert parse_usb(value) is None


def test_screenshot_case_through_matrix_and_conflicts_preserved():
    items = [{'item_id': str(i), 'attribute_observations': [{
        'attribute_code': 'ports.usb', 'raw_name': name, 'raw_value': value,
        'normalized_value': value, 'configuration_scope': 'unspecified', 'unit': None,
        'knowledge_state': 'known'}]} for i,(name,value) in enumerate([
            ('Portas USB', '2x USB 2.0, 4x USB 3.2'),
            ('ATR_USB', '2 x USB 2.0 Type-A, 4 x USB 3.2 Gen2 Type-A')])]
    status = current_comparison(items)['rows'][0]['statuses']['1']
    assert status['code'] == 'equivalent' and 'não confirmados' in status['note']
    items[1]['attribute_observations'][0]['knowledge_state'] = 'conflicting'
    assert current_comparison(items)['rows'][0]['statuses']['1']['code'] == 'conflict'
    items[1]['attribute_observations'][0]['configuration_scope'] = 'optional'
    assert current_comparison(items)['rows'][0]['statuses']['1']['code'] == 'insufficient'
