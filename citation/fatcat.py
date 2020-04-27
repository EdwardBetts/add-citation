import requests
import urllib.parse
import os.path
import json

def lookup_doi(doi):
    lookup_url = 'https://api.fatcat.wiki/v0/release/lookup'
    doi_escaped = urllib.parse.quote_plus(doi)
    filename = f'cache/{doi_escaped}.html'
    if os.path.exists(filename):
        return json.load(open(filename))

    params = {'doi': doi, 'expand': 'files', 'hide': 'abstracts,refs'}
    r = requests.get(lookup_url, params=params)
    open(filename, 'w').write(r.text)
    return r.json()

def get_urls_from_fatcat(item):
    return [f['urls'] for f in item.get('files', []) if f['urls']]
