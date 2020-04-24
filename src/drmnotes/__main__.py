import click
from datetime import datetime
import os
from subprocess import call
from glob import glob
from mako.lookup import TemplateLookup
import markdown
from bs4 import BeautifulSoup
import attr
import cgi
from feedgen.feed import FeedGenerator
import subprocess
from dateutil import tz
import re
from markdown.inlinepatterns import HtmlPattern, SimpleTagPattern
import dateutil
import sqlite3
import hashlib
import functools


_DATABASE = None

def database():
    global _DATABASE
    if _DATABASE is None:
        try:
            os.makedirs(CACHE_DIR)
        except FileExistsError:
            pass
        _DATABASE = sqlite3.connect(os.path.join(CACHE_DIR, "cache.db"))
    return _DATABASE

def cached(f):
    name = f.__name__

    cache = {}

    @functools.wraps(f)
    def accept(*args):
        key = cache_key(':'.join(args))

        try:
            return cache[key]
        except KeyError:
            pass
        db = database()
        cursor = db.cursor()
        cursor.execute("create table if not exists cache_objects(name text, key unsigned bigint, result text, unique (name, key))")
        cursor.execute("select result from cache_objects where name = ? and key = ?", (name, key))
        row = cursor.fetchone()
        if row is None:
            result = f(*args)
            cursor.execute("insert into cache_objects(name, key, result) values(?, ?, ?)", (name, key, result))
        else:
            result = row[0]
        db.commit()
        cache[key] = result
        return result

    return accept

def git(*args):
    subprocess.check_call(["git", *args])

@attr.s()
class Post(object):
    original_file = attr.ib()
    name = attr.ib()
    title = attr.ib()
    date = attr.ib()
    body = attr.ib()
    url = attr.ib()


ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__),
    '..', '..',
))

assert os.path.exists(os.path.join(ROOT, 'setup.py'))

CACHE_DIR = os.path.join(ROOT, '.cache')


TEMPLATES = os.path.join(ROOT, 'templates')
POSTS = os.path.join(ROOT, 'posts')

HTML_ROOT = os.path.join(ROOT, 'docs')

INDEX_PAGE = os.path.join(HTML_ROOT, 'index.html')

HTML_POSTS = os.path.join(HTML_ROOT, 'posts')

EDITOR = 'vim'


TEMPLATE_LOOKUP = TemplateLookup(
    directories=[TEMPLATES, POSTS],
    module_directory=os.path.join(CACHE_DIR, 'mako_modules')
)


@click.group()
def main():
    pass


POST_DATE_FORMAT = '%Y-%m-%d-%H:%M'

def contents(filename):
    try:
        with open(filename) as i:
            return i.read()
    except FileNotFoundError:
        pass


def edit_and_commit_post(name):
    post_file = os.path.join(
        POSTS, name + '.md'
    )

    prev = contents(post_file)

    call([EDITOR, post_file])

    if contents(post_file) == prev:
        return

    do_build(rebuild=False)
    files = [post_file, os.path.join(HTML_POSTS, name + '.html')]
    git("add", *files)
    git("add", "-u", HTML_ROOT)
    git("commit", "-m", "Add new post %r" % (name,))


@main.command(name='new-post')
def new_post():
    now = datetime.now()
    name = now.strftime(POST_DATE_FORMAT) 
    edit_and_commit_post(name)


@main.command(name='edit-post')
@click.argument('name', default='')
def edit_post(name):
    if not name:
        name = max(os.listdir(POSTS))
    name = os.path.basename(name)
    name = name.replace('.md', '')
    edit_and_commit_post(name)



class MathJaxExtension(markdown.Extension):
    def extendMarkdown(self, md, md_globals):
        # Needs to come before escape matching because \ is pretty important in LaTeX
        md.inlinePatterns.add('mathjax', MathJaxPattern(md), '<escape')


class MathJaxPattern(markdown.inlinepatterns.Pattern):

    def __init__(self, md):
        markdown.inlinepatterns.Pattern.__init__(self, r'\\\((.+?)\\\)', md)

    def handleMatch(self, m):
        return self.markdown.htmlStash.store(
            r"\(" + cgi.escape(m.group(2)) + r"\)"
        )


LATEX_BLOCK = r"(\\begin{[^}]+}.+?\\end{[^}]+})"
LATEX_EXPR = r"(\\\(.+?\\\))"


DEL_RE = r'(~~)(.*?)~~'



class MathJaxAlignExtension(markdown.Extension):
    def extendMarkdown(self, md, md_globals):
        # Needs to come before escape matching because \ is pretty important in LaTeX
        md.inlinePatterns.add('mathjaxblocks', HtmlPattern(LATEX_BLOCK, md), '<escape')
        md.inlinePatterns.add('mathjaxexprs', HtmlPattern(LATEX_EXPR, md), '<escape')
        md.inlinePatterns.add('del', SimpleTagPattern(DEL_RE, 'del') , '>not_strong')


@cached
def md(text):
    return markdown.markdown(
        text, extensions=[
            MathJaxAlignExtension(),
            'markdown.extensions.fenced_code',
            'markdown.extensions.codehilite',
        ]
    )


PULL_IN_TAGS = re.compile("\s+</", re.MULTILINE)
PULL_IN_FULL_STOP = re.compile(r">\s+\.", re.MULTILINE)


def clean_html(soup):
    return str(soup)


@main.command()
@click.option('--rebuild/--no-rebuild', default=False)
@click.option('--full/--posts-only', default=True)
@click.argument('name', default='')
def build(rebuild, full, name):
    do_build(rebuild, full, name)


def cache_key(s):
    return int.from_bytes(hashlib.sha1(s.encode('utf-8')).digest()[:4], 'big')


def post_names():
    return [
        os.path.basename(f)[:-3] for f in glob(os.path.join(POSTS, "*.md"))
    ]


POSTS_CACHE = {}

def post_object(name):
    try:
        return POSTS_CACHE[name]
    except KeyError:
        pass
    post_html_file = os.path.join(HTML_POSTS, name + ".html")
    
    with open(post_html_file) as i:
        contents = i.read()

    key = cache_key(contents)

    db = database()

    cursor = db.cursor()

    cursor.execute("""
        create table if not exists posts(
            name text, key unsigned bigint, date text, body text, title text,
            unique (name, key)
        )
    """)

    cursor.execute("select date, title, body from posts where key = ? and name = ?", (key, name))

    row = cursor.fetchone()
    if row is not None:
        date, title, body = row
    else:
        soup = BeautifulSoup(contents, 'html.parser')
        title_elts = soup.select("p.subtitle")

        if not title_elts:
            title = name
        else:
            title = ' '.join(map(str, title_elts[0].contents))
        body = '\n'.join(map(str, soup.select('#the-post')[0].children))
        date = soup.select('dd.post-date')[0].text.strip()
        cursor.execute("insert into posts (key, name, date, title, body) values (?, ?, ?, ?, ?)", (
            key, name, date, title, body
        ))
    db.commit()
    url = '/posts/' + name + ".html"
    result = Post(
        original_file=os.path.join(POSTS, name + ".md"),
        name=name,
        date=date, url=url,
        body=body,
        title=title,
    )
    POSTS_CACHE[name] = result
    return result

@cached
def post_html(name, source_text):
    source_html = md(source_text)
    soup = BeautifulSoup(source_html, 'html.parser')

    title_elt = soup.find("h1")

    if title_elt is None:
        title = None
    else:
        title = ' '.join(map(str, title_elt.contents))
        title_elt.decompose()

    for d in [3, 2]:
        for f in soup.findAll('h%d' % (d,)):
            f.name = 'h%d' % (d + 1,)

    date = datetime.strptime(name, POST_DATE_FORMAT)
    post_template = TEMPLATE_LOOKUP.get_template("post.html")

    return post_template.render(
        post=clean_html(soup),
        title=title,
        date=date.strftime('%Y-%m-%d'),
    )


def do_build(rebuild=False, full=True, name=''):
    only = name

    try:
        os.makedirs(HTML_POSTS)
    except FileExistsError:
        pass

    for name in post_names():
        source = os.path.join(POSTS, name + ".md")
        if not name.startswith(only):
            continue

        dest = os.path.join(HTML_POSTS, name + ".html")

        if not (
            rebuild or
            not os.path.exists(dest) or
            os.path.getmtime(source) > os.path.getmtime(dest)
        ):
            continue

        with open(source) as i:
            source_text = i.read()

        with open(dest, 'w') as o:
            o.write(post_html(name, source_text))


    if not full:
        return

    for post in glob(os.path.join(HTML_POSTS, "*.html")):
        source = os.path.join(
            POSTS, os.path.basename(post).replace('.html', '.md')
        )
        if not os.path.exists(source):
            os.unlink(post)

    posts = [post_object(name) for name in post_names()]

    posts.sort(key=lambda p: p.name, reverse=True)

    new_count = 5
    new_posts = posts[:new_count]

    old_posts = []

    for post in posts[new_count:]:
        date = dateutil.parser.parse(post.date)
        date = f"{date.year}-{date.month:02d}"

        if not old_posts or date != old_posts[-1][0]:
            old_posts.append((date, []))
        old_posts[-1][-1].append(post)


    with open(INDEX_PAGE, 'w') as o:
        o.write(TEMPLATE_LOOKUP.get_template('index.html').render(
            new_posts=new_posts, old_posts=old_posts, title="Thoughts from David R. MacIver",
        ))


    fg = FeedGenerator()
    fg.id('https://notebook.drmaciver.com/')
    fg.title("DRMacIver's notebook")
    fg.author( {'name':'David R. MacIver','email':'david@drmaciver.com'} )
    fg.link(href='https://notebook.drmaciver.com', rel='alternate')
    fg.link(href='https://notebook.drmaciver.com/feed.xml', rel='self')
    fg.language('en')

    dates = []

    for post in sorted(posts, key=lambda p: p.date, reverse=True)[:10]:
        fe = fg.add_entry()
        fe.id('https://notebook.drmaciver.com' + post.url)
        fe.link(href='https://notebook.drmaciver.com' + post.url)
        fe.title(post.title or post.name)
        fe.content(post.body, type="html")
        updated = subprocess.check_output([
        "git", "log", "-1", '--date=iso8601', '--format="%ad"', "--", post.original_file,
        ]).decode('ascii').strip().strip('"')
        if updated:
            updated = dateutil.parser.parse(updated)
        else:
            updated = datetime.strptime(post.name.replace('.html', ''), POST_DATE_FORMAT).replace(
                tzinfo=tz.gettz()
            )
        dates.append(updated)
        fe.updated(updated)

    fg.updated(max(dates))

    fg.atom_file(os.path.join(HTML_ROOT, 'feed.xml'), pretty=True)
