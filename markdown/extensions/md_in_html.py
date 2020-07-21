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
import xml.etree.ElementTree as etree
from html.parser import HTMLParser


# Block-level tags in which the content only gets span level parsing
span_tags = ['address', 'dd', 'dt', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'legend', 'li', 'p', 'td', 'th']

# Block-level tags in which the content gets parsed as blocks
block_tags = [
    'address', 'article', 'aside', 'blockquote', 'body', 'colgroup', 'details', 'div', 'dl', 'fieldset',
    'figcaption', 'figure', 'footer', 'form', 'iframe', 'header', 'hr', 'main', 'menu', 'nav',  'map',
    'noscript', 'object', 'ol', 'section', 'table', 'tbody', 'thead', 'tfoot', 'tr', 'ul'
]

# Block-level tags which never get their content parsed.
raw_tags = ['canvas', 'math', 'option', 'pre', 'script', 'style', 'textarea']

block_level_tags = span_tags + block_tags + raw_tags


class HTMLTreeBuilder(HTMLParser):
    """ Parser a string of HTML into an ElementTree object. """

    def __init__(self, htmlStash, *args, **kwargs):
        if 'convert_charrefs' not in kwargs:
            kwargs['convert_charrefs'] = False
        super().__init__(*args, **kwargs)
        self.htmlStash = htmlStash

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
        if 'p' in self.stack and tag in block_level_tags:
            # Close unclosed 'p' tag
            self.handle_endtag('p')
        # Valueless attr (ex: `<tag checked>`) results in `[('checked', None)]`. Convert to `{'checked': 'checked'}`.
        attrs = {key: value if value is not None else key for key, value in attrs}
        self.stack.append(tag)
        self.treebuilder.start(tag, attrs)

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
        self.treebuilder.comment(data)

    def handle_entityref(self, name):
        self.treebuilder.data('&{};'.format(name))

    def handle_charref(self, name):
        self.treebuilder.data('&#{};'.format(name))

    def stash(self, text):
        placeholder = self.htmlStash.store(text)
        self.handle_starttag('p', {})
        self.handle_data(placeholder)
        self.handle_endtag('p')

    def handle_decl(self, decl):
        self.stash('<!{}>'.format(decl))

    def unknown_decl(self, data):
        end = ']]>' if data.startswith('CDATA[') else ']>'
        self.stash('<![{}{}'.format(data, end))


def parse_html(data, htmlStash=None):
    """ Parser a string of HTML and return the toplevel element as an etree Element instance. """
    parser = HTMLTreeBuilder(htmlStash, convert_charrefs=False)
    parser.feed(data)
    return parser.close()


class MarkdownInHtmlProcessor(BlockProcessor):
    """Process Markdown Inside HTML Blocks."""

    def test(self, parent, block):
        m = util.HTML_PLACEHOLDER_RE.match(block)
        if m:
            self.index = int(m.group(1))
            element = self.parser.md.htmlStash.tag_data[self.index]
            if element is not None and 'markdown' in element.attrs:
                return True
        return False

    def parse_element_content(self, element, override=None):
        """
        Parse content as Markdown.

        If `markdown="1"` and tag is not a `block_tag` or `markdown="block", then the text
        content is parsed as block level markdown and appended as children on the element.
        If 'markdown="1" and tag is a `span_tag` or `markdown="span"`, then only span level
        parsing will be done on the text content. If no `markdown` attribute is set on the
        element, the `markdown` attribute is set to anythign except "1", "block" or "span",
        or the tag is not a known `block_tag` or 'span_tag, then the text content is converted
        to an AtomicString, so that no processing will happen on it.

        When `override` is set, the more restrictive value between `override` and the `markdown`
        attribute of the element is used. `override` is set by the parent element as child
        elements are parsed recursively.
        """
        md_attr = element.attrib.pop('markdown', '0')
        if md_attr == 'markdown':
            # `<tag markdown>` is the same as `<tag markdown='1'>`.
            md_attr = '1'
        if override == '0' or (override == 'span' and md_attr != '0'):
            # Only use the override if it is more restrictive than the markdown attribute.
            md_attr = override

        if ((md_attr == '1' and element.tag in block_tags) or
                (md_attr == 'block' and element.tag in span_tags + block_tags)):
            # Parse content as block level
            # The order in which the different parts are parsed (text, children, tails) is important here
            # as the order of elements needs to be preserved. We can't be inserting items at a later point
            # in the current iteration as we don't want to do raw processing on elements created from
            # parsing Markdown text (for example). Therefore, the order of operations is children, tails, text.

            # Recursively parse existing children from raw HTML
            for child in list(element):
                self.parse_element_content(child)

            # Parse Markdown text in tail of children. Do this seperate to avoid raw HTML parsing.
            # Save the position of each item to be inserted later in reverse.
            tails = []
            for pos, child in enumerate(element):
                if child.tail:
                    block = child.tail
                    child.tail = ''
                    # Use a dummy placeholder element.
                    dummy = etree.Element('div')
                    self.parser.parseBlocks(dummy, block.split('\n'))
                    children = list(dummy)
                    children.reverse()
                    tails.append((pos + 1, children))

            # Insert the elements created from the tails in reverse.
            tails.reverse()
            for pos, tail in tails:
                for item in tail:
                    element.insert(pos, item)

            # Parse Markdown text content. Do this last to avoid raw HTML parsing.
            if element.text:
                block = element.text
                element.text = ''
                # Use a dummy placeholder element as the content needs to get inserted before existing children.
                dummy = etree.Element('div')
                self.parser.parseBlocks(dummy, block.split('\n'))
                children = list(dummy)
                children.reverse()
                for child in children:
                    element.insert(0, child)

        elif ((md_attr == '1' and element.tag in span_tags) or
              (md_attr == 'span' and element.tag in span_tags + block_tags)):
            # Parse content as span level only
            for child in list(element):
                self.parse_element_content(child, override='span')
        else:
            # Disable inline parsing for everything else
            element.text = util.AtomicString(element.text)
            for child in list(element):
                self.parse_element_content(child, override='0')
                if child.tail:
                    child.tail = util.AtomicString(child.tail)

    def run(self, parent, blocks):
        blocks.pop(0)
        raw_html = self.parser.md.htmlStash.rawHtmlBlocks[self.index]

        et_el = parse_html(raw_html, self.parser.md.htmlStash)
        self.parse_element_content(et_el)
        parent.append(et_el)


class MarkdownInHtmlExtension(Extension):
    """Add Markdown parsing in HTML to Markdown class."""

    def extendMarkdown(self, md):
        """ Register extension instances. """

        md.parser.blockprocessors.register(
            MarkdownInHtmlProcessor(md.parser), 'markdown_block', 105
        )


def makeExtension(**kwargs):  # pragma: no cover
    return MarkdownInHtmlExtension(**kwargs)
