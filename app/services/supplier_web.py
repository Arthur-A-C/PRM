"""Bounded, SSRF-safe collection of a supplier's official website (public pages of the same site only).

Two independent guards: every URL (start, redirect, link) is resolved and checked before the request, and the
connection itself is opened only to an address re-validated at connect time (no DNS-rebinding window).
No cookies, credentials, proxies from the environment or internal headers are ever sent.
"""
import html
import ipaddress
import json
import re
import socket
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import httpcore
import httpx

USER_AGENT = 'PRM-Fornecedores/1.0 (consulta pontual de dados cadastrais publicos)'
BLOCKED_NAMES = ('localhost', 'metadata.google.internal', 'metadata')
BLOCKED_SUFFIXES = ('.localhost', '.local', '.internal', '.lan', '.home', '.corp', '.intranet', '.localdomain', '.arpa')
SOCIAL = {'linkedin.com': 'LinkedIn', 'instagram.com': 'Instagram', 'youtube.com': 'YouTube', 'youtu.be': 'YouTube',
          'facebook.com': 'Facebook', 'fb.com': 'Facebook', 'x.com': 'X/Twitter', 'twitter.com': 'X/Twitter',
          'pinterest.com': 'Pinterest', 'teams.microsoft.com': 'Teams', 'teams.live.com': 'Teams',
          'wa.me': 'WhatsApp', 'api.whatsapp.com': 'WhatsApp', 'web.whatsapp.com': 'WhatsApp', 'chat.whatsapp.com': 'WhatsApp'}
KEYWORDS = {'contact': 9, 'contato': 9, 'fale-conosco': 9, 'contact-us': 9, 'contactus': 9, 'about': 7, 'sobre': 7,
            'quem-somos': 7, 'company': 6, 'empresa': 6, 'profile': 5, 'location': 5, 'address': 5, 'office': 4,
            'sales': 5, 'vendas': 5, 'support': 3, 'suporte': 3, 'impressum': 8, 'imprint': 8, 'legal': 2, 'team': 3}
SKIP_EXT = re.compile(r'\.(pdf|jpe?g|png|gif|webp|svg|zip|rar|7z|mp4|mp3|avi|mov|docx?|xlsx?|pptx?|exe|dmg|apk|ico|css|js|xml|json)$', re.I)
EMAIL = re.compile(r'[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}')
BLOCK_TAGS = {'p', 'div', 'br', 'li', 'tr', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'section', 'article', 'footer',
              'header', 'address', 'table', 'ul', 'ol', 'dd', 'dt', 'nav'}


class Blocked(ValueError):
    """URL refused by the navigation policy (scheme, port, private network, other site)."""


class FetchError(RuntimeError):
    pass


def resolve(host, port):
    return socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)


def public_ip(text):
    try:
        ip = ipaddress.ip_address(str(text).split('%')[0])
    except ValueError:
        return False
    if ip.version == 6:
        if ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        elif ip.sixtofour or ip.teredo or ip.is_site_local:
            return False
    bad = ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified
    return ip.is_global and not bad


def check_host(host, port):
    """Resolves and returns only public addresses; any private/reserved answer blocks the whole host."""
    name = (host or '').strip('[]').rstrip('.').lower()
    if not name or name in BLOCKED_NAMES or name.endswith(BLOCKED_SUFFIXES) or '.' not in name and ':' not in name:
        raise Blocked('Endereço não permitido.')
    try:
        literal = ipaddress.ip_address(name)
    except ValueError:
        literal = None
    if literal is not None and not public_ip(name):
        raise Blocked('Endereço aponta para rede interna/privada e foi bloqueado.')
    try:
        infos = resolve(name, port)
    except (socket.gaierror, UnicodeError, OSError):
        raise Blocked('Domínio não encontrado.') from None
    addresses = sorted({info[4][0] for info in infos})
    if not addresses or not all(public_ip(a) for a in addresses):
        raise Blocked('Endereço aponta para rede interna/privada e foi bloqueado.')
    return addresses


def normalize_url(raw):
    raw = (raw or '').strip()
    if not raw:
        raise Blocked('Informe o site oficial do fornecedor.')
    if '://' not in raw:
        raw = 'https://' + raw
    parts = urlsplit(raw)
    if parts.scheme.lower() not in {'http', 'https'}:
        raise Blocked('Somente endereços http/https são permitidos.')
    if parts.username or parts.password:
        raise Blocked('URL com credenciais não é permitida.')
    try:
        port = parts.port
    except ValueError:
        raise Blocked('Porta inválida.') from None
    if port not in (None, 80, 443):
        raise Blocked('Somente as portas padrão 80/443 são permitidas.')
    host = (parts.hostname or '').lower()
    if not host:
        raise Blocked('URL sem domínio.')
    try:
        host = host.encode('idna').decode('ascii')
    except UnicodeError:
        raise Blocked('Domínio inválido.') from None
    netloc = host if port is None else f'{host}:{port}'
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or '/', parts.query, ''))


def check_url(url):
    url = normalize_url(url)
    parts = urlsplit(url)
    check_host(parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80))
    return url


def site_host(host):
    host = (host or '').lower().rstrip('.')
    return host[4:] if host.startswith('www.') else host


def same_site(url, base):
    host = site_host(urlsplit(url).hostname)
    return host == base or host.endswith('.' + base)


class SafeBackend(httpcore.SyncBackend):
    """Connects only to an address validated at connect time; TLS still verifies the original hostname."""

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        address = check_host(host, port)[0]
        return super().connect_tcp(address, port, timeout=timeout, local_address=local_address, socket_options=socket_options)


class SafeTransport(httpx.HTTPTransport):
    def __init__(self):
        super().__init__(trust_env=False, retries=0)
        self._pool = httpcore.ConnectionPool(ssl_context=httpx.create_ssl_context(trust_env=False), max_connections=4,
                                             retries=0, network_backend=SafeBackend())


def make_transport():
    return SafeTransport()


class PageParser(HTMLParser):
    SKIP = {'script', 'style', 'noscript', 'svg', 'template', 'iframe', 'canvas', 'head'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.footer, self.links, self.jsonld, self.meta = [], [], [], [], {}
        self.title, self._skip, self._footer, self._anchor, self._jsonld, self._title = '', 0, 0, None, None, False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or '') for k, v in attrs}
        if tag == 'script' and 'ld+json' in a.get('type', '').lower():
            self._jsonld = []
        if tag == 'title':
            self._title = True
        if tag == 'meta' and a.get('content'):
            key = (a.get('property') or a.get('name') or '').lower()
            if key in {'description', 'og:site_name', 'og:title', 'og:description', 'twitter:site'}:
                self.meta[key] = a['content'][:500]
        if tag in self.SKIP:
            self._skip += 1
        if tag == 'footer':
            self._footer += 1
        if tag == 'a' and a.get('href'):
            self._anchor = [a['href'], []]
        if tag in BLOCK_TAGS:
            self._emit('\n')

    def handle_endtag(self, tag):
        if tag == 'script' and self._jsonld is not None:
            self.jsonld.append(''.join(self._jsonld))
            self._jsonld = None
        if tag == 'title':
            self._title = False
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == 'footer' and self._footer:
            self._footer -= 1
        if tag == 'a' and self._anchor:
            self.links.append((self._anchor[0], ' '.join(self._anchor[1]).strip()[:120]))
            self._anchor = None
        if tag in BLOCK_TAGS:
            self._emit('\n')

    def handle_data(self, data):
        if self._jsonld is not None:
            self._jsonld.append(data)
            return
        if self._title:
            self.title += data
        if self._skip:
            return
        if self._anchor:
            self._anchor[1].append(data.strip())
        self._emit(data)

    def _emit(self, data):
        if self._skip:
            return
        (self.footer if self._footer else self.text).append(data)


def clean(parts, limit):
    text = re.sub(r'[ \t\r\f\v]+', ' ', ''.join(parts))
    text = re.sub(r'\n\s*\n+', '\n', text).strip()
    return text[:limit]


def phone_digits(value):
    return re.sub(r'\D', '', value or '')


def email_kind(email):
    local = email.split('@')[0].lower()
    if re.search(r'sale|venda|comercial|commercial|business|order|pedido|quote|cotac', local):
        return 'commercial'
    if re.search(r'financ|billing|account|cobranc|fatura|invoice|pagament|payable', local):
        return 'financial'
    return 'general'


def jsonld_orgs(raw_blocks):
    found = []
    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            kind = node.get('@type')
            kinds = kind if isinstance(kind, list) else [kind]
            if any(isinstance(k, str) and k in {'Organization', 'Corporation', 'LocalBusiness', 'Store', 'Manufacturer',
                                                'OnlineStore', 'WholesaleStore', 'ProfessionalService'} for k in kinds):
                found.append(node)
            for key in ('@graph', 'publisher', 'author', 'brand', 'manufacturer', 'mainEntity'):
                if key in node:
                    walk(node[key])
    for raw in raw_blocks[:10]:
        try:
            walk(json.loads(raw[:200000]))
        except (ValueError, RecursionError):
            continue
    return found[:5]


@dataclass
class Page:
    url: str
    title: str = ''
    text: str = ''
    footer: str = ''
    emails: list = field(default_factory=list)
    phones: list = field(default_factory=list)
    whatsapp: list = field(default_factory=list)
    social: list = field(default_factory=list)
    organizations: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    internal: list = field(default_factory=list)


def parse_page(url, body, base, text_limit):
    parser = PageParser()
    try:
        parser.feed(body)
        parser.close()
    except Exception:  # malformed HTML: keep what was parsed
        pass
    page = Page(url=url, title=clean([parser.title], 200), text=clean(parser.text, text_limit),
                footer=clean(parser.footer, 4000), meta=parser.meta, organizations=jsonld_orgs(parser.jsonld))
    seen = set()
    for href, label in parser.links:
        href = html.unescape(href.strip())
        low = href.lower()
        if low.startswith('mailto:'):
            email = unquote(href[7:].split('?')[0]).strip()
            if EMAIL.fullmatch(email) and email.lower() not in seen:
                seen.add(email.lower())
                page.emails.append(email)
            continue
        if low.startswith('tel:'):
            number = unquote(href[4:]).strip()
            if 6 <= len(phone_digits(number)) <= 16 and number not in page.phones:
                page.phones.append(number)
            continue
        absolute = urljoin(url, href)
        parts = urlsplit(absolute)
        if parts.scheme not in {'http', 'https'}:
            continue
        host = site_host(parts.hostname)
        network = next((name for domain, name in SOCIAL.items() if host == domain or host.endswith('.' + domain)), None)
        if network == 'WhatsApp':
            query = re.search(r'phone=([\d+%]+)', parts.query or '')
            digits = phone_digits(parts.path) or phone_digits(unquote(query.group(1)) if query else '')
            if 8 <= len(digits) <= 16 and digits not in page.whatsapp:
                page.whatsapp.append(digits)
            elif absolute not in [s[1] for s in page.social]:
                page.social.append((network, absolute))
        elif network:
            if absolute not in [s[1] for s in page.social] and len(absolute) < 400:
                page.social.append((network, absolute))
        elif same_site(absolute, base) and not SKIP_EXT.search(parts.path or ''):
            page.internal.append((urlunsplit((parts.scheme, parts.netloc, parts.path or '/', parts.query, '')), label))
    for email in EMAIL.findall(page.text + '\n' + page.footer):
        if email.lower() not in seen and not email.lower().endswith(('.png', '.jpg', '.webp', '.gif')):
            seen.add(email.lower())
            page.emails.append(email)
    return page


def link_score(url, label):
    target = (urlsplit(url).path + ' ' + (label or '')).lower().replace('_', '-').replace(' ', '-')
    return max((weight for word, weight in KEYWORDS.items() if word in target), default=0)


def fetch(client, url, max_bytes):
    """GET with manual, re-validated redirects. Returns (final_url, html) or raises Blocked/FetchError."""
    for _ in range(6):
        url = check_url(url)
        client.cookies.clear()
        try:
            with client.stream('GET', url) as response:
                if response.status_code in (301, 302, 303, 307, 308) and response.headers.get('location'):
                    url = urljoin(url, response.headers['location'])
                    continue
                if response.status_code != 200:
                    raise FetchError(f'HTTP {response.status_code}')
                kind = response.headers.get('content-type', '').lower()
                if 'html' not in kind and 'xml' not in kind:
                    raise FetchError('Conteúdo não é HTML')
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    chunks.append(chunk)
                    if size >= max_bytes:
                        break
                body = b''.join(chunks)[:max_bytes]
                return url, body.decode(response.encoding or 'utf-8', errors='replace')
        except httpx.TimeoutException:
            raise FetchError('Tempo esgotado') from None
        except httpx.HTTPError as exc:
            cause = exc.__cause__ or exc.__context__
            if isinstance(cause, Blocked):
                raise cause from None
            raise FetchError(type(exc).__name__) from None
    raise FetchError('Redirecionamentos demais')


@dataclass
class Site:
    start_url: str
    base: str
    pages: list
    warnings: list


def crawl(start, settings, transport=None, clock=time.monotonic):
    """Home + the most relevant internal pages (contact/about/company...), bounded by pages, bytes and time."""
    url = check_url(start)
    deadline = clock() + settings.supplier_ai_crawl_seconds
    warnings, pages = [], []
    with httpx.Client(transport=transport or make_transport(), follow_redirects=False, trust_env=False,
                      timeout=httpx.Timeout(settings.supplier_ai_fetch_timeout_seconds),
                      headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,application/xhtml+xml'}) as client:
        try:
            final, body = fetch(client, url, settings.supplier_ai_page_max_bytes)
        except FetchError as exc:
            if not start.strip().lower().startswith(('http://', 'https://')):
                try:  # only when the user typed no scheme: HTTPS first, then HTTP
                    final, body = fetch(client, 'http://' + urlsplit(url).netloc + urlsplit(url).path,
                                        settings.supplier_ai_page_max_bytes)
                    warnings.append('Site sem HTTPS; usada a versão HTTP.')
                except FetchError:
                    raise FetchError(f'Não foi possível abrir o site ({exc}).') from None
            else:
                raise FetchError(f'Não foi possível abrir o site ({exc}).') from None
        base = site_host(urlsplit(final).hostname)
        if base != site_host(urlsplit(url).hostname):
            warnings.append(f'O endereço informado redirecionou para {base}; analisado somente esse site.')
        home = parse_page(final, body, base, settings.supplier_ai_page_text_chars)
        pages.append(home)
        visited = {final.rstrip('/'), url.rstrip('/')}
        queue = sorted({u: link_score(u, l) for u, l in home.internal}.items(), key=lambda x: -x[1])
        queue = [u for u, score in queue if score > 0]
        skipped = 0
        while queue and len(pages) < settings.supplier_ai_max_pages:
            if clock() > deadline:
                warnings.append('Tempo máximo de coleta atingido; páginas restantes não analisadas.')
                break
            link = queue.pop(0)
            if link.rstrip('/') in visited or not same_site(link, base):
                continue
            visited.add(link.rstrip('/'))
            try:
                final_link, body = fetch(client, link, settings.supplier_ai_page_max_bytes)
            except (FetchError, Blocked):
                skipped += 1
                continue
            if not same_site(final_link, base):
                continue
            page = parse_page(final_link, body, base, settings.supplier_ai_page_text_chars)
            if page.footer == home.footer:
                page.footer = ''  # repeated footer: sent once, with the home page
            pages.append(page)
            known = set(queue) | visited
            extra = [(u, link_score(u, l)) for u, l in page.internal if u not in known and u.rstrip('/') not in visited]
            queue += [u for u, s in sorted(extra, key=lambda x: -x[1]) if s >= 5]
        if skipped:
            warnings.append(f'{skipped} página(s) do site não puderam ser abertas.')
    return Site(start_url=final, base=base, pages=pages, warnings=warnings)
