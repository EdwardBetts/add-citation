import requests
import mwparserfromhell

query_url = 'https://en.wikipedia.org/w/api.php'

def run_query(params, language_code='en'):
    base = {
        'format': 'json',
        'formatversion': 2,
        'action': 'query',
        'continue': '',
    }
    p = base.copy()
    p.update(params)

    r = requests.get(query_url, params=p)
    expect = 'application/json; charset=utf-8'
    success = True
    if r.status_code != 200:
        print('status code: {r.status_code}'.format(r=r))
        success = False
    if r.headers['content-type'] != expect:
        print('content-type: {r.headers[content-type]}'.format(r=r))
        success = False
    assert success
    json_reply = r.json()
    return json_reply['query']

def get_article_props(title):
    params = {
        'prop': 'extracts|categories',
        'exintro': '1',
        'clprop': 'hidden',
        'cllimit': 'max',
        'titles': title,
    }
    return run_query(params)['pages'][0]

def get_category_members(title):
    params = {
        'list': 'categorymembers',
        'cmtitle': 'Category:' + title,
        'cmlimit': 'max',
        'cmnamespace': '0',
    }
    return run_query(params)['categorymembers']

def get_wiki_doi_templates(title):
    params = {'prop': 'revisions', 'rvprop': 'content', 'titles': title}
    page = run_query(params)['pages'][0]
    assert title == page['title']
    if 'revisions' not in page:
        return []
    content = page['revisions'][0]['content']
    wikicode = mwparserfromhell.parse(content)
    return [t for t in wikicode.filter_templates() if t.has('doi')]
