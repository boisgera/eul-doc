#!/usr/bin/env python

# Python 2.7 Standard Library
import __builtin__
import datetime
import json
import os.path
import re
import sys
import urllib2

# Third-Party Libraries
import pandoc
from pandoc.types import *

# Eul's Doc Metadata
from .about import *

# TODO
# ------------------------------------------------------------------------------
#
#   - support profiles (--html by default, implement --pdf too)
#   - support date for all profiles (if not hard-coded)
#  

# Helpers
# ------------------------------------------------------------------------------
def iter(elt, enter=None, exit=None):
    yield elt
    if enter is not None:
        enter(elt)
    if isinstance(elt, dict):
        elt = elt.items()
    if hasattr(elt, "__iter__"): # exclude strings
        for child in elt:
             for subelt in iter(child, enter, exit):
                 yield subelt
    if exit is not None:
        exit(elt)

def iter_path(elt):
    path = []
    def enter(elt_):
        path.append(elt_)
    def exit(elt_):
        path.pop()
    for elt_ in iter(elt, enter, exit):
        yield path + [elt_]

def find_parent(doc, elt):
    for path in iter_path(doc):
        elt_ = path[-1]
        parent = path[-2] if len(path) >= 2 else None
        if elt is elt_:
             return parent


# Transforms
# ------------------------------------------------------------------------------
def match_lightweight_section(elt):
    if type(elt) in (Para, Plain):
        content = elt[0]
        if len(content) >= 1 and type(content[0]) is Strong:
            return True
    return False

def lightweight_sections(doc, level=3):
    paras = filter(match_lightweight_section, iter(doc))
    for para in paras:
        blocks = find_parent(doc, para)
        content = para[0].pop(0)[0]
        zwnj = RawInline(Format("html"), u"&zwnj;")
        if len(para[0]) >= 1 and para[0][0] == Space():
            para[0].pop(0)
        para[0].insert(0, zwnj)
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
 - If nothing is left after this, use the identifier `section`.
"""
    parts = []
    for inline in inlines:
        part = None
        type_ = type(inline)
        if type_ is Str:
            part = inline[0]
        elif type_ in (Space, SoftBreak, LineBreak):
            part = " "
        elif type_ in (Emph, Strikeout, Subscript, SmallCaps):
            part = string_id(inline[0])
        elif type_ in (Cite, Image, Link, Quoted, Span):
            part = string_id(inline[1])
        elif type_ in (Code, Math, RawInline):
            part = inline[1]
        elif type_ is Note:
            part = ""
        else:
            raise TypeError("invalid type {0!r}".format(type_))
        parts.append(part)
    text = "".join(parts)
    text = text.lower()
    text = text.replace(" ", "-")
    text = re.sub("[^a-z0-9\_\-\.]","", text)
    match = re.search("[a-z].*", text)
    if match is not None:
        return match.group()
    else:
        return "section"

def auto_identifiers(doc):
    headers = [elt for elt in iter(doc) if type(elt) is Header]
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
                if i >=1:
                    level, attr, inlines = header[:]
                    _, classes, kv = attr
                    new_id = id_ + "-" + str(i)
                    attr = new_id, classes, kv
                    header[:] = level, attr, inlines
    return doc

def autolink_headings(doc):
    # TODO: link the document title (if any) to "#"
    meta = doc[0][0]
    title = meta.get("title")
    if title is not None and type(title) is MetaInlines:
        inlines = title[0]
        title[0] = [Link(("", [], []), inlines, ("#", ""))]

    headers = [elt for elt in iter(doc) if type(elt) is Header]
    for header in headers:
        # We forbid nested links (see HTML spec).
        # Instead we should probably "unlink" the inner elts and always
        # apply the outer linkage for consistency.
        if not any(elt for elt in iter(header[2]) if type(elt) is Link): 
            id_ = header[1][0]
            target = ("#"+id_, "")
            link = Link(("", [], []), header[2], target)
            header[2] = [link]
    return doc

def convert_images(doc):
    images = [elt for elt in iter(doc) if type(elt) is Image]
    for image in images:
        attr, inlines, target = image
        url, title = target
        base, ext = os.path.splitext(url)
        svg_url = base + ".svg"
        if svg_url.startswith("http://"):
            open_ = urllib2.open
        else:
            open_ = open
            try:
                open_(svg_url)
                new_url = svg_url
            except (IOError, urllib2.HTTPError):
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
            if format == Format("tex") and text.strip() == u"\\hfill":
                return True
        return False

    hfills = [elt for elt in iter(doc) if match(elt)]
    for hfill_ in hfills:
        inlines = find_parent(doc, hfill_)
        for index, elt in enumerate(inlines):
            if elt is hfill_:
              break
        style = "float:right;"
        zwnj = RawInline(Format("html"), u"&zwnj;") # I hate you CSS.
        span = Span(("", [], [("style", style)]), [zwnj] + inlines[index:])
        inlines[:] = inlines[:index] + [span]
    return doc

def today(doc):
    """
    Add the current date in metadata if the field is empty.
    """
    metadata = doc[0][0]
    if u"date" not in metadata:
        date = datetime.date.today()
        day = unicode(date.day)
        year = unicode(date.year)
        months = u"""January February March April May June July August 
                     September October November December""".split()
        month = months[date.month - 1]
        meta = doc[0][0]
        inlines = [Str(month), Space(), Str(day + ","), Space(), Str(year)]
        meta["date"] = MetaInlines(inlines)
    return doc


# Main Entry Point
# ------------------------------------------------------------------------------
def main():
    args = sys.argv[1:]
    doc = pandoc.read(json.load(sys.stdin))
    if "--pdf" in args:
        doc = today(doc)
    else:
        doc = lightweight_sections(doc)
        doc = auto_identifiers(doc)
        doc = autolink_headings(doc)
        doc = convert_images(doc)
        doc = hfill(doc)
        doc = today(doc)

    print json.dumps(pandoc.write(doc))

