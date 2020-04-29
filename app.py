#!/usr/bin/python3

from flask import Flask, render_template, redirect, url_for, request, session, g, jsonify
from citation import mediawiki, fatcat, mediawiki_oauth
from citation.error_mail import setup_error_mail
from werkzeug.exceptions import InternalServerError
from werkzeug.debug.tbtools import get_current_traceback
from requests_oauthlib import OAuth1Session
from collections import defaultdict
import inspect

app = Flask(__name__)
app.config.from_object('config.default')
setup_error_mail(app)

def get_url_pair(src):
    by_rel = defaultdict(list)
    for i in src:
        by_rel[i['rel']].append(i['url'])

    if len(src) == 2 and len(by_rel['webarchive']) == 1:
        other_key = next(key for key in by_rel.keys() if key != 'webarchive')
        return {'web': by_rel[other_key][0], 'archive': by_rel['webarchive'][0]}

def pick_urls(src):
    chosen = get_url_pair(src)
    return set(chosen.values()) if chosen else set()

@app.errorhandler(InternalServerError)
def exception_handler(e):
    tb = get_current_traceback()
    last_frame = next(frame for frame in reversed(tb.frames) if not frame.is_library)
    last_frame_args = inspect.getargs(last_frame.code)
    return render_template('show_error.html',
                           tb=tb,
                           last_frame=last_frame,
                           last_frame_args=last_frame_args), 500

@app.before_request
def global_user():
    g.user = mediawiki_oauth.get_username()

@app.route('/')
def index():
    if 'title' in request.args:
        title = request.args['title'].strip().replace(' ', '_')
        if title:
            return redirect(url_for('article_page', title=title))
    articles = [line[:-1] for line in open('data/articles')]
    return render_template('index.html', articles=articles)

@app.route('/enwiki/Category:<path:cat>')
def category_page(cat):
    if ' ' in cat:
        return redirect(url_for(request.endpoint, cat=cat.replace(' ', '_')))

    cat = cat.replace('_', ' ')
    members = mediawiki.get_category_members(cat)
    return render_template('category.html',
                           title=cat,
                           members=members)

def build_citation_dict(t):
    doi = t.get('doi').value.strip()
    cite_title = t.get('title').value.strip()
    item = fatcat.lookup_doi(doi)
    return {
        'title': cite_title,
        'doi': doi,
        'template': t,
        'item': item,
        'urls': fatcat.get_urls_from_fatcat(item),
    }

@app.route('/enwiki/<path:title>', methods=['GET', 'POST'])
def article_page(title):
    if request.method == 'POST':
        return save_article(title)

    if ' ' in title:
        return redirect(url_for(request.endpoint, title=title.replace(' ', '_')))
    title = title.replace('_', ' ')

    article_props = mediawiki.get_article_props(title)

    if 'missing' in article_props:
        return render_template('missing.html', title=title), 404

    wikicode = mediawiki.get_wikicode(title)
    templates = mediawiki.templates_with_doi(wikicode) if wikicode else []
    citations = [build_citation_dict(t) for t in templates]

    return render_template('article.html',
                           title=title,
                           extract=article_props['extract'],
                           cats=article_props['categories'],
                           pick_urls=pick_urls,
                           citations=citations)

def date_from_web_archive_url(archive_url):
    web_archive_start = 'https://web.archive.org/web/'
    offset = len(web_archive_start)

    assert archive_url.startswith(web_archive_start)
    archive_date_str = archive_url[offset:offset + 8]
    assert archive_date_str.isdigit()
    year = archive_date_str[:4]
    month = archive_date_str[4:6]
    day = archive_date_str[6:8]
    archive_date = f'{year}-{month}-{day}'

    return archive_date

def preview_save(title):
    title = title.replace('_', ' ')
    wikicode = mediawiki.get_wikicode(title)
    assert wikicode
    templates = mediawiki.templates_with_doi(wikicode)
    citations = [build_citation_dict(t) for t in templates]
    citations = [cite for cite in citations if cite['urls']]

def nbsp_at_start(line):
    ''' Protect spaces at the start of a string. '''
    space_count = 0
    for c in line:
        if c != ' ':
            break
        space_count += 1
    # return Markup('&nbsp;') * space_count + line[space_count:]
    return '\u00A0' * space_count + line[space_count:]


def save_article(title):
    title = title.replace('_', ' ')
    wikicode = mediawiki.get_wikicode(title)
    assert wikicode
    update_wikicode(wikicode)

    return render_template('preview.html',
                           title=title,
                           wikitext=str(wikicode),
                           nbsp_at_start=nbsp_at_start)
    # return str(wikicode), 200, {'Content-Type': 'text/plain'}

def update_wikicode(wikicode):
    templates = mediawiki.templates_with_doi(wikicode)
    citations = [build_citation_dict(t) for t in templates]
    citations = [cite for cite in citations if cite['urls']]

    max_cite_params = max(int(key[5:]) for key in request.form
                          if key.startswith('cite_'))

    assert max_cite_params == len(citations)
    assert all(request.form[f'doi_{num}'] == cite['doi']
               for num, cite in enumerate(citations, start=1))

    for num, cite in enumerate(citations, start=1):
        file_choice = int(request.form[f'cite_{num}'])
        if file_choice == 0:
            continue

        t = cite['template']
        files = [f for f in cite['item']['files'] if f.get('urls')]
        f = files[file_choice - 1]
        assert f['urls']
        url_pair = get_url_pair(f['urls'])
        assert url_pair

        archive_date = date_from_web_archive_url(url_pair['archive'])
        t.add('url', url_pair['web'])
        t.add('format', 'PDF')
        t.add('archive-url', url_pair['archive'])
        t.add('archive-date', archive_date)

    return wikicode

@app.route('/oauth/start')
def start_oauth():
    next_page = request.args.get('next')
    if next_page:
        session['after_login'] = next_page

    client_key = app.config['CLIENT_KEY']
    client_secret = app.config['CLIENT_SECRET']
    base_url = 'https://en.wikipedia.org/w/index.php'
    request_token_url = base_url + '?title=Special%3aOAuth%2finitiate'

    oauth = OAuth1Session(client_key,
                          client_secret=client_secret,
                          callback_uri='oob')
    fetch_response = oauth.fetch_request_token(request_token_url)

    session['owner_key'] = fetch_response.get('oauth_token')
    session['owner_secret'] = fetch_response.get('oauth_token_secret')

    base_authorization_url = 'https://en.wikipedia.org/wiki/Special:OAuth/authorize'
    authorization_url = oauth.authorization_url(base_authorization_url,
                                                oauth_consumer_key=client_key)
    return redirect(authorization_url)

@app.route("/oauth/callback", methods=["GET"])
def oauth_callback():
    base_url = 'https://en.wikipedia.org/w/index.php'
    client_key = app.config['CLIENT_KEY']
    client_secret = app.config['CLIENT_SECRET']

    oauth = OAuth1Session(client_key,
                          client_secret=client_secret,
                          resource_owner_key=session['owner_key'],
                          resource_owner_secret=session['owner_secret'])

    oauth_response = oauth.parse_authorization_response(request.url)
    verifier = oauth_response.get('oauth_verifier')
    access_token_url = base_url + '?title=Special%3aOAuth%2ftoken'
    oauth = OAuth1Session(client_key,
                          client_secret=client_secret,
                          resource_owner_key=session['owner_key'],
                          resource_owner_secret=session['owner_secret'],
                          verifier=verifier)

    oauth_tokens = oauth.fetch_access_token(access_token_url)
    session['owner_key'] = oauth_tokens.get('oauth_token')
    session['owner_secret'] = oauth_tokens.get('oauth_token_secret')

    next_page = session.get('after_login')
    return redirect(next_page) if next_page else index()

@app.route('/oauth/disconnect')
def oauth_disconnect():
    for key in 'owner_key', 'owner_secret', 'username', 'after_login':
        if key in session:
            del session[key]
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
