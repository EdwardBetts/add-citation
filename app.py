#!/usr/bin/python3

from flask import Flask, render_template, redirect, url_for, request
from citation import mediawiki, fatcat

app = Flask(__name__)
app.config.from_object('config.default')

@app.route('/')
def index():
    articles = [line[:-1] for line in open('articles')]
    return render_template('index.html', articles=articles)

@app.route('/enwiki/category/<path:cat>')
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
