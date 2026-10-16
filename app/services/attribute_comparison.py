"""Comparação conservadora de observações; não homologa substituição de produtos."""
import re
from decimal import Decimal
from app.services.usb_comparison import compare_usb
from app.services.comparison_details import build_display_rows
from app.services.operating_system import compare_os


LABELS = {'reference': 'Referência', 'equal': 'Igual', 'equivalent': 'Equivalente',
          'partial': 'Correspondência parcial',
          'different': 'Diferente', 'insufficient': 'Dados insuficientes', 'conflict': 'Conferir conflito'}


def text_key(value):
    return ' '.join(str(value).casefold().split())


def value_key(value, code):
    text = text_key(value['normalized'] if value['normalized'] is not None else value['raw'])
    if code in {'compute.ram', 'compute.storage'}:
        match = re.fullmatch(r'(\d+(?:[.,]\d+)?)\s*(kb|mb|gb|tb|kib|mib|gib|tib)', text)
        if match:
            # SI e IEC permanecem distintos; não presumir 1 TB = 1024 GB.
            unit = match[2]
            scale = {'kb': 1000, 'mb': 1000**2, 'gb': 1000**3, 'tb': 1000**4,
                     'kib': 1024, 'mib': 1024**2, 'gib': 1024**3, 'tib': 1024**4}[unit]
            return ('capacity', Decimal(match[1].replace(',', '.')) * scale)
    return ('text', text)


def verdict(reference, values, code):
    if code == 'compute.os':
        return compare_os(reference, values)
    if not reference or not values:
        return 'insufficient'
    if any(v['state'] == 'conflicting' for v in reference + values):
        return 'conflict'
    if any(v['state'] != 'known' or not str(v['raw']).strip() or text_key(v['raw']) in {'-', 'n/a', 'na', 'não informado', 'desconhecido'} for v in reference + values):
        return 'insufficient'
    def keyed(observations):
        result = {}
        for v in observations:
            scope = (v['scope'], v['unit'])
            result.setdefault(scope, set()).add(value_key(v, code))
        return result
    left, right = keyed(reference), keyed(values)
    if left.keys() != right.keys():
        return 'insufficient'
    if any(len(v) > 1 for v in list(left.values()) + list(right.values())):
        return 'conflict'
    if left == right:
        raw_left = {(v['scope'], v['unit'], str(v['raw']).strip()) for v in reference}
        raw_right = {(v['scope'], v['unit'], str(v['raw']).strip()) for v in values}
        return 'equal' if raw_left == raw_right else 'equivalent'
    if code == 'ports.usb':
        results = [compare_usb(next(iter(left[scope]))[1], next(iter(right[scope]))[1]) for scope in left]
        if 'different' in results:
            return 'different'
        return 'insufficient' if 'insufficient' in results else 'equivalent'
    # Descrições compostas, listas e alternativas exigem avaliação técnica.
    complex_pattern = r'[,;|/~]|\b(suporta|ate|até|opcional|ou|or)\b'
    if any(re.search(complex_pattern, text_key(v['raw'])) for v in reference + values):
        return 'insufficient'
    return 'different'


def decorate_comparison(items, rows):
    reference_id = items[0]['item_id'] if items else None
    for row in rows:
        row['statuses'] = {}
        reference = row['values'].get(reference_id, [])
        for item in items:
            status = 'reference' if item['item_id'] == reference_id else verdict(reference, row['values'].get(item['item_id'], []), row['code'])
            row['statuses'][item['item_id']] = {'code': status, 'label': LABELS[status]}
            if status == 'equivalent' and row['code'] == 'ports.usb':
                row['statuses'][item['item_id']]['note'] = 'Quantidades e versões USB equivalentes. Geração e conector são conferidos quando informados nos dois produtos; detalhes ausentes permanecem não confirmados.'
    groups = {}
    for row in rows:
        code = row['code']
        group = 'Memória' if code in {'compute.ram', 'compute.ram.type', 'unmapped.memoria'} else 'Armazenamento' if code in {'compute.storage', 'compute.storage.type'} else 'Sistema Operacional' if code == 'compute.os' else 'Outras características'
        if code == 'unmapped.memoria':
            row['label'] = 'Memória — contexto não identificado'
        groups.setdefault(group, []).append(row)
    return {'items': items, 'rows': rows, 'reference_id': reference_id,
            'display_rows': build_display_rows(items, rows, verdict, LABELS),
            'groups': [{'label': label, 'rows': groups[label]} for label in ['Memória', 'Armazenamento', 'Sistema Operacional', 'Outras características'] if label in groups]}
