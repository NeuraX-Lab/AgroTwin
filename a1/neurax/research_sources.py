"""Opt-in public research: bounded official pages plus bibliographic candidates."""
from __future__ import annotations
import hashlib
from html.parser import HTMLParser
import json
from urllib import error, parse, request

from .core import timestamp

SOURCES = {
    'nasa_power_daily': 'https://power.larc.nasa.gov/docs/services/api/temporal/daily/',
    'nasa_power_api': 'https://power.larc.nasa.gov/docs/services/api/',
    'nasa_earthdata': 'https://www.earthdata.nasa.gov/',
    'sklearn_gradient_boosting': 'https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html',
    'sklearn_temporal_cv': 'https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html',
    'google_colab_faq': 'https://research.google.com/colaboratory/faq.html',
    'fao_soil': 'https://www.fao.org/soils-portal/en/',
}
ALLOWED_HOSTS = {parse.urlsplit(x).hostname for x in SOURCES.values()}


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'svg'):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'svg'):
            self.hidden = max(0, self.hidden-1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


class _RestrictRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = parse.urlsplit(newurl)
        if u.scheme != 'https' or u.hostname not in ALLOWED_HOSTS:
            raise ValueError('Public source redirected to an unapproved destination')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_official_page(source: str) -> dict:
    if source not in SOURCES:
        raise ValueError('Unknown source; choose a registered official source ID')
    url = SOURCES[source]
    req = request.Request(url, headers={'User-Agent':'NeuraX-Research-Agent/0.4',
                                        'Accept':'text/html,text/plain'})
    with request.build_opener(_RestrictRedirect()).open(req, timeout=15) as resp:
        final = parse.urlsplit(resp.geturl())
        if final.scheme != 'https' or final.hostname not in ALLOWED_HOSTS:
            raise ValueError('Unexpected source response host')
        mime = resp.headers.get_content_type()
        if mime not in ('text/html', 'text/plain'):
            raise ValueError('Unsupported source content type')
        payload = resp.read(80001)
        if len(payload) > 80000:
            payload = payload[:80000]
        html = payload.decode('utf-8', errors='replace')
    if mime == 'text/html':
        parser = _TextParser()
        parser.feed(html)
        text = ' '.join(parser.parts)
    else:
        text = html
    return {'source_id':source,'url':url,'retrieved_at':timestamp(),
            'excerpt':text[:9000], 'excerpt_sha256': hashlib.sha256(text[:9000].encode()).hexdigest(),
            'status':'retrieved_excerpt_not_scientifically_reviewed',
            'truncated': len(text)>9000 or len(payload)>=80000,
            'note':'Verify meaning, current parameters and applicability before using as evidence.'}


def find_papers(topic: str) -> dict:
    q = str(topic).strip()[:170]
    if not q or any(c in q for c in ('\n', '\r', '{', '}')):
        raise ValueError('Use a short public bibliographic topic, never raw data')
    url = 'https://api.crossref.org/works?' + parse.urlencode(
        {'query.bibliographic': q, 'rows': 5, 'select': 'DOI,title,published,URL'})
    req = request.Request(url, headers={'User-Agent':'NeuraX-Research-Agent/0.4',
                                        'Accept':'application/json'})
    with request.urlopen(req, timeout=12) as resp:
        payload = resp.read(120001)
        if len(payload)>120000:
            raise ValueError('Bibliographic index response exceeds configured size limit')
    items=json.loads(payload)['message']['items']
    return {'topic':q,'source':'Crossref','retrieved_at':timestamp(),
            'status':'bibliographic_leads_not_paper_verified',
            'items':[{'title':(p.get('title') or [''])[0][:250],
                      'doi':p.get('DOI'), 'url':p.get('URL')} for p in items]}