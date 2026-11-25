#!/usr/bin/env python3
"""Fetch the licensed Mongolian corpora and derive the mn pack inputs.

Three sources, all redistributable:

  * Mongolian Wikipedia, CC BY-SA 4.0. The clean backbone. Its vocabulary is
    also what tells Mongolian apart from Russian in the web corpus, because
    both are Cyrillic and the letters alone do not separate them.
  * Tatoeba Mongolian, CC BY 2.0 FR. A few thousand everyday sentences.
  * mC4 Mongolian, ODC-BY. Web text, which is where everyday phrasing lives.
    Wikipedia is encyclopedic, and a keyboard wants the way people write: in
    Wikipedia "сайна" is mostly part of a name and "байна" follows it one
    time in fifty, while on the web "сайна байна" is everywhere.

Writes:
  source/mn.txt             word<TAB>count, most frequent first
  source/mn_sentences.tsv   one sentence per line, for the next-word model
  source/mn-receipt.json    URLs, licences, digests, and what the derivation did
"""
import bz2
import collections
import gzip
import hashlib
import html
import json
import pathlib
import random
import re
import shutil
import sys
import unicodedata
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

MC4_REVISION = "1588ec454efa1a09f29cd18ddd04fe05fc8653a2"
MC4_URL = ("https://huggingface.co/datasets/allenai/c4/resolve/"
           f"{MC4_REVISION}/multilingual/c4-mn.tfrecord-{{:05d}}-of-00128.json.gz")
MC4_SHARDS = 16
MC4_SHA256 = {
    "00000": "0ee5abb6a5c592137a88eec0978669e9bccf96b62c779fbd76046a9ffd1fd596",
    "00001": "48f28dd89f18ee7d8589d2431c8ae6fbcc76f6c0fe0c0362c21531a6b951e5f4",
    "00002": "7ac8dc4e6a64370a575933e9e3c4e570aa1c59ea92b100a0f2b19df74fea709a",
    "00003": "431b1df3a3bf552622ccbdf0a1cb60ddb53b63c0819e15f21f78bcc02d38783a",
    "00004": "6aeae90000977431066a263452c3810864f049d7dde8871cad65822b76681150",
    "00005": "eb2fc06f48722305b02c2d49f5412870004afca78b6efd4f7b3d80c20bfc6a53",
    "00006": "d75d17b043612e397e3a2a78717aca455a333c714b3562c15c2984f0511ad403",
    "00007": "ed8f2c8389f9722374231fa35a04afb1e36c6c04628cc4992bafc6fe802b112a",
    "00008": "f7af03cf8aaf0b4663da01c2f20ab2bab8a75fe13ad40348492dc7df2c576f79",
    "00009": "3f7ad88f6b84dbe28dedb9b50b076042b14efda7d76f4ee04fcda66eb0ac1ef2",
    "00010": "28f03d515c3cd3d11c8a1d783e6862a43889fabdb719cf53692812780f4927e1",
    "00011": "cdcb9ec6944cd2791a620c3b07a091e8e20d7454847ae025484680f0857297ba",
    "00012": "9aab16edbae58224aadbc987685414238f989315349f733ece3de5392445468c",
    "00013": "aa4927a9b402cb787992031767ae3b3301d23d8a52cd36aeb340f43ea401f54d",
    "00014": "05de28171906689c9d467431f9a3f2398bf82bbb1202fc237aa1902a01441de6",
    "00015": "4eee4aa9c2161865c94f1e34092c9e20b9ebcbac05998b39a01acc95ec7d994b",
}
MC4_LICENSE = "ODC-BY-1.0"
MC4_NAME = "mC4 Mongolian (Allen AI), web text"

# The corpus file is shuffled with a fixed seed, so a rebuild from the same
# pinned sources gives the same file and the neural model in the workflow is
# trained on the same text as the one the macOS job exports.
SHUFFLE_SEED = 20261125

# The dump server asks for a User-Agent that says who is fetching.
USER_AGENT = "Clink language pack builder (https://github.com/cmspam/clink-language-packs)"

ALPHABET = set("абвгдеёжзийклмнопөпрстуүфхцчшщъьыэюя")
# Letters only Kazakh writes. A page with them is not Mongolian.
KAZAKH_ONLY = set("әғқңұһі")
# Buryat is written in the same letters and shares enough words with Mongolian
# to pass a vocabulary check, so a Buryat page looks Mongolian to every test
# above. These words are Buryat and not Mongolian, so a page carrying them is
# dropped whole.
BURYAT = re.compile(r"\b(?:наймаа|заяа|ажан|буряад|буряалууд|хүнзүй)\b")
WORD = re.compile(r"[а-яёөү]+")
TOKEN = re.compile(r"[^\s.,!?;:\"“”«»()\[\]{}]+")
# A dictionary entry is a Mongolian word: its letters, with an internal hyphen
# or apostrophe. Numbers and Latin fragments from web pages are not words, and
# letting them in would push letters out of the dictionary's alphabet table.
MONGOOLIAN_WORD = re.compile(r"[а-яёөү]+(?:[-'’][а-яёөү]+)*")

# Wikipedia markup that carries no running text.
DROP_BLOCKS = [
    re.compile(r"<!--.*?-->", re.S),
    re.compile(r"<ref[^>/]*>.*?</ref>", re.S | re.I),
    re.compile(r"<ref[^>]*/>", re.I),
    re.compile(r"<((?:math|gallery|timeline|pre|code|syntaxhighlight|poem|score|source))\b[^>]*>.*?</\1>", re.S | re.I),
    re.compile(r"<(?:math|gallery|timeline|pre|code|syntaxhighlight|poem|score|source)[^>]*/>", re.I),
]
DROP_TABLE = re.compile(r"\{[|].*?\|\}", re.S)
DROP_TEMPLATE = re.compile(r"\{\{.*?\}\}", re.S)
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


def sentences_from(text: str):
    """Yield running-text sentences worth learning from."""
    for piece in re.split(r"[.!?;\n…]+", text):
        tokens = TOKEN.findall(piece.lower())
        if not 3 <= len(tokens) <= 40:
            continue
        letters = sum(len(token) for token in tokens)
        cyrillic = sum(1 for char in piece.lower() if char in ALPHABET)
        # A line that is mostly not Mongolian is a name list or a citation.
        if letters and cyrillic / letters < 0.75:
            continue
        if not any(char in ALPHABET for char in piece):
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
                yield from sentences_from(clean(" ".join(buffer)))
                buffer = []
                inside = False
                continue
            buffer.append(line)


def tatoeba_sentences(path: pathlib.Path):
    with bz2.open(path, "rt", encoding="utf-8", errors="replace") as raw:
        for line in raw:
            text = line.rstrip("\n").rsplit("\t", 1)[-1]
            tokens = TOKEN.findall(text.lower())
            if not 3 <= len(tokens) <= 40:
                continue
            yield " ".join(tokens)


def fetch(url: str, digest: str, cache: pathlib.Path) -> pathlib.Path:
    """Return a cached copy of the download, verified against its digest."""
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and hashlib.sha256(cache.read_bytes()).hexdigest() == digest:
        return cache
    print(f"  fetching {url}", file=sys.stderr, flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response, cache.open("wb") as target:
        shutil.copyfileobj(response, target)
    actual = hashlib.sha256(cache.read_bytes()).hexdigest()
    if actual != digest:
        cache.unlink()
        raise SystemExit(f"{url}: digest {actual} does not match the pinned {digest}")
    return cache


def mc4_sentences(path: pathlib.Path, vocabulary: set[str]):
    """Yield the sentences of one web corpus shard that are really Mongolian.

    The shard holds a mix of languages, and Russian is written in the same
    Cyrillic letters, so the letters alone cannot sort it out. What does sort
    it out is the words: a Mongolian page repeats the common Mongolian words,
    a Russian page does not have them at all.
    """
    kept = dropped = 0
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as raw:
        for line in raw:
            try:
                document = json.loads(line)
            except ValueError:
                continue
            text = document.get("text", "")
            if not text.strip():
                continue
            lower = text.lower()
            if any(char in KAZAKH_ONLY for char in lower):
                dropped += 1
                continue
            if BURYAT.search(lower):
                dropped += 1
                continue
            tokens = TOKEN.findall(lower)
            if len(tokens) < 40:
                continue
            letters = [char for char in lower if char.isalpha()]
            if not letters:
                continue
            cyrillic = sum(1 for char in letters if char in ALPHABET)
            if cyrillic / len(letters) < 0.75:
                dropped += 1
                continue
            known = sum(1 for token in tokens if token in vocabulary)
            if known / len(tokens) < 0.25:
                dropped += 1
                continue
            before = kept
            for sentence in sentences_from(text):
                kept += 1
                yield sentence
            if kept == before:
                dropped += 1
    print(f"    {path.name}: {kept:,} sentences, {dropped:,} documents dropped", file=sys.stderr, flush=True)


def main() -> None:
    cache = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE / ".cache"
    # How many word forms the dictionary carries. More forms cover more
    # conjugations; the file grows with them.
    dictionary_size = int(sys.argv[2]) if len(sys.argv) > 2 else 50_000
    SOURCE.mkdir(exist_ok=True)

    wiki = fetch(WIKI_URL, WIKI_SHA256, cache / "mnwiki-20261101-pages-articles.xml.bz2")
    tatoeba = fetch(TATOEBA_URL, TATOEBA_SHA256, cache / "mon_sentences.tsv.bz2")

    # The encyclopedia is counted first. Its word list is the clean one, and it
    # is what tells Mongolian apart from Russian in the web corpus, because both
    # are written in the same letters and the letters alone separate nothing.
    wiki_lines = list(wiki_sentences(wiki))
    tatoeba_lines = list(tatoeba_sentences(tatoeba))
    encyclopedia = collections.Counter()
    encyclopedia.update(" ".join(wiki_lines).split())
    vocabulary = {word for word, count in encyclopedia.most_common(50_000)}
    rng = random.Random(SHUFFLE_SEED)

    counts = collections.Counter()
    sentences = 0
    with (SOURCE / "mn_sentences.tsv").open("w", encoding="utf-8", newline="\n") as output:
        # The web text comes first in the file. The neural model trains on the
        # first lines of the corpus, and the web is where everyday phrasing
        # lives; the encyclopedia would teach it to write like a reference work.
        # Within each source the lines are shuffled, so a sample of any size is
        # a fair sample of the whole and not one site in a row.
        for number in sorted(MC4_SHA256):
            shard = fetch(MC4_URL.format(int(number)), MC4_SHA256[number],
                          cache / f"c4-mn-{number}.json.gz")
            lines = list(mc4_sentences(shard, vocabulary))
            rng.shuffle(lines)
            output.writelines(sentence + "\n" for sentence in lines)
            counts.update(" ".join(lines).split())
            sentences += len(lines)
        print(f"  mC4: {sentences:,} sentences", file=sys.stderr, flush=True)

        for lines, name in ((wiki_lines, "wikipedia"), (tatoeba_lines, "tatoeba")):
            rng.shuffle(lines)
            output.writelines(sentence + "\n" for sentence in lines)
            counts.update(" ".join(lines).split())
            before = sentences
            sentences += len(lines)
            print(f"  {name}: {sentences - before:,} sentences", file=sys.stderr, flush=True)

    if not sentences:
        raise SystemExit("No usable sentences were produced.")

    words = [(word, count) for word, count in counts.most_common()
             if MONGOOLIAN_WORD.fullmatch(word)]
    (SOURCE / "mn.txt").write_text(
        "".join(f"{word}\t{count}\n" for word, count in words[:dictionary_size]),
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
                "role": "dictionary frequencies, next-word pairs, and the vocabulary that identifies Mongolian in the web corpus",
            },
            {
                "name": TATOEBA_NAME,
                "url": TATOEBA_URL,
                "license": TATOEBA_LICENSE,
                "sha256": TATOEBA_SHA256,
                "role": "everyday sentences",
            },
            {
                "name": MC4_NAME,
                "url": MC4_URL.format(0),
                "revision": MC4_REVISION,
                "license": MC4_LICENSE,
                "shards": MC4_SHA256,
                "role": "web text, where everyday phrasing lives",
            },
        ],
        "derived": {
            "sentences": sentences,
            "tokens": sum(counts.values()),
            "wordTypes": len(counts),
            "mongolianWordTypes": len(words),
            "dictionaryWords": min(dictionary_size, len(words)),
            "normalization": (
                "Wikipedia markup removed; words are Cyrillic letters with an "
                "internal hyphen or apostrophe; sentences of 3 to 40 words; "
                "sentences that are mostly not Mongolian dropped. The web "
                "corpus is kept only where most of its words are Mongolian, "
                "which is what separates it from Russian in the same script, "
                "and where the page carries no Kazakh or Buryat letters or "
                "words. The web text is written first and each source is "
                "shuffled, so the neural model trains on a fair sample of "
                "everyday writing rather than on one site in a row"
            ),
        },
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {sentences:,} sentences and {len(counts):,} word types.")


if __name__ == "__main__":
    main()
