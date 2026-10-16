"""Regra comercial: presença/suporte de SO comparados por família.

Edição, versão e instalação continuam nas evidências, mas não são critérios
de igualdade deste atributo. Ausência explícita e negação não viram suporte.
"""
import re
from app.services.catalog_treatment import plain

VERSION = 'os-families-v2'
FAMILIES = {'Windows': r'\bwindows\b', 'Linux': r'\blinux\b|\b(?:ubuntu|debian|centos|yocto)\b',
            'Android': r'\bandroid\b', 'macOS': r'\bmac\s?os\b', 'FreeBSD': r'\bfreebsd\b', 'DOS': r'\b(?:ms dos|freedos)\b',
            'ChromeOS': r'\bchrome\s?os\b', 'FreeRTOS': r'\bfreertos\b', 'VxWorks': r'\bvxworks\b'}


def os_families(value):
    text = plain(str(value))
    if re.search(r'\b(?:nao|not|incompativel|unsupported|except|exceto)\b', text):
        return None
    if re.search(r'\b(?:sem|without|no)\s+(?:suporte|support|windows|linux|android|macos)\b', text):
        return None
    absent = bool(re.search(r'\b(?:sem sistema operacional|sem so|no os|without os)\b', text))
    found = {name for name, pattern in FAMILIES.items() if re.search(pattern, text)}
    if absent:
        found.add('Sem sistema operacional')
    return frozenset(found) if found else None


def combined_os(observations):
    if not observations:
        return None
    sets = [os_families(v.get('raw', v.get('raw_value', ''))) for v in observations]
    if any(v is None for v in sets):
        return None
    return frozenset().union(*sets)


def os_value(observations):
    families = combined_os(observations)
    first = observations[0]
    # Conflitos lexicais antigos de listas reconhecidas são resolvidos por esta
    # regra explícita. Valores negativos/não reconhecidos permanecem pendentes.
    known = families is not None and all(v['state'] in {'known', 'conflicting'} for v in observations)
    return {**first, 'raw': '; '.join(v['raw'] for v in observations),
            'normalized': ' / '.join(sorted(families)) if known else None,
            'scope': 'os_family', 'unit': '', 'state': 'known' if known else 'unparseable'}


def compare_os(reference, values):
    if not reference or not values:
        return 'insufficient'
    a, b = os_value(reference), os_value(values)
    if a['state'] != 'known' or b['state'] != 'known':
        return 'insufficient'
    return 'equivalent' if a['normalized'] == b['normalized'] else 'different'
