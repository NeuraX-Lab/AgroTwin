"""Opt-in, allowlisted and bounded retrieval of official methodology references.

This is source retrieval, NOT arbitrary web search or scientific peer review.
"""
from __future__ import annotations
import re, ssl, urllib.request, urllib.parse
from html.parser import HTMLParser
from .core import timestamp

OFFICIAL_URLS=[
  'https://power.larc.nasa.gov/docs/services/api/temporal/daily/',
  'https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html',
  'https://research.google.com/colaboratory/faq.html',
]
ALLOWED={'power.larc.nasa.gov','scikit-learn.org','research.google.com'}

class Parser(HTMLParser):
    def __init__(self):
        super().__init__();self.text=[];self.ignored=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript'):self.ignored+=1
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript'):self.ignored=max(0,self.ignored-1)
    def handle_data(self,data):
        if not self.ignored and data.strip():self.text.append(data.strip())

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ValueError('HTTP redirect blocked; authorize updated URL explicitly.')

def fetch_sources():
    fetched=[]
    opener=urllib.request.build_opener(NoRedirect)
    for url in OFFICIAL_URLS:
        host=urllib.parse.urlsplit(url).hostname
        if host not in ALLOWED:continue
        record={'url':url,'retrieved_at':timestamp(),'verified':False}
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'NeuraX-research-audit/0.2','Accept':'text/html'})
            with opener.open(request,timeout=8) as response:
                content_type=response.headers.get_content_type()
                if content_type!='text/html':raise ValueError(f'Unsupported content type {content_type}')
                body=response.read(100000+1)
                if len(body)>100000:raise ValueError('Source exceeds bounded retrieval limit')
                parser=Parser();parser.feed(body.decode('utf-8',errors='replace'))
                content=re.sub(r'\s+',' ',' '.join(parser.text))
                record.update(status='retrieved',preview=content[:1000],verified=False,
                    note='Read source manually before using as evidence; this is an HTML preview, not a fact verification.')
        except Exception as ex:
            record.update(status='error',error=f'{type(ex).__name__}: {str(ex)[:180]}')
        fetched.append(record)
    return {'retrieved_at':timestamp(),'sources':fetched,
            'warning':'No arbitrary search; Codex/browser should follow research_queue queries, verify citations and avoid posting private data.'}
