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



@attr.s()
class Post(object):
    name = attr.ib()
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
    post_file = os.path.join(
        POSTS, now.strftime(POST_DATE_FORMAT) + '.md'
    )
    call([EDITOR, post_file])


class MathJaxPattern(markdown.inlinepatterns.Pattern):

    def __init__(self, md):
        markdown.inlinepatterns.Pattern.__init__(self, r'\\\((.+?)\\\)', md)

    def handleMatch(self, m):
        return self.markdown.htmlStash.store(
            cgi.escape(m.group(0))

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
        date = soup.select('dd.post-date')[0].text.strip()
        url = '/posts/' + os.path.basename(post)
        posts.append(Post(
            name=os.path.basename(post),
            date=date, url=url,
            body='\n'.join(map(str, soup.select('#the-post')[0].children))
        ))

    posts.sort(key=lambda p: p.name, reverse=True)


    with open(INDEX_PAGE, 'w') as o:
        o.write(TEMPLATE_LOOKUP.get_template('index.html').render(
            posts=posts,
        ))
