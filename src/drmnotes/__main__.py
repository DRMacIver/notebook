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
import urllib
from urllib.parse import urlparse
import json
import requests
import random
from prompt_toolkit.shortcuts import radiolist_dialog


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


def json_cached(f):
    @cached
    @functools.wraps(f)
    def returns_json(*args):
        return json.dumps(f(*args))

    @functools.wraps(f)
    def accept(*args):
        return json.loads(returns_json(*args))

    return accept


def cached(f):
    name = f.__name__

    cache = {}

    @functools.wraps(f)
    def accept(*args):
        key = cache_key(":".join(args))

        try:
            return cache[key]
        except KeyError:
            pass
        db = database()
        cursor = db.cursor()
        cursor.execute(
            "create table if not exists cache_objects(name text, key unsigned bigint, result text, unique (name, key))"
        )
        cursor.execute(
            "select result from cache_objects where name = ? and key = ?", (name, key)
        )
        row = cursor.fetchone()
        if row is None:
            result = f(*args)
            cursor.execute(
                "insert into cache_objects(name, key, result) values(?, ?, ?)",
                (name, key, result),
            )
        else:
            result = row[0]
        db.commit()
        cache[key] = result
        return result

    return accept


@json_cached
def fetch(url):
    try:
        req = requests.head(url)

        content_types = req.headers.get("content-type", ("text/html",))
        if "text/html" in content_types:
            req = requests.get(req.url)
            text = req.text
        else:
            text = None
    except requests.ConnectionError:
        return {"url": url, "contents": None, "status": None}

    return {"url": req.url, "contents": text, "status": req.status_code}


@cached
def title(url):
    parsed = urlparse(url)
    if parsed.netloc in ("", "notebook.drmaciver.com"):
        if parsed.path == "/":
            return "My Notebook"
        else:
            assert parsed.path.startswith("/posts/")
            name = parsed.path[len("/posts/") : -len(".html")]
            return post_object(name).title
    fetched = fetch(url)
    if fetched["status"] != 200:
        return None
    contents = fetched["contents"]
    if contents is None:
        return None
    soup = BeautifulSoup(contents, "html.parser")
    title = soup.find("title")
    if title is None:
        return None
    return re.compile("\s+", re.MULTILINE).sub(" ", title.text).strip()


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

    links = attr.ib()


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

assert os.path.exists(os.path.join(ROOT, "setup.py"))

CACHE_DIR = os.path.join(ROOT, ".cache")


TEMPLATES = os.path.join(ROOT, "templates")
POSTS = os.path.join(ROOT, "posts")

HTML_ROOT = os.path.join(ROOT, "docs")

INDEX_PAGE = os.path.join(HTML_ROOT, "index.html")

HTML_POSTS = os.path.join(HTML_ROOT, "posts")

EDITOR = "vim"


TEMPLATE_LOOKUP = TemplateLookup(
    directories=[TEMPLATES, POSTS],
    module_directory=os.path.join(CACHE_DIR, "mako_modules"),
)


@click.group()
def main():
    pass


POST_DATE_FORMAT = "%Y-%m-%d-%H:%M"


def contents(filename):
    try:
        with open(filename) as i:
            return i.read()
    except FileNotFoundError:
        pass


def edit_and_commit_post(name, prompt=None):
    post_file = os.path.join(POSTS, name + ".md")

    exists = os.path.exists(post_file)

    assert not (exists and prompt)

    if prompt:
        with open(post_file, "w") as o:
            o.write(prompt)

    prev = contents(post_file)

    call([EDITOR, post_file])

    if contents(post_file) == prev:
        if not exists and os.path.exists(post_file):
            os.unlink(post_file)
        return

    do_build(rebuild=False)
    files = [post_file, os.path.join(HTML_POSTS, name + ".html")]
    git("add", *files)
    git("add", "-u", HTML_ROOT)

    if prev:
        git("commit", "-m", "Edit post %r" % (name,))
    else:
        git("commit", "-m", "Add new post %r" % (name,))


@main.command(name="new-post")
def new_post():
    now = datetime.now()
    name = now.strftime(POST_DATE_FORMAT)
    edit_and_commit_post(name)


@attr.s()
class Book:
    title = attr.ib()
    author = attr.ib()
    url = attr.ib()
    page_range = attr.ib()


CANON = [
    Book(
        title="Leisure: The Basis of Culture",
        author="Josef Pieper",
        url="https://amzn.to/3gnbo5l",
        page_range=(3, 156),
    ),
    Book(
        title="Voices: The Educational Formation of Conscience",
        author="Thomas F. Green",
        url="https://amzn.to/2X0wxe2",
        page_range=(1, 210),
    ),
    Book(
        title="Conflict is Not Abuse",
        author="Sarah Schulman",
        url="https://amzn.to/3emI4ud",
        page_range=(15, 285),
    ),
    Book(
        title="How to talk about books you haven't read",
        author="Pierre Bayard",
        url="https://amzn.to/2yzEkGq",
        page_range=(3, 185),
    ),
    Book(
        title="Finding Our Sea-Legs",
        author="Will Buckingham",
        url="https://amzn.to/3d3M3vs",
        page_range=(1, 180),
    ),
    Book(
        title="Ritual and its Consequences",
        author="Seligman, Weller, Puett, and Simon",
        url="https://amzn.to/3d55qUM",
        page_range=(3, 197),
    ),
    Book(
        title="Epistemic Injustice: Power and the Ethics of Knowing",
        author="Miranda Fricker",
        url="https://amzn.to/3d3aby7",
        page_range=(1, 177),
    ),
    Book(
        title="all about love",
        author="bell hooks",
        url="https://amzn.to/2WYa559",
        page_range=(3, 237),
    ),
    Book(
        title="the wave in the mind",
        author="Ursula K. Le Guin",
        url="https://amzn.to/3d13X1P",
        page_range=(3, 301),
    ),
    Book(
        title="Two Cheers for Anarchism",
        author="James C. Scott",
        url="https://amzn.to/3c2iusJ",
        page_range=(1, 149),
    ),
    Book(
        title="Sorting Things Out: Classification and its Consequences",
        author="Bowker and Star",
        url="https://amzn.to/2A9stPS",
        page_range=(1, 333),
    ),
    Book(
        title="Rewriting the Rules",
        author="Meg-John Barker",
        url="https://amzn.to/36wKnYH",
        page_range=(2, 366),
    ),
]


@main.command(name="book-post")
def book_post():

    book = random.choice(CANON)

    while True:
        page = random.randint(*book.page_range)
        result = radiolist_dialog(
            values=[
                ("yes", "Yes"),
                ("new-book", "Pick a different book"),
                ("new-page", "Pick a different page"),
            ],
            text=f"Would you like to write about {book.title} page {page}?",
        ).run()

        if result == "yes":
            break
        elif result == "new-book":
            book = random.choice(CANON)
        elif result == "new-page":
            pass
        else:
            assert result is None
            return

    prompt = f"From [{book.title}]({book.url}) by {book.author}, page {page}:"

    now = datetime.now()
    name = now.strftime(POST_DATE_FORMAT)
    edit_and_commit_post(name, prompt=prompt)


@main.command(name="edit-post")
@click.argument("name", default="")
def edit_post(name):
    if not name:
        name = max(os.listdir(POSTS))
    name = os.path.basename(name)
    name = name.replace(".md", "")
    edit_and_commit_post(name)


class MathJaxExtension(markdown.Extension):
    def extendMarkdown(self, md, md_globals):
        # Needs to come before escape matching because \ is pretty important in LaTeX
        md.inlinePatterns.add("mathjax", MathJaxPattern(md), "<escape")


class MathJaxPattern(markdown.inlinepatterns.Pattern):
    def __init__(self, md):
        markdown.inlinepatterns.Pattern.__init__(self, r"\\\((.+?)\\\)", md)

    def handleMatch(self, m):
        return self.markdown.htmlStash.store(r"\(" + cgi.escape(m.group(2)) + r"\)")


LATEX_BLOCK = r"(\\begin{[^}]+}.+?\\end{[^}]+})"
LATEX_EXPR = r"(\\\(.+?\\\))"


DEL_RE = r"(~~)(.*?)~~"


class MathJaxAlignExtension(markdown.Extension):
    def extendMarkdown(self, md, md_globals):
        # Needs to come before escape matching because \ is pretty important in LaTeX
        md.inlinePatterns.add("mathjaxblocks", HtmlPattern(LATEX_BLOCK, md), "<escape")
        md.inlinePatterns.add("mathjaxexprs", HtmlPattern(LATEX_EXPR, md), "<escape")
        md.inlinePatterns.add("del", SimpleTagPattern(DEL_RE, "del"), ">not_strong")


@cached
def md(text):
    return markdown.markdown(
        text,
        extensions=[
            MathJaxAlignExtension(),
            "markdown.extensions.fenced_code",
            "markdown.extensions.codehilite",
        ],
    )


PULL_IN_TAGS = re.compile("\s+</", re.MULTILINE)
PULL_IN_FULL_STOP = re.compile(r">\s+\.", re.MULTILINE)


def clean_html(soup):
    return str(soup)


@main.command()
@click.option("--rebuild/--no-rebuild", default=False)
@click.option("--full/--posts-only", default=True)
@click.argument("name", default="")
def build(rebuild, full, name):
    do_build(rebuild, full, name)


def cache_key(s):
    return int.from_bytes(hashlib.sha1(s.encode("utf-8")).digest()[:4], "big")


def post_names():
    return [os.path.basename(f)[:-3] for f in glob(os.path.join(POSTS, "*.md"))]


def mine(url):
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc in (
        "drmaciver.com",
        "notebook.drmaciver.com",
        "drmaciver.substack.com",
        "",
    )


def ignore_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.path == "/" and mine(url):
        return True
    if parsed.netloc in ("twitter.com", "www.twitter.com"):
        return True
    if fetch(url)["status"] != 200:
        return True
    return False


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

    with database() as db:

        cursor = db.cursor()

        cursor.execute(
            """
            create table if not exists posts(
                name text, key unsigned bigint, date text, body text, title text,
                unique (name, key)
            )
        """
        )

        cursor.execute(
            """
            create table if not exists links(
                name text, key unsigned bigint, url text, sort_order unsigned bigint,
                unique (name, key, url)
            )
        """
        )

        cursor.execute(
            "select date, title, body from posts where key = ? and name = ?",
            (key, name),
        )

        row = cursor.fetchone()
        if row is not None:
            date, title, body = row
            cursor.execute(
                "select url from links where key = ? and name = ? order by sort_order",
                (key, name),
            )
            links = [url for url, in cursor if not ignore_url(url)]
        else:
            soup = BeautifulSoup(contents, "html.parser")
            title_elts = soup.select("p.subtitle")

            if not title_elts:
                title = name
            else:
                title = " ".join(map(str, title_elts[0].contents))
            body = "\n".join(map(str, soup.select("#the-post")[0].children))
            date = soup.select("dd.post-date")[0].text.strip()
            cursor.execute(
                "insert into posts (key, name, date, title, body) values (?, ?, ?, ?, ?)",
                (key, name, date, title, body),
            )
            links = []
            for index, a in enumerate(soup.select("a")):
                href = a["href"]
                if ignore_url(href):
                    continue
                if href in links:
                    continue
                links.append(href)
                cursor.execute(
                    "insert into links (key, name, url, sort_order) values (?, ?, ?, ?)",
                    (key, name, href, index),
                )
        db.commit()
    url = "/posts/" + name + ".html"
    result = Post(
        original_file=os.path.join(POSTS, name + ".md"),
        name=name,
        date=date,
        url=url,
        body=body,
        title=title,
        links=links,
    )
    POSTS_CACHE[name] = result
    return result


@cached
def post_html(name, source_text):
    source_html = md(source_text)
    soup = BeautifulSoup(source_html, "html.parser")

    title_elt = soup.find("h1")

    if title_elt is None:
        title = None
    else:
        title = " ".join(map(str, title_elt.contents))
        title_elt.decompose()

    for d in [3, 2]:
        for f in soup.findAll("h%d" % (d,)):
            f.name = "h%d" % (d + 1,)

    date = datetime.strptime(name, POST_DATE_FORMAT)
    post_template = TEMPLATE_LOOKUP.get_template("post.html")

    return post_template.render(
        post=clean_html(soup),
        title=title,
        date=date.strftime("%Y-%m-%d"),
        url=f"https://notebook.drmaciver.com/posts/{name}.html",
    )


def do_build(rebuild=False, full=True, name=""):
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
            rebuild
            or not os.path.exists(dest)
            or os.path.getmtime(source) > os.path.getmtime(dest)
        ):
            continue

        with open(source) as i:
            source_text = i.read()

        with open(dest, "w") as o:
            o.write(post_html(name, source_text))

    if not full:
        return

    for post in glob(os.path.join(HTML_POSTS, "*.html")):
        source = os.path.join(POSTS, os.path.basename(post).replace(".html", ".md"))
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

    with open(INDEX_PAGE, "w") as o:
        o.write(
            TEMPLATE_LOOKUP.get_template("index.html").render(
                new_posts=new_posts,
                old_posts=old_posts,
                title="Thoughts from David R. MacIver",
            )
        )

    fg = FeedGenerator()
    fg.id("https://notebook.drmaciver.com/")
    fg.title("DRMacIver's notebook")
    fg.author({"name": "David R. MacIver", "email": "david@drmaciver.com"})
    fg.link(href="https://notebook.drmaciver.com", rel="alternate")
    fg.link(href="https://notebook.drmaciver.com/feed.xml", rel="self")
    fg.language("en")

    dates = []

    for post in sorted(posts, key=lambda p: p.date, reverse=True)[:10]:
        fe = fg.add_entry()
        fe.id("https://notebook.drmaciver.com" + post.url)
        fe.link(href="https://notebook.drmaciver.com" + post.url)
        fe.title(post.title or post.name)
        fe.content(post.body, type="html")
        updated = (
            subprocess.check_output(
                [
                    "git",
                    "log",
                    "-1",
                    "--date=iso8601",
                    '--format="%ad"',
                    "--",
                    post.original_file,
                ]
            )
            .decode("ascii")
            .strip()
            .strip('"')
        )
        if updated:
            updated = dateutil.parser.parse(updated)
        else:
            updated = datetime.strptime(
                post.name.replace(".html", ""), POST_DATE_FORMAT
            ).replace(tzinfo=tz.gettz())
        dates.append(updated)
        fe.updated(updated)

    fg.updated(max(dates))

    fg.atom_file(os.path.join(HTML_ROOT, "feed.xml"), pretty=True)
