import pytest

from app.services.refined_catalog import normalize_attribute, load_policy
from app.services.attribute_dictionary import alias_index
from app.services.refined_catalog_database import current_comparison


@pytest.mark.parametrize('competitor,own,value,code', [
    ('ATR_USB', 'Portas USB', '2x USB 3.0', 'ports.usb'),
    ('ATR_COM', 'Portas Seriais COM', '6x COM (RS-232/422/485)', 'ports.serial'),
    ('ATR_Protecao_IP', 'Proteção IP', 'IP-20', 'protection.ip'),
    ('CORRENTE NOMINAL', 'Corrente Nominal', '25 A', 'electrical.current.nominal'),
    ('ATR_Entradas_Digitais', 'Entrada Digital', '16x', 'io.digital.input'),
])
def test_aliases_align_in_comparison_without_losing_source(competitor, own, value, code):
    items = []
    for index, name in enumerate([own, competitor]):
        attr = normalize_attribute(name, value, 'box_pc')
        assert attr['attribute_code'] == code
        attr.update(raw_name=name, raw_value=value)
        items.append({'item_id': str(index), 'attribute_observations': [attr]})
    rows = current_comparison(items)['rows']
    assert len(rows) == 1 and len(rows[0]['values']) == 2
    assert rows[0]['values']['1'][0]['name'] == competitor


def test_unsafe_semantics_remain_separate():
    codes = {normalize_attribute(n, '24 V', 'contactor')['attribute_code'] for n in
             ['ATR_Tensao', 'Tensão de Entrada', 'Tensão de Saída', 'Tensão Bobina', 'TENSAO NOMINAL']}
    assert len(codes) == 5
    assert normalize_attribute('Memória', '8GB', 'box_pc')['attribute_code'] == 'compute.ram'
    assert normalize_attribute('ATR_Memoria', '8GB', 'plc')['attribute_code'] == 'control.memory'
    assert not normalize_attribute('Resolução', 'Multifeixes', 'sensor')['mapped']
    assert not normalize_attribute('Grau Proteção', 'Térmico', 'unknown')['mapped']
    assert not normalize_attribute('CA', '9992', 'unknown')['mapped']


def test_ports_do_not_invent_counts_and_keep_conflicts():
    serial = normalize_attribute('ATR_COM', '6x COM (RS-232/422/485)', 'box_pc')
    assert serial['qualifiers']['explicit_port_count'] == 6
    assert len(serial['qualifiers']['interfaces_observed']) == 3
    assert 'explicit_port_count' not in normalize_attribute('ATR_USB', 'USB 3.0', 'box_pc')['qualifiers']
    ambiguous = normalize_attribute('ATR_USB', '2x USB, 4x USB, 2x USB, 4x USB', 'box_pc')
    assert ambiguous['knowledge_state'] == 'conflicting'
    assert ambiguous['normalized_value'] is None
    assert normalize_attribute('ATR_Protecao_IP', 'IP-20', 'box_pc')['normalized_value'] == 'IP20'


def test_dictionary_is_versioned_and_aliases_unambiguous():
    assert len(alias_index()) > 70
    policy = load_policy()
    assert policy['attribute_dictionary']['version'] == 'attributes-v3'
    assert policy['rule_version'] == 'refined-base-v2'


def test_scalar_units_and_quantity_do_not_create_format_conflicts():
    assert normalize_attribute('ATR_Numero_de_Polos', '4', 'unknown')['normalized_value'] == normalize_attribute('NUMERO POLOS', '4 POLOS', 'unknown')['normalized_value'] == 4
    first = normalize_attribute('ATR_Corrente_Nominal', '500 mA', 'unknown')
    second = normalize_attribute('Corrente Nominal', '0,5 A', 'unknown')
    assert first['normalized_value'] == second['normalized_value'] == '0.5'
    assert first['unit'] == second['unit'] == 'A'
    assert normalize_attribute('Peso', '0.391 kg', 'unknown')['normalized_value'] == '391'
    assert normalize_attribute('Tensão de Entrada', '12-24 V', 'unknown')['normalized_value'] == '12-24 V'
    assert normalize_attribute('Tensão', '24 Vcc/ca', 'unknown')['unit'] is None
    assert normalize_attribute('Potência', '2, 5 W', 'unknown')['knowledge_state'] == 'conflicting'


def test_deduplication_and_conflicts_require_same_scope_and_unit():
    from app.services.refined_catalog import normalize_record
    raw = {'Codigo_ECO': 'sample', 'Nome_Original': 'Fonte', 'ATR_Tensao': '24 V',
           'Atributos_PRM': 'Tensao=24 | Tensao=12 V opcional | Tensao=24 V'}
    record = {'position': 1, 'raw': raw, 'issues': [], 'error': None}
    item, attrs = normalize_record(record, 'eco', load_policy(), 'test')
    assert len(attrs) == 3
    assert all(a['knowledge_state'] == 'known' for a in attrs)
    assert 'divergent_attribute_observations' not in item['quality_issues']
    assert next(a for a in attrs if a['unit'] == 'V')['correlated_representations']


def test_scalar_aliases_do_not_create_false_conflicts_in_actual_record_pipeline():
    from app.services.refined_catalog import normalize_record
    raw = {'sku': 'sample', 'nome': 'Disjuntor',
           'especificacoes': 'Número de Polos: 4 | NUMERO POLOS: 4 POLOS | CORRENTE NOMINAL: 500 mA | Corrente Nominal: 0,5 A'}
    item, attrs = normalize_record({'position': 1, 'raw': raw, 'issues': [], 'error': None}, 'dimensional', load_policy(), 'test')
    assert len(attrs) == 4
    assert all(a['knowledge_state'] == 'known' for a in attrs)
    assert 'divergent_attribute_observations' not in item['quality_issues']
