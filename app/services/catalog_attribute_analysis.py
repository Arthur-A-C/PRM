"""Indicadores reproduzíveis do snapshot; equivalência de SO é apenas um atributo."""
from collections import Counter, defaultdict
from app.services.operating_system import combined_os, VERSION
from app.services.comparison_details import extract_components, usb_components


class AttributeAnalysis:
    def __init__(self):
        self.counts = defaultdict(Counter)
        self.profiles = []

    def observe(self, item, attrs):
        source = item['source_id']
        c = self.counts[source]
        c['total'] += 1
        selected = [a for a in attrs if a['attribute_code'] == 'compute.os']
        if selected:
            c['with_os'] += 1
            families = combined_os(selected)
            recognized = families is not None and all(a['knowledge_state'] == 'known' for a in selected)
            c['recognized_os'] += recognized
            self.profiles.append((source, item['classification']['family_id'], item['public_catalog'], families if recognized else None))
        for name, codes in [('memory', {'compute.ram', 'compute.ram.type'}), ('storage', {'compute.storage', 'compute.storage.type'}), ('usb', {'ports.usb'})]:
            selected = [a for a in attrs if a['attribute_code'] in codes]
            if not selected:
                continue
            c[name + '_present'] += 1
            components = []
            for a in selected:
                v = {'raw': a['raw_value'], 'normalized': a['normalized_value'], 'state': a['knowledge_state'],
                     'scope': a['configuration_scope'], 'unit': a['unit'] or ''}
                components.extend(usb_components(v) if name == 'usb' else extract_components(v, name))
            interpreted = components and all(v['state'] == 'known' and code not in {'ports.usb', 'detail.residual'} for _, v, code in components)
            c[name + '_interpreted'] += bool(interpreted)

    def summary(self):
        own = defaultdict(set)
        for source, family, public, os in self.profiles:
            if source in {'portwell', 'choice'} and public and family != 'unknown' and os:
                own[family].add(os)
        reports = []
        for source in ['eco', 'dimensional']:
            c = self.counts[source]
            outcomes = Counter()
            for src, family, _, os in self.profiles:
                if src != source:
                    continue
                outcome = 'inconclusive' if not os or not own[family] else 'equivalent' if os in own[family] else 'different'
                outcomes[outcome] += 1
            missing = c['total'] - c['with_os']
            reports.append({'source': source, 'total': c['total'], 'with_os': c['with_os'], 'missing_os': missing,
                            'equivalent': outcomes['equivalent'], 'different': outcomes['different'],
                            'inconclusive': outcomes['inconclusive'],
                            'equivalent_percent_total': round(100 * outcomes['equivalent'] / c['total'], 2) if c['total'] else 0,
                            'equivalent_percent_assessed': round(100 * outcomes['equivalent'] / (outcomes['equivalent'] + outcomes['different']), 2) if outcomes['equivalent'] + outcomes['different'] else None})
        return {'policy': VERSION, 'scope': 'os_attribute_same_family_own_public',
                'sources': {s: dict(c) for s, c in self.counts.items()}, 'competitors': reports}
