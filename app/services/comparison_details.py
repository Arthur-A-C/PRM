"""Visão composta de características, sem modificar observações publicadas."""
import re
from collections import Counter

from app.services.usb_comparison import parse_usb
from app.services.operating_system import os_value

SCOPES = {'unspecified': 'Escopo não informado', 'supported': 'Suportado',
          'os_family': 'Famílias de SO — presença ou suporte',
          'installed': 'Instalado', 'optional': 'Opcional'}
CAPACITY = re.compile(r'\b\d+(?:[.,]\d+)?\s*(?:[kmgt]i?b)\b', re.I)


def extract_components(value, kind):
    """Extrai apenas detalhes explícitos; resíduos continuam visíveis e pendentes."""
    raw = str(value['raw'])
    if value['state'] != 'known':
        return [('Descrição não validada', value, kind)]
    text = raw.replace('×', 'x')
    parts, spans = [], []

    def add(label, match, canonical=None, code=None):
        if match:
            v = {**value, 'raw': match[0], 'normalized': canonical or match[0], 'unit': ''}
            parts.append((label, v, code or 'detail.' + label))
            spans.append(match.span())

    if kind == 'memory':
        for m in re.finditer(r'\b(?:LPDDR|GDDR|DDR)\s*[- ]?\s*\d+[A-Z]?\b', text, re.I):
            add('Tecnologia', m, re.sub(r'[ -]', '', m[0]).upper())
        for m in re.finditer(r'\b(?:SO[ -]?DIMM|DIMM)\b', text, re.I):
            add('Formato', m, 'SO-DIMM' if m[0].lower().startswith('so') else 'DIMM')
        for m in re.finditer(r'\b\d+(?:[.,]\d+)?\s*(?:MHz|MT/s)\b', text, re.I):
            add('Frequência / taxa', m, re.sub(r'\s+', '', m[0]).upper())
        for m in re.finditer(r'\b(\d+)\s*x(?=\s*(?:SO[ -]?DIMM|DIMM)\b)', text, re.I):
            add('Slots informados', m, m[1])
    else:
        for m in re.finditer(r'\b(?:SSD|HDD|eMMC)\b', text, re.I):
            add('Tecnologia', m, m[0].upper())
        for m in re.finditer(r'\b(?:mSATA|SATA|NVMe|PCIe)\b', text, re.I):
            add('Protocolo' if m[0].lower() == 'nvme' else 'Barramento' if m[0].lower() == 'pcie' else 'Interface', m, m[0].upper())
        for m in re.finditer(r'\bM\.2(?:\s+\d{4})?|\b(?:2\.5|3\.5)\s*["″]', text, re.I):
            add('Formato', m, re.sub(r'\s+', '', m[0]).upper())

    capacities = list(CAPACITY.finditer(text))
    ranged = bool(re.search(r'\b\d+(?:[.,]\d+)?\s*(?:[kmgt]i?b)?\s*(?:~|–|\ba\b|\bto\b|-)\s*\d+\s*[kmgt]i?b', text, re.I))
    for m in capacities:
        prefix = text[:m.start()]
        maximum = re.search(r'(?:até|ate|up to|máx(?:imo)?\.?|max(?:imum)?\.?)\s*$', prefix, re.I)
        per_module = re.search(r'\d+\s*x\s*$', prefix, re.I)
        if ranged or per_module or (len(capacities) > 1 and not maximum):
            continue
        add('Capacidade máxima' if maximum else 'Capacidade informada', m, code='compute.ram' if kind == 'memory' else 'compute.storage')
        if maximum:
            spans.append(maximum.span())

    remainder = list(text)
    for start, end in spans:
        remainder[start:end] = ' ' * (end - start)
    residue = ''.join(remainder).strip(' ()[],;+|\t\n')
    if residue.strip(' ()[],;+|\t\n') or not parts:
        parts.append(('Descrição complementar', {**value, 'state': 'unparseable'}, 'detail.residual'))
    return parts


def usb_components(value):
    parsed = parse_usb(value['raw']) if value['state'] == 'known' else None
    if parsed is None:
        return [('Descrição USB', value, 'ports.usb')]
    parts = []
    for version, count in sorted(Counter(p[0] for p in parsed).items()):
        parts.append((f'USB {version} — quantidade', {**value, 'raw': str(count), 'normalized': str(count)}, 'detail.count'))
        for index, name in [(1, 'geração'), (2, 'conector')]:
            entries = [p[index] for p in parsed if p[0] == version]
            known = [p for p in entries if p]
            if known:
                description = ', '.join(f'{n}x {term}' for term, n in sorted(Counter(known).items()))
                parts.append((f'USB {version} — {name}', {**value, 'raw': description, 'normalized': description,
                              'state': 'known' if len(known) == count else 'unknown'}, 'detail.usb'))
    return parts


def build_display_rows(items, rows, verdict, labels):
    """Uma linha por característica; detalhes independentes dentro de cada célula."""
    reference_id = items[0]['item_id'] if items else None
    groups = {}
    for row in rows:
        code = row['code']
        kind = 'memory' if code in {'compute.ram', 'compute.ram.type', 'unmapped.memoria'} else 'storage' if code in {'compute.storage', 'compute.storage.type'} else code
        label = {'memory': 'Memória', 'storage': 'Armazenamento'}.get(kind, row['label'])
        # Não unir campos não mapeados com nomes distintos.
        group_key = (kind, row['label'] if code.startswith('unmapped.') and kind != 'memory' else '')
        group = groups.setdefault(group_key, {'label': label, 'code': kind, 'values': {}, 'facets': {}})
        for item_id, observations in row['values'].items():
            group['values'].setdefault(item_id, []).extend(observations)
            if kind == 'compute.os':
                observations = [os_value(observations)]
            for value in observations:
                if kind in {'memory', 'storage'} and code != 'unmapped.memoria':
                    components = extract_components(value, kind)
                elif kind == 'ports.usb':
                    components = usb_components(value)
                else:
                    components = [('Memória sem contexto' if code == 'unmapped.memoria' else 'Valor', value, code)]
                for name, detail, detail_code in components:
                    key = (name, detail['scope'], detail['unit'], detail_code)
                    facet = group['facets'].setdefault(key, {'label': name, 'scope': detail['scope'], 'unit': detail['unit'], 'code': detail_code, 'values': {}})
                    facet['values'].setdefault(item_id, []).append(detail)
    result = []
    for group in groups.values():
        group['cells'] = {}
        for item in items:
            item_id = item['item_id']
            details, states = [], []
            for facet in group['facets'].values():
                values = facet['values'].get(item_id, [])
                reference = facet['values'].get(reference_id, [])
                state = 'reference' if item_id == reference_id else 'conflict' if any(v['state'] == 'conflicting' for v in reference + values) else verdict(reference, values, facet['code'])
                states.append(state)
                details.append({'label': facet['label'], 'scope': SCOPES.get(facet['scope'], facet['scope']),
                                'unit': facet['unit'], 'values': values, 'reference': reference,
                                'status': {'code': state, 'label': labels[state]}})
            if item_id == reference_id:
                state = 'reference'
            elif 'conflict' in states:
                state = 'conflict'
            elif 'different' in states:
                state = 'different'
            elif any(s in {'equal', 'equivalent'} for s in states):
                state = 'partial' if 'insufficient' in states else 'equal' if all(s == 'equal' for s in states) else 'equivalent'
            else:
                state = 'insufficient'
            group['cells'][item_id] = {'details': details, 'status': {'code': state, 'label': labels[state]}}
        group.pop('facets')
        result.append(group)
    return result
