"""Links in text bound for a forge: the ones it would show, raw or rendered, to unlisted hosts."""

import re

import ada_url
from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from markdown_it.rules_inline.backticks import backtick
from markdown_it.token import Token

from code_factory.platform.text.screen_reading import numbered

_PAGE = "https://github.com/"
# What a forge renders as a link, in any case: an address with a scheme, a protocol-relative
# `//host` and a bare `www.` name.
_LINK = re.compile(r"""(?:https?:)?//[^\s<>()\[\]"'`]+|\bwww\.[^\s<>()\[\]"'`]+""", re.IGNORECASE)
# What a forge's autolinker takes as one link: everything up to white space or `<`, so a `(`, `'`
# or `"` before an `@` leaves the text after it a host the reader's browser goes to.
_RUN = re.compile(r"(?:https?:)?//[^\s<]+|\bwww\.[^\s<]+", re.IGNORECASE)
# Punctuation that ends a sentence rather than an address, which a forge leaves out of a link.
_SENTENCE_END = ".,:;!?*_~"
# What may stand before a protocol-relative `//` for it to start a link: so `a//b` is none.
_OPENERS = frozenset("([<\"'`*_:")

# Every destination is kept as written: the validator that would turn `javascript:` links into
# text and the normaliser that would rewrite a destination are both replaced, so each link a
# reader's browser may follow is seen.
_MARKDOWN = MarkdownIt("commonmark", {"html": True}).enable("table").enable("strikethrough")
_MARKDOWN.validateLink = lambda url: True  # noqa: ARG005
_MARKDOWN.normalizeLink = lambda url: url


def _counting_code_newlines(state: StateInline, silent: bool) -> bool:
    """The code span rule, which turns a span's newlines into spaces, noting how many it held."""
    before = state.pos
    done = backtick(state, silent)
    if done and not silent and state.tokens and state.tokens[-1].type == "code_inline":
        state.tokens[-1].meta["newlines"] = state.src.count("\n", before, state.pos)
    return done


_MARKDOWN.inline.ruler.at("backticks", _counting_code_newlines)


def listed(host: str, hosts: list[str]) -> bool:
    """Whether the host is one of `hosts` or a name under one."""
    for entry in hosts:
        name = entry.strip().lower()
        if name and (host == name or host.endswith("." + name)):
            return True
    return False


def _host(url: str) -> str | None:
    try:
        return str(ada_url.parse_url(url)["hostname"]).lower()
    except ValueError:
        return None


def _absolute(link: str) -> str:
    if link.startswith("//"):
        return "https:" + link
    return "https://" + link if link[:4].lower() == "www." else link


def _raw_allowed(link: str, hosts: list[str]) -> bool:
    host = _host(_absolute(link))
    return host is not None and listed(host, hosts)


def _raw_host_unlisted(link: str, hosts: list[str]) -> bool:
    """Whether the whole run a forge links, read as an address, names a host not listed.

    Only a run with an `@` can name another host than the part up to a stop character does.
    """
    host = _host(_absolute(link)) if "@" in link else None
    return host is not None and not listed(host, hosts)


def _starts_a_word(line: str, start: int) -> bool:
    return start == 0 or line[start - 1].isspace() or line[start - 1] in _OPENERS


def _raw_unlisted(line: str, hosts: list[str]) -> bool:
    return any(
        not _raw_allowed(found.group(0).rstrip(_SENTENCE_END), hosts)
        for found in _LINK.finditer(line)
        if not found.group(0).startswith("//") or _starts_a_word(line, found.start())
    ) or any(
        _raw_host_unlisted(found.group(0).rstrip(_SENTENCE_END), hosts)
        for found in _RUN.finditer(line)
        if not found.group(0).startswith("//") or _starts_a_word(line, found.start())
    )


def _resolves_allowed(destination: str, hosts: list[str]) -> bool:
    """Whether a destination is a web address on a listed host.

    It is resolved as a browser resolves it against a page on github.com.
    """
    try:
        resolved = ada_url.parse_url(ada_url.join_url(_PAGE, destination))
    except ValueError:
        return False
    return resolved["protocol"] in {"http:", "https:"} and listed(
        str(resolved["hostname"]).lower(), hosts
    )


def _source_newlines(child: Token) -> int:
    """The newlines of the source a token spans that its own text no longer shows."""
    if child.type == "code_inline":
        return int(child.meta.get("newlines", 0))
    if child.type in {"html_inline", "image"}:
        return child.content.count("\n")
    return 0


def _held_in_inline(token: Token, hosts: list[str]) -> set[int]:
    first = token.map[0] + 1 if token.map is not None else 1
    breaks = 0
    held: set[int] = set()
    for child in token.children or []:
        if child.type in {"softbreak", "hardbreak"}:
            breaks += 1
            continue
        destination = {"link_open": "href", "image": "src"}.get(child.type)
        if destination is not None:
            if not _resolves_allowed(str(child.attrGet(destination) or ""), hosts):
                held.add(first + breaks)
        elif child.type == "html_inline" and "=" in child.content:
            held.add(first + breaks)
        breaks += _source_newlines(child)
    return held


def rendered_link_lines(text: str, hosts: list[str]) -> set[int]:
    """The lines holding a link a forge renders to a host not listed.

    Every link and image the text parses to counts (reference links, autolinks, entities and
    escapes decoded) when its destination is not a web address on a listed host, and so does any
    raw HTML with an attribute, which may carry one.
    """
    held: set[int] = set()
    for token in _MARKDOWN.parse(text):
        if token.type == "inline":
            held |= _held_in_inline(token, hosts)
        elif token.type == "html_block" and "=" in token.content and token.map is not None:
            held.add(token.map[0] + 1)
    return held


def link_lines(text: str, hosts: list[str]) -> list[int]:
    """The lines holding a link to a host not listed, raw or rendered, sorted, once each."""
    held = rendered_link_lines(text, hosts)
    held.update(number for number, line in numbered(text) if _raw_unlisted(line, hosts))
    return sorted(held)
