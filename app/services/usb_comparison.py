"""Normalização de descrições USB para comparação de quantidades e versões.

Detalhes ausentes são lacunas, não afirmações de geração/conector iguais.
O parser exige consumo completo; alternativas e características não reconhecidas
não são descartadas silenciosamente.
"""
import re
from collections import Counter

TERM_PATTERNS = (
    (r'\b(?:type|tipo)\s*[- ]?\s*([abc])\b', r'type-\1'),
    (r'\b(?:generation|geração|geracao|gen)\s*[- ]?\s*(\d)(?:\s*x\s*(\d))?\b',
     lambda m: 'gen' + m[1] + ('x' + m[2] if m[2] else '')),
)
PORT = re.compile(r'(\d+)\s*x\s*usb\s*(\d+\.\d+)(?:\s*(gen\d(?:x\d)?))?(?:\s*(type-[abc]))?')


def parse_usb(value):
    text = str(value).casefold().replace('×', 'x')
    for pattern, replacement in TERM_PATTERNS:
        text = re.sub(pattern, replacement, text)
    # Accept separators and whitespace between complete groups only.
    groups, end = [], 0
    for match in PORT.finditer(text):
        if text[end:match.start()].strip(' ,;+|\t\n\r'):
            return None
        quantity = int(match[1])
        if not 1 <= quantity <= 64:
            return None
        groups.extend([(match[2], match[3], match[4])] * quantity)
        end = match.end()
    if not groups or len(groups) > 64 or text[end:].strip(' ,;+|\t\n\r'):
        return None
    return groups


def compare_usb(left, right):
    left, right = parse_usb(left), parse_usb(right)
    if left is None or right is None:
        return 'insufficient'
    if Counter(v[0] for v in left) != Counter(v[0] for v in right):
        return 'different'
    # Matching bipartido evita depender da ordem dos segmentos ou de uma escolha
    # gulosa quando há grupos com conector/geração explicitados só de um lado.
    matched = {}
    def assign(index, seen):
        a = left[index]
        for j, b in enumerate(right):
            if j in seen or a[0] != b[0] or any(x and y and x != y for x, y in zip(a[1:], b[1:])):
                continue
            seen.add(j)
            if j not in matched or assign(matched[j], seen):
                matched[j] = index
                return True
        return False
    return 'equivalent' if all(assign(i, set()) for i in range(len(left))) else 'different'
