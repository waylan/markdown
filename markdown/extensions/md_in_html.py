"""
Python-Markdown Markdown in HTML Extension
===============================

An implementation of [PHP Markdown Extra](http://michelf.com/projects/php-markdown/extra/)'s
parsing of Markdown syntax in raw HTML.

See <https://Python-Markdown.github.io/extensions/raw_html>
for documentation.

Copyright The Python Markdown Project

License: [BSD](https://opensource.org/licenses/bsd-license.php)

"""

from . import Extension
from ..blockprocessors import BlockProcessor
from .. import util
import re
import xml.etree.ElementTree as etree
from html.parser import HTMLParser


class HTMLTreeBuilder(HTMLParser):
    """ Parser a string of HTML into an ElementTree object. """

    def reset(self):
        """Reset this instance.  Lose all unprocessed data."""
        self.stack = []
        self.treebuilder = etree.TreeBuilder(insert_comments=True, insert_pis=True)
        super().reset()

    def close(self):
        """ Flush the buffer and return the toplevel element as an etree Element instance. """
        super().close()
        return self.treebuilder.close()

    def handle_starttag(self, tag, attrs):
        attribs = dict()
        for key, value in attrs:
            # Valueless attr (`<tag checked>`) results in `('checked', None)`. Convert to `{'checked': 'checked'}`.
            attribs[key] = value if value is not None else key
        self.stack.append(tag)
        self.treebuilder.start(tag, dict(attribs))

    def handle_endtag(self, tag):
        if tag in self.stack:
            while self.stack:
                # Close any unclosed children first, then this element
                item = self.stack.pop()
                self.treebuilder.end(item)
                if item == tag:
                    break
        else:
            # Treat orphan closing tag as an empty tag.
            self.handle_startendtag(tag, {})

    def handle_data(self, data):
        self.treebuilder.data(data)

    def handle_pi(self, data):
        self.treebuilder.pi(data)

    def handle_comment(self, data):
        self.treebuilder.comment(text)

    def handle_entityref(self, name):
        self.treebuilder.data('&{};'.format(name))

    def handle_charref(self, name):
        self.treebuilder.data('&#{};'.format(name))

    def handle_decl(decl):
        # TODO: Explore using a custom treebuilder which supports a `doctype` method.
        # See https://docs.python.org/3/library/xml.etree.elementtree.html#xml.etree.ElementTree.TreeBuilder.doctype
        self.treebuilder.data('<!{}>'.format(decl))

    def unknown_decl(self, data):
        end = ']]>' if data.startswith('CDATA[') else ']>'
        self.treebuilder.data('<![{}{}'.format(data, end))


def parse_html(data):
    """ Parser a string of HTML and return the toplevel element as an etree Element instance. """
    parser = HTMLTreeBuilder(convert_charrefs=False)
    parser.feed(data)
    return parser.close()


class MarkdownInHtmlProcessor(BlockProcessor):
    """Process Markdown Inside HTML Blocks."""
    def __init__(self, parser, span_tags):
        super().__init__(parser)
        self.span_tags = span_tags

    def test(self, parent, block):
        m = util.HTML_PLACEHOLDER_RE.match(block)
        if m:
            self.index = int(m.group(1))
            element = self.parser.md.htmlStash.tag_data[self.index]
            if element is not None and 'markdown' in element.attrs:
                return True
        return False

    def parse_element_content(self, element):
        """
        Parse content as Markdown.

        If the element has children, then any text content is not parsed as block level.
        If 'markdown="1" and tag is not a `span_tag` or `markdown="block", then the text
        content is parsed as block level markdown and appended as children on the element.
        If markdown is anything except 1 or block, or 'markdown="1" and tag is a `span_tag`,
        then no block level parsing will be done on the text content. If no markdown attribute
        is set on the element or `markdown="0", then the text content is set to an
        AtomicString, so that no inlne processing will happen either.
        """
        md_attr = element.attrib.pop('markdown') if 'markdown' in element.attrib else '0'
        if md_attr not in ['0', 'span'] and len(element):
            # handle children
            for child in list(element):
                self.parse_element_content(child)
        elif md_attr == 'block' or (md_attr in ['1', 'markdown'] and element.tag not in self.span_tags):
            # No children, parse text content
            block = element.text
            element.text = ''
            self.parser.parseBlocks(element, block.split('\n'))
        elif md_attr == '0':
            # Disable inline parsing
            element.text = util.AtomicString(element.text)

    def run(self, parent, blocks):
        blocks.pop(0)
        raw_html = self.parser.md.htmlStash.rawHtmlBlocks[self.index]

        et_el = parse_html(raw_html)
        self.parse_element_content(et_el)
        parent.append(et_el)


class MarkdownInHtmlExtension(Extension):
    """Add Markdown parsing in HTML to Markdown class."""

    def extendMarkdown(self, md):
        """ Register extension instances. """

        span_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'dd', 'dt', 'td', 'th', 'legend', 'address']
        md.parser.blockprocessors.register(
            MarkdownInHtmlProcessor(md.parser, span_tags), 'markdown_block', 105
        )


def makeExtension(**kwargs):  # pragma: no cover
    return MarkdownInHtmlExtension(**kwargs)
