#!/usr/bin/env python3
"""Fetch the licensed Mongolian corpora and derive the mn pack inputs.

Two sources, both redistributable:

  * Mongolian Wikipedia, CC BY-SA 4.0, the dated pages-articles dump.
  * Tatoeba Mongolian sentences, CC BY 2.0 FR.

Both downloads are pinned by SHA-256 so a rebuild either reproduces the same
pack or fails loudly instead of silently changing the data.

Writes:
  source/mn.txt             word<TAB>count, most frequent first
  source/mn_sentences.tsv   one sentence per line, for the next-word model
  source/mn-receipt.json    URLs, licences, digests, and what the derivation did
"""
import bz2
import collections
import hashlib
import html
import json
import pathlib
import re
import shutil
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source"

WIKI_URL = "https://dumps.wikimedia.org/mnwiki/20261101/mnwiki-20261101-pages-articles.xml.bz2"
WIKI_SHA256 = "224581a786698cf0d0ef23a442fbc0b592fd5e5492532eb9761c94954cc94fff"
WIKI_LICENSE = "CC-BY-SA-4.0"
WIKI_NAME = "Mongolian Wikipedia, pages-articles dump, 2026-11-01"

TATOEBA_URL = "https://downloads.tatoeba.org/exports/per_language/mon/mon_sentences.tsv.bz2"
TATOEBA_SHA256 = "9cc84dab554a5ba15fe657fc3a655e66671bd8e4e2e6960e3f09d63fef56fde8"
TATOEBA_LICENSE = "CC-BY-2.0-FR"
TATOEBA_NAME = "Tatoeba Mongolian sentence export"

# A Mongolian word: Cyrillic letters, optionally joined by a hyphen or an
# apostrophe. Latin runs, digits and punctuation are not words.
WORD = re.compile(r"[а-яёөү]+(?:[-'’][а-яёөү]+)*")
# Every letter the alphabet has, plus the two marks that only appear inside
# numbers in practice.
ALPHABET = set("абвгдеёжзийклмнопөпрстуүфхцчшщъьэюяы")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")

# Wikipedia markup that carries no running text.
DROP_BLOCKS = [
    re.compile(r"<!--.*?-->", re.S),
    re.compile(r"<ref[^>/]*>.*?</ref>", re.S | re.I),
    re.compile(r"<ref[^>]*/>", re.I),
    re.compile(r"<((?:math|gallery|timeline|pre|code|syntaxhighlight|poem|score|source))\b[^>]*>.*?</\1>", re.S | re.I),
    re.compile(r"<(?:math|gallery|timeline|pre|code|syntaxhighlight|poem|score|source)[^>]*/>", re.I),
]
# Tables, then templates, which nest.
DROP_TABLE = re.compile(r"\{[|].*?\|\}", re.S)
DROP_TEMPLATE = re.compile(r"\{\{.*?\}\}", re.S)
# Links into a namespace: files, images, categories, help pages in any
# language. A colon in the target marks one.
DROP_NAMED_LINK = re.compile(r"\[\[(?:[^|\]]*:)[^|\]]*(?:\|[^\]]*)?\]\]")
KEEP_LABELLED_LINK = re.compile(r"\[\[[^|\]]*\|([^\]]*)\]\]")
KEEP_PLAIN_LINK = re.compile(r"\[\[([^\]]*)\]\]")
DROP_EXTERNAL = re.compile(r"\[(?:https?:|ftp:)[^\s\]]+\s+([^\]]*)\]")
DROP_BARE_EXTERNAL = re.compile(r"\[(?:https?:|ftp:)[^\s\]]*\]")
DROP_HEADING = re.compile(r"^=+\s*(.*?)\s*=+\s*$", re.M)
DROP_HTML = re.compile(r"<[^>]+>")
LIST_MARKER = re.compile(r"^[*#:;]+\s*", re.M)
QUOTES = re.compile(r"'{2,5}")


def clean(text: str) -> str:
    """Reduce Wikipedia markup to running text."""
    for pattern in DROP_BLOCKS:
        text = pattern.sub(" ", text)
    text = DROP_TABLE.sub(" ", text)
    while True:
        stripped = DROP_TEMPLATE.sub(" ", text)
        if stripped == text:
            break
        text = stripped
    text = DROP_NAMED_LINK.sub(" ", text)
    text = KEEP_LABELLED_LINK.sub(r"\1", text)
    text = KEEP_PLAIN_LINK.sub(r"\1", text)
    text = DROP_EXTERNAL.sub(r"\1", text)
    text = DROP_BARE_EXTERNAL.sub(" ", text)
    text = DROP_HEADING.sub(r"\1", text)
    text = DROP_HTML.sub(" ", text)
    text = LIST_MARKER.sub("", text)
    text = QUOTES.sub("", text)
    return html.unescape(text)


def usable_sentences(text: str):
    """Yield running-text sentences worth learning from."""
    for piece in SENTENCE_SPLIT.split(text.replace("\n", " ")):
        tokens = WORD.findall(piece.lower())
        if not 3 <= len(tokens) <= 40:
            continue
        letters = sum(len(token) for token in tokens)
        cyrillic = sum(1 for ch in piece.lower() if ch in ALPHABET)
        # A line that is mostly Latin is a name list, a citation or a formula.
        if letters and cyrillic / max(letters, 1) < 0.6:
            continue
        if not any(ch in ALPHABET for ch in piece):
            continue
        yield " ".join(tokens)


def wiki_sentences(path: pathlib.Path):
    """Stream the dump, one article at a time, and yield its sentences."""
    inside = False
    buffer: list[str] = []
    with bz2.open(path, "rt", encoding="utf-8", errors="replace") as raw:
        for line in raw:
            if not inside:
                if "<text" in line:
                    inside = True
                    line = line.split(">", 1)[-1]
                else:
                    continue
            if "</text>" in line:
                buffer.append(line.split("</text>")[0])
                for sentence in usable_sentences(clean(" ".join(buffer))):
                    yield sentence
                buffer = []
                inside = False
                continue
            buffer.append(line)


def tatoeba_sentences(path: pathlib.Path):
    with bz2.open(path, "rt", encoding="utf-8", errors="replace") as raw:
        for line in raw:
            text = line.rstrip("\n").rsplit("\t", 1)[-1]
            tokens = WORD.findall(text.lower())
            if not 3 <= len(tokens) <= 40:
                continue
            yield " ".join(tokens)


def fetch(url: str, digest: str, cache: pathlib.Path) -> pathlib.Path:
    """Return a cached copy of the download, verified against its digest."""
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and hashlib.sha256(cache.read_bytes()).hexdigest() == digest:
        return cache
    print(f"  fetching {url}", file=sys.stderr, flush=True)
    with urllib.request.urlopen(url) as response, cache.open("wb") as target:
        shutil.copyfileobj(response, target)
    actual = hashlib.sha256(cache.read_bytes()).hexdigest()
    if actual != digest:
        cache.unlink()
        raise SystemExit(f"{url}: digest {actual} does not match the pinned {digest}")
    return cache


def main() -> None:
    cache = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE / ".cache"
    SOURCE.mkdir(exist_ok=True)

    wiki = fetch(WIKI_URL, WIKI_SHA256, cache / "mnwiki-20261101-pages-articles.xml.bz2")
    tatoeba = fetch(TATOEBA_URL, TATOEBA_SHA256, cache / "mon_sentences.tsv.bz2")

    counts: collections.Counter = collections.Counter()
    sentences = 0
    with (SOURCE / "mn_sentences.tsv").open("w", encoding="utf-8", newline="\n") as output:
        for name, reader in (("wikipedia", wiki_sentences), ("tatoeba", tatoeba_sentences)):
            before = sentences
            for sentence in reader(wiki if name == "wikipedia" else tatoeba):
                output.write(sentence + "\n")
                counts.update(sentence.split())
                sentences += 1
            print(f"  {name}: {sentences - before:,} sentences", file=sys.stderr, flush=True)

    if not sentences:
        raise SystemExit("No usable sentences were produced.")

    (SOURCE / "mn.txt").write_text(
        "".join(f"{word}\t{count}\n" for word, count in counts.most_common(50_000)),
        encoding="utf-8",
    )
    (SOURCE / "mn-receipt.json").write_text(json.dumps({
        "language": {"code": "mn", "name": "Mongolian"},
        "sources": [
            {
                "name": WIKI_NAME,
                "url": WIKI_URL,
                "license": WIKI_LICENSE,
                "sha256": WIKI_SHA256,
                "role": "dictionary frequencies and next-word pairs",
            },
            {
                "name": TATOEBA_NAME,
                "url": TATOEBA_URL,
                "license": TATOEBA_LICENSE,
                "sha256": TATOEBA_SHA256,
                "role": "everyday sentences, added to the dictionary and the next-word model",
            },
        ],
        "derived": {
            "sentences": sentences,
            "tokens": sum(counts.values()),
            "wordTypes": len(counts),
            "dictionaryWords": min(50_000, len(counts)),
            "normalization": (
                "Wikipedia markup removed; words are Cyrillic letters with an "
                "internal hyphen or apostrophe; sentences of 3 to 40 words; "
                "sentences that are mostly non-Cyrillic dropped"
            ),
        },
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {sentences:,} sentences and {len(counts):,} word types.")


if __name__ == "__main__":
    main()
