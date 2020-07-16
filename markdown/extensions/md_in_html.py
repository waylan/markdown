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
        md_attr = element.attrib.pop('markdown', 0)
        if md_attr not in ['0', 'span'] and len(element):
            # handle children
            for child in list(element):
                self.parse_element_content(child)
        elif md_attr == 'block' or (md_attr == '1' and element.tag not in self.span_tags):
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

        et_el = etree.fromstring(raw_html)
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
