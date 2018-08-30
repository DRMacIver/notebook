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


@main.command(name='new-post')
def new_post():
    now = datetime.now()
    name = now.strftime(POST_DATE_FORMAT) 
    post_file = os.path.join(
        POSTS, name + '.md'
    )
    call([EDITOR, post_file])
    build(rebuild=False)
    files = [post_file, os.path.join(HTML_POSTS, name + '.html')]
    git("add", *files)
    git("add", "-u", HTML_ROOT)
    git("commit", *files, "-m", "Add new post %r" % (name,))




class MathJaxPattern(markdown.inlinepatterns.Pattern):

    def __init__(self, md):
        markdown.inlinepatterns.Pattern.__init__(self, r'(?<!\\)(\$\$?)(.+?)\2', md)

    def handleMatch(self, m):
        # Pass the math code through, unmodified except for basic entity substitutions.
        # Stored in htmlStash so it doesn't get further processed by Markdown.
        text = cgi.escape(m.group(2) + m.group(3) + m.group(2))
        return self.markdown.htmlStash.store(text)


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

class MathJaxExtension(markdown.Extension):
    def extendMarkdown(self, md, md_globals):
        md.inlinePatterns.add('mathjax', MathJaxPattern(md), '<escape')


def md(text):
    return markdown.markdown(
        text, extensions=[
            MathJaxExtension(),
            'markdown.extensions.fenced_code',
            'markdown.extensions.codehilite',
        ]
    )


@main.command()
@click.option('--rebuild/--no-rebuild', default=False)
def build(rebuild):
    post_template = TEMPLATE_LOOKUP.get_template("post.html")

    try:
        os.makedirs(HTML_POSTS)
    except FileExistsError:
        pass

    for source in glob(os.path.join(POSTS, '*.md')):
        name = os.path.basename(source)
        dest = os.path.join(HTML_POSTS, name.replace('.md', '.html'))

        if not (
            rebuild or
            not os.path.exists(dest) or
            os.path.getmtime(source) > os.path.getmtime(dest)
        ):
            continue

        with open(source) as i:
            source_text = i.read()

        source_text = source_text.replace(r"\(", "$").replace(r"\)", "$")

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

        date = datetime.strptime(name.replace('.md', ''), POST_DATE_FORMAT)

        with open(dest, 'w') as o:
            o.write(post_template.render(
                post=soup.prettify(),
                title=title,
                date=date.strftime('%Y-%m-%d'),
            ))

    for post in glob(os.path.join(HTML_POSTS, "*.html")):
        source = os.path.join(
            POSTS, os.path.basename(post).replace('.html', '.md')
        )
        if not os.path.exists(source):
            os.unlink(post)

    posts = []

    for post in glob(os.path.join(HTML_POSTS, "*.html")):
        with open(post) as i:
            contents = i.read()
        soup = BeautifulSoup(contents, 'html.parser')
        title_elts = soup.select("p.subtitle")

        name = os.path.basename(post)

        if not title_elts:
            title = name.replace('.html', '')
        else:
            title = ' '.join(map(str, title_elts[0].contents))

        date = soup.select('dd.post-date')[0].text.strip()
        url = '/posts/' + os.path.basename(post)
        posts.append(Post(
            original_file=os.path.join(POSTS, name.replace('.html', '.md')),
            name=name,
            date=date, url=url,
            body='\n'.join(map(str, soup.select('#the-post')[0].children)),
            title=title,
        ))

    posts.sort(key=lambda p: p.name, reverse=True)


    with open(INDEX_PAGE, 'w') as o:
        o.write(TEMPLATE_LOOKUP.get_template('index.html').render(
            posts=posts,
        ))


    fg = FeedGenerator()
    fg.id('https://notebook.drmaciver.com/')
    fg.title("DRMacIver's notebook")
    fg.author( {'name':'David R. MacIver','email':'david@drmaciver.com'} )
    fg.link(href='https://notebook.drmaciver.com', rel='alternate')
    fg.link(href='https://notebook.drmaciver.com/feed.xml', rel='self')
    fg.language('en')

    for post in posts:
        fe = fg.add_entry()
        fe.id('https://notebook.drmaciver.com' + post.url)
        fe.link(href='https://notebook.drmaciver.com' + post.url)
        fe.title(post.title or post.name)
        updated = subprocess.check_output([
        "git", "log", "-1", '--date=iso8601', '--format="%ad"', "--", post.original_file,
        ]).decode('ascii').strip().strip('"')
        fe.updated(updated)

    fg.atom_file(os.path.join(HTML_ROOT, 'feed.xml'), pretty=True)
