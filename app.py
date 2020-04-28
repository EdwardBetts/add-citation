#!/usr/bin/python3

from flask import Flask, render_template, redirect, url_for, request, session, g
from citation import mediawiki, fatcat, mediawiki_oauth
from citation.error_mail import setup_error_mail
from werkzeug.exceptions import InternalServerError
from werkzeug.debug.tbtools import get_current_traceback
from requests_oauthlib import OAuth1Session
import inspect

app = Flask(__name__)
app.config.from_object('config.default')
setup_error_mail(app)

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

@app.route('/enwiki/<path:title>')
def article_page(title):
    if ' ' in title:
        return redirect(url_for(request.endpoint, title=title.replace(' ', '_')))

    title = title.replace('_', ' ')

    article_props = mediawiki.get_article_props(title)

    if 'missing' in article_props:
        return render_template('missing.html', title=title), 404

    templates = mediawiki.get_wiki_doi_templates(title)
    citations = []
    for t in templates:
        doi = t.get('doi').value.strip()
        cite_title = t.get('title').value.strip()
        item = fatcat.lookup_doi(doi)
        ret = {
            'title': cite_title,
            'doi': doi,
            'template': t,
            'item': item,
            'urls': fatcat.get_urls_from_fatcat(item),
        }
        citations.append(ret)

    return render_template('article.html',
                           title=title,
                           extract=article_props['extract'],
                           cats=article_props['categories'],
                           citations=citations)

@app.route('/oauth/start')
def start_oauth():
    next_page = request.args.get('next')
    if next_page:
        session['after_login'] = next_page

    client_key = app.config['CLIENT_KEY']
    client_secret = app.config['CLIENT_SECRET']
    base_url = 'https://www.wikidata.org/w/index.php'
    request_token_url = base_url + '?title=Special%3aOAuth%2finitiate'

    oauth = OAuth1Session(client_key,
                          client_secret=client_secret,
                          callback_uri='oob')
    fetch_response = oauth.fetch_request_token(request_token_url)

    session['owner_key'] = fetch_response.get('oauth_token')
    session['owner_secret'] = fetch_response.get('oauth_token_secret')

    base_authorization_url = 'https://www.wikidata.org/wiki/Special:OAuth/authorize'
    authorization_url = oauth.authorization_url(base_authorization_url,
                                                oauth_consumer_key=client_key)
    return redirect(authorization_url)

@app.route("/oauth/callback", methods=["GET"])
def oauth_callback():
    base_url = 'https://www.wikidata.org/w/index.php'
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
    return redirect(url_for('browse_page'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
