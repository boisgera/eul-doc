#!/usr/bin/env python

# Python 3 Standard Library
import datetime
import os.path
import re
import urllib3

# Third-Party Libraries
import pandoc
from pandoc.types import (
    BulletList,
    Code,
    Cite,
    DefinitionList,
    Emph,
    Format,
    Header,
    HorizontalRule,
    Image,
    OrderedList,
    LineBreak,
    Link,
    Math,
    MetaInlines,
    Note,
    Para,
    Plain,
    Quoted,
    RawInline,
    SmallCaps,
    SoftBreak,
    Space,
    Span,
    Str,
    Strikeout,
    Strong,
    Subscript,
)


# Helpers
# ------------------------------------------------------------------------------
def find_parent(root, elt):
    return find_location(root, elt)[0]


def find_location(root, elt):
    for elt_, path in pandoc.iter(root, path=True):
        if elt_ is elt:
            return path[-1]


# Transforms
# ------------------------------------------------------------------------------
def turn_separators_into_headers(doc):
    # Pandoc has a very little support for in-place substitution so far :(
    separators = [elt for elt in iter(doc) if isinstance(elt, HorizontalRule)]
    for separator in separators:
        # find the separator parent and location in parent
        parent, i = find_location(doc, separator)
        # substitute an empty level 3 header
        parent[i] = Header(3, ("", [], []), [])
    return doc


def remove_separators(doc):
    # Pandoc has a very little support for in-place substitution so far :(
    separators = [elt for elt in iter(doc) if isinstance(elt, HorizontalRule)]
    for separator in separators:
        # find the separator parent and location in parent
        parent, i = find_location(doc, separator)
        del parent[i]
    return doc


def remove_preview_links(doc):
    # Pandoc has a very little support for in-place substitution
    links = [elt for elt in pandoc.iter(doc) if isinstance(elt, Link)]
    for link in links:
        attrs, inlines, target = link[:]
        _, classes, _ = attrs
        if "preview" in classes:
            # find the link parent (a list) and location in parent
            parent, i = find_location(doc, link)
            # substitute to the links its content
            parent[i : i + 1] = inlines
    return doc


# Warning: proof sections won't end with tombstones.
# Need to be handle in js.
def lightweight_sections(doc, level=3):
    List = (OrderedList, BulletList, DefinitionList)

    def is_lightweight_section(elt):
        "True for paragraphs or plain text that starts with strong item"
        if isinstance(elt, (Para, Plain)):
            content = elt[0]
            if len(content) >= 1 and isinstance(content[0], Strong):
                return True
        return False

    for elt, path in pandoc.iter(doc, path=True):
        if isinstance(elt, Para) and is_lightweight_section(elt):
            para = elt
            if not any(isinstance(parent, List) for parent, index in path):
                blocks, index = find_location(doc, para)
                inlines = para[0]
                content = inlines.pop(0)[0]
                zwnj = RawInline(Format("html"), "&zwnj;")  # Zero-width non-joiner
                if len(inlines) >= 1 and inlines[0] == Space():
                    inlines.pop(0)
                inlines.insert(0, zwnj)
                # The function `blocks.index` --
                # that checks equality instead of identity --
                # won't always work.
                for index, elt in enumerate(blocks):
                    if elt is para:
                        break
                header = Header(level, ("", [], []), content)
                blocks.insert(index, header)
    return doc


def string_id(inlines):
    """To derive the identifier from the header text,

    - Remove all formatting, links, etc.
    - Remove all footnotes.
    - Remove all punctuation, except underscores, hyphens, and periods.
    - Replace all spaces and newlines with hyphens.
    - Convert all alphabetic characters to lowercase.
    - Remove everything up to the first letter (identifiers may not begin with a
      number or punctuation mark).
    - If nothing is left after this, use the identifier `section`."""
    parts = []
    for inline in inlines:
        part = None
        type_ = type(inline)
        if isinstance(inline, Str):
            part = inline[0]
        elif isinstance(inline, (Space, SoftBreak, LineBreak)):
            part = " "
        elif isinstance(inline, (Emph, Strikeout, Subscript, SmallCaps)):
            part = string_id(inline[0])
        elif isinstance(inline, (Cite, Image, Link, Quoted, Span)):
            part = string_id(inline[1])
        elif isinstance(inline, (Code, Math, RawInline)):
            part = inline[1]
        elif isinstance(inline, Note):
            part = ""
        else:
            raise TypeError("invalid type {0!r}".format(type_))
        parts.append(part)
    text = "".join(parts)
    text = text.lower()
    text = text.replace(" ", "-")
    text = re.sub("[^a-z0-9\_\-\.]", "", text)
    match = re.search("[a-z].*", text)
    if match is not None:
        return match.group()
    else:
        return "section"


def auto_identifiers(doc):
    headers = [elt for elt in pandoc.iter(doc) if type(elt) is Header]
    for header in headers:
        level, attr, inlines = header[:]
        id_, classes, kv = attr
        if not id_:
            id_ = string_id(inlines)
            header[:] = [level, (id_, classes, kv), inlines]
    # manage duplicate ids
    id_map = {}
    for header in headers:
        id_ = header[1][0]
        id_map.setdefault(id_, []).append(header)
    for id_, headers in id_map.items():
        if len(headers) > 1:
            for i, header in enumerate(headers):
                if i >= 1:
                    level, attr, inlines = header[:]
                    _, classes, kv = attr
                    new_id = id_ + "-" + str(i)
                    attr = new_id, classes, kv
                    header[:] = level, attr, inlines
    return doc


# TODO: solve the duplicated anchor in TOC.
def autolink_headings(doc):
    # TODO: link the document title (if any) to "#"
    meta = doc[0][0]
    title = meta.get("title")
    if title is not None and type(title) is MetaInlines:
        inlines = title[0]
        title[0] = [Link(("", [], []), inlines, ("#", ""))]

    headers = [elt for elt in pandoc.iter(doc) if type(elt) is Header]
    for header in headers:
        # We forbid nested links (see HTML spec).
        # Instead we should probably "unlink" the inner elts and always
        # apply the outer linkage for consistency.
        if not any(elt for elt in pandoc.iter(header[2]) if type(elt) is Link):
            id_ = header[1][0]
            target = ("#" + id_, "")
            link = Link(("", [], []), header[2], target)
            header[2] = [link]
    return doc


def convert_images(doc):
    images = [elt for elt in pandoc.iter(doc) if type(elt) is Image]
    for image in images:
        attr, inlines, target = image
        url, title = target
        base, _ = os.path.splitext(url)
        svg_url = base + ".svg"
        if svg_url.startswith("http://"):
            open_ = urllib3.open
        else:
            open_ = open
            try:
                open_(svg_url)
                new_url = svg_url
            except (IOError, urllib3.HTTPError):
                new_url = url
        new_target = (new_url, title)
        image[:] = (attr, inlines, new_target)
    return doc


# Alignement of tombstone are an issue when they are the single elt on the line.
# This is a general issue with single math span, not something specific of the
# tombstone ... line-height hack doesn't work either ...
def hfill(doc):
    def match(elt):
        if type(elt) is RawInline:
            format, text = elt[:]
            if format == Format("tex") and text.strip() == "\\hfill":
                return True
        return False

    hfills = [elt for elt in pandoc.iter(doc) if match(elt)]
    for hfill_ in hfills:
        inlines = find_parent(doc, hfill_)
        for index, elt in enumerate(inlines):
            if elt is hfill_:
                break
        style = "float:right;"
        zwnj = RawInline(Format("html"), "&zwnj;")  # I hate you CSS.
        span = Span(("", ["tombstone"], [("style", style)]), [zwnj] + inlines[index:])
        inlines[:] = inlines[:index] + [span]
    return doc


def today(doc):
    """
    Add the current date in metadata if the field is empty.
    """
    metadata = doc[0][0]
    if "date" not in metadata:
        date = datetime.date.today()
        day = date.day
        year = date.year
        months = """January February March April May June July August 
                     September October November December""".split()
        month = months[date.month - 1]
        meta = doc[0][0]
        inlines = [Str(month), Space(), Str(day + ","), Space(), Str(year)]
        meta["date"] = MetaInlines(inlines)
    return doc


# Targets
# ------------------------------------------------------------------------------
def pdf_transform(doc):
    doc = today(doc)
    doc = remove_separators(doc)
    doc = remove_preview_links(doc)
    return doc


def html_transform(doc):
    doc = turn_separators_into_headers(doc)
    doc = lightweight_sections(doc)
    doc = auto_identifiers(doc)
    doc = autolink_headings(doc)
    doc = convert_images(doc)
    doc = hfill(doc)
    doc = today(doc)
    return doc
