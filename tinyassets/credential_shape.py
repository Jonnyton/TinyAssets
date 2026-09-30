"""Does this free text carry a credential SHAPE?

Free text the rail stores in the clear -- a withdraw reason, a Reply-or-note, a
connection label, an intent line -- gets screened so a key pasted into the wrong
box is refused rather than written to disk unencrypted.

The screen this replaces was one flat pattern, ``[A-Za-z0-9_\\-]{16,}``. Because
``-`` is inside its character class, an ordinary hyphenated English compound is
an "unbroken 16+ character run": ``self-authenticating`` is 19 characters, so
live on 2026-09-30 a universe was refused twice for explaining, in plain words,
that *there is no token to paste* --

    "That link is a self-authenticating webhook URL with the secret embedded in
    the path, so there is no separate token to paste."

A refusal a truthful sentence cannot get past is worse than no screen: the agent
cannot say why it is withdrawing an ask, and the user never learns.

**Parse, don't pattern-match** (the lesson of PR #4017, three review rounds on
three input classes). Where a credential *ends* depends on how it *started*, so
this splits the text into tokens and decides per token, with the decision made by
structure rather than by any word in the sentence:

1. a published credential prefix (``sk-``, ``ghp_``, ``xoxb-``, ``AKIA``…) --
   providers publish these precisely so a token is recognisable;
2. a JWT, a PEM private key block, or an HTTP auth header value;
3. a URL, which is **parsed**: userinfo, or a path/query/fragment segment that is
   itself opaque, or a query parameter whose *name* says it is a secret;
4. otherwise an opaque high-entropy run: long enough, not word-shaped, and with
   a per-character entropy no sentence reaches.

**Nothing the old pattern caught may be let through.** It fired on any 16+
character run of ``[A-Za-z0-9_-]``, so every length bar here is 16 rather than a
rounder number: a cross-family review round on 2026-09-30 found a TOTP base32
seed (``JBSWY3DPEHPK3PXP`` -- Google's own published example), a 64-bit key in 16
hex characters, and a 20-digit numeric secret all sitting under a 20-character
bar. The same round found ``,`` and ``;`` being treated as token boundaries,
which split one long secret into two short ones and cut a URL off before its own
query string, and a bare ``?<token>`` arriving as a parameter NAME with an empty
value while only values were judged.

Measured on 2026-09-30 against 36,705 real prose lines from this repo's docs and
3,000-sample random sweeps per credential alphabet:

============================  =========================================
prose lines refused           4.6% (the old pattern refused every
                              hyphenated compound word)
base64url / base64 / hex /    0 escaped at 16, 24, 32 and 40 chars
base32 / base58 / alnum /
digits / mixed-case letters
letters of ONE case only      1.6% at 16 chars, 1.1% at 20, 0.2% at 32
============================  =========================================

What it deliberately does NOT decide, both being shapes no structural test can
separate from writing without semantics:

* a hyphenated passphrase of real words (``correct-horse-battery-staple``);
* a secret drawn only from letters of a single case -- the one alphabet above
  with a measurable escape rate, and one no provider issues keys in: a random
  40-character AWS-shaped base64 secret is letters-only about twice in ten
  thousand. (The base32 residual is this same class; a 16-character base32 draw
  is letters-only 3% of the time.)

The old pattern "caught" both only as a side effect of catching every compound
word, which is the bug. Conversely an opaque identifier that is not secret -- a
git sha, a UUID, a ULID, a 16-digit number -- is still refused, because by shape
it is key material; the refusal says to put it in words, which is answerable.

Screening the shapes above is what was asked for (founder, 2026-09-30: "keep
refusing real secrets: sk-…, long high-entropy tokens, URLs with secret
path/query segments").
"""

from __future__ import annotations

import math
import re
from urllib.parse import parse_qsl, urlsplit

__all__ = ["credential_shape", "looks_like_credential"]

#: Vowels, ``y`` included: it carries a syllable in ``rhythm`` and ``myth``, and
#: excluding it makes ordinary words look like consonant soup. Used only to bound
#: consonant RUNS -- "must contain a vowel" was tried and refused ``html``,
#: ``https`` and ``environment-variables.md``, which is the same over-reach in a
#: smaller pattern.
_VOWELS = frozenset("aeiouyAEIOUY")

#: Below this an opaque run is too short to be a usable secret on its own, and
#: short high-entropy strings are everywhere in prose (acronyms, ids, versions).
#: SIXTEEN, deliberately the same length the flat pattern this replaces used: a
#: longer bar is a regression, and a 16-character run is exactly where real
#: secrets live at the short end -- a TOTP base32 seed (``JBSWY3DPEHPK3PXP``,
#: Google's own published example) and a 64-bit key in hex are both 16.
_MIN_OPAQUE_CHARS = 16

#: Inside a URL the bar is lower: a path segment or query value is a *slot*, so
#: an opaque run there is positional evidence a bare word in a sentence is not.
_MIN_URL_SEGMENT_CHARS = 12

#: Shannon entropy per character, the last gate a run that is already too long
#: and not word-shaped has to clear. Low, and measured that way: at 2.7 it
#: spared 22 distinct prose tokens in 37,334 lines -- 0.09 of a percentage point
#: -- while letting 21% of random 16-digit and 8% of random 20-digit secrets
#: through, because a short draw from a ten-symbol alphabet repeats itself. At
#: 2.0 the prose figure is unchanged and those drop to 0.1% and 0%. What it is
#: actually for is a DEGENERATE run -- ``XXXXXXXXXXXXXXXX``, a repeated block --
#: which is a documentation placeholder, not key material.
_MIN_ENTROPY_BITS = 2.0

#: The longest alphabetic part still plausibly one word. Generous on purpose:
#: ``antidisestablishmentarianism`` is 28 characters and ``pseudopseudohypo-
#: parathyroidism`` 30, and a 24-character cap refused both. Length is the weak
#: signal here; bigram plausibility is the strong one.
_MAX_WORD_CHARS = 60

#: English tops out at five: ``stre-ngths-``, ``a-ngsts-``.
_MAX_CONSONANT_RUN = 5

#: The longest run of digits that is still a written number rather than a
#: secret: a millisecond epoch is 13, a full date 8, an international phone
#: number 15. Past that, digits alone carry the entropy of key material -- 20
#: decimal digits is 66 bits.
_MAX_DIGIT_RUN = 15

#: Published credential prefixes. Matching one IS the finding -- the provider
#: publishes the prefix so a leaked token is recognisable -- but a body must
#: follow it, so the bare word ``sk-`` in a sentence is not a credential.
_PREFIXES: tuple[str, ...] = (
    "sk-", "sk_", "pk_live_", "pk_test_", "sk_live_", "sk_test_", "rk_live_",
    "rk_test_", "whsec_", "ghp_", "gho_", "ghu_", "ghs_", "ghr_",
    "github_pat_", "glpat-", "gldt-", "glsoat-", "xoxb-", "xoxp-", "xoxa-",
    "xoxs-", "xoxr-", "xoxe-", "xapp-", "hf_", "npm_", "dop_v1_", "doo_v1_",
    "dor_v1_", "shpat_", "shpss_", "shpca_", "shppa_", "sq0atp-", "sq0csp-",
    "lin_api_", "figd_", "figu_", "rpa_", "sgp_", "sl.", "ya29.", "gsk_",
    "nvapi-", "r8_", "tvly-", "pplx-", "csk-", "AIza", "AKIA", "ASIA", "ABIA",
    "ACCA", "SG.",
)

#: Prefixes whose match must respect case. AWS key ids and Google API keys are
#: uppercase/CamelCase by specification; lowercasing them would let the English
#: words ``akia``/``sg.`` (nonexistent, but the principle holds for a
#: case-insensitive match on short prefixes) widen the net for nothing.
_CASE_SENSITIVE_PREFIXES = frozenset({"AIza", "AKIA", "ASIA", "ABIA", "ACCA",
                                      "SG."})

#: The body a prefix must carry before the token counts as a credential.
_MIN_PREFIX_BODY_CHARS = 8

#: A JWT: three base64url segments, the first a base64url-encoded ``{"``.
_JWT_RE = re.compile(r"^eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{4,}$")

#: A PEM private key block, matched on the armour rather than the body.
_PEM_RE = re.compile(r"-----BEGIN[ A-Z]*PRIVATE KEY-----")

#: An HTTP authorization header value pasted whole.
_AUTH_HEADER_RE = re.compile(r"\b(?:Bearer|Basic|Token)\s+[A-Za-z0-9+/=_.\-]{12,}")

#: Hex key material. Sixteen, not thirty-two: a 64-bit device key ships as 16
#: hex characters, and requiring an md5's worth let one through.
_HEX_RE = re.compile(r"^[0-9a-fA-F]{16,}$")

#: Classic base64 with its own alphabet: ``+``, ``/`` and padding do not occur
#: inside a word, so the run itself is the finding once it is long enough.
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]{24,}={0,2}$")

#: Query parameter NAMES that declare their value is a secret. The name is
#: structure -- the author of the URL wrote it -- not a word in a sentence.
_SECRET_PARAM_NAMES = frozenset({
    "access_token", "api_key", "apikey", "auth", "auth_token", "client_secret",
    "credential", "id_token", "key", "password", "passwd", "pwd",
    "refresh_token", "secret", "sig", "signature", "sig_token", "token",
    "x-amz-signature", "x-api-key",
})

#: The shortest query value that can be a secret worth refusing.
_MIN_SECRET_PARAM_CHARS = 8

#: A bare ``host/path`` with no scheme is still a URL to a reader, and the founder's
#: own report quoted one that way (``tinyassets.io/mcp/hooks/…``).
_SCHEMELESS_URL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}/")

#: A dotted-quad host. A credential ask pointing at a raw address is never help.
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

#: Common English letter bigrams. A long alphabetic run whose adjacent pairs are
#: mostly in here is a word; a random one is not. This is the discriminator that
#: the old single pattern had no way to express.
_COMMON_BIGRAMS = frozenset("""
th he in er an re on at en nd ti es or te of ed is it al ar st to nt ng se ha
as ou io le ve co me de hi ri ro ic ne ea ra ce li ch ll be ma si om ur ca el
ta la ns di fo ho pe ec pr no ct us ac ot il tr ly nc et ut ss so rs un lo wa
ge ie wh ee wi em ad ol rt po we na ul ni ts mo ow pa im mi ai sh ir su id os
iv ia am fi ci vi pl ig tu ev ld ry mp fe bl ab gh ap ck au sc ag ei ei ep ff
ft gi gr ke ld lt ly nk nu od oo op pi qu rd rg rm rn rv sp sw tt ty ue ui um
up ve ye yo ys ze ci ph th ok ib ip ob og ua ub uc ug ur wo tw sm sn sl fl fr
dr br cr gl gn kn ps rh wr xi ax ex ox ix ux ny my by cy dy gy py sy ty vy
""".split())

#: Separators a written compound uses to join words. A credential uses some of
#: the same characters, which is exactly why splitting on them and judging the
#: PARTS is the work: ``self-authenticating`` splits into two words,
#: ``sk_live_51ABCDEFSECRET`` does not. ``:`` and ``@`` are in here so an agent
#: can name a file line (``path/to/file.py:LINE``) or an address
#: (``someone@example.com``) in a note without being refused; a credential
#: carrying either has already been caught as a URL or an auth header, both
#: parsed before this. Adding those two alone took the refusal rate on 37,334
#: real prose lines from 4.8% to 2.8%.
_SEPARATOR_RE = re.compile(r"[-_./\\|'’:@+,;]+")

#: A short word carrying an index: ``v1``, ``sp800``, ``mvcc2``. Bounded tight,
#: so ``51ABCDEFSECRET`` cannot claim to be one.
_SHORT_SUFFIXED_RE = re.compile(r"^[A-Za-z]{1,4}\d{1,4}$")

#: One CamelCase segment. A word's worth of letters, not a fragment.
_CAMEL_SPLIT_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])")
_MIN_CAMEL_SEGMENT_CHARS = 3

#: Bigram plausibility is only meaningful once a run has several pairs; below
#: this length the ratio is noise.
_MIN_BIGRAM_CHARS = 12

#: The share of adjacent pairs that must be common English bigrams. Measured
#: over every 20+ character run in this repo's prose, real writing does not go
#: below 0.586 (``pseudopseudohypoparathyroidism``), while uniformly random
#: letters average 0.29. 0.45 was tried and let 40 characters of uppercase
#: gibberish through at 0.50 (cross-family review, 2026-09-30); it also left a
#: 5% escape rate on random lowercase, which 0.55 cuts to 1%.
_MIN_BIGRAM_RATIO = 0.55

#: Punctuation that wraps a token in prose but never starts or ends a credential.
_SHELL = "\"'`()[]{}<>,;:!?*‘’“”… \t\r\n"
_TRAILING_SHELL = _SHELL + "."

#: Token boundaries. Whitespace is not enough: a markdown link glues two URLs
#: into one "token" (``[name](https://host/name)``), and the glue -- ``](`` --
#: then reads as an opaque path segment.
#:
#: ``,`` and ``;`` are deliberately NOT boundaries, though they look like them.
#: Splitting on them cut a long run into short ones that each ducked under the
#: length bar (``7Hq2Lp9XvB4nZm8K;dRtW3Ysa``), and cut a URL off before its own
#: query string (``?token=1234;<secret>``) -- both found by cross-family review,
#: 2026-09-30. They are word SEPARATORS instead, so prose still reads as prose.
_TOKEN_SPLIT_RE = re.compile(r"[\s()\[\]{}<>\"'`‘’“”…]+")


def looks_like_credential(text: str) -> bool:
    """Whether ``text`` carries something shaped like a credential."""
    return credential_shape(text) is not None


def credential_shape(text: str) -> str | None:
    """The name of the first credential shape found in ``text``, else ``None``.

    The name is a short machine label (``"published_prefix"``,
    ``"url_query_secret"``, ``"opaque_high_entropy"``…) for logs and tests. It is
    never shown to a user: each call site owns its own wording, because what to
    say depends on which box the text came from.
    """
    if not text:
        return None
    body = str(text)
    if _PEM_RE.search(body):
        return "private_key_block"
    if _AUTH_HEADER_RE.search(body):
        return "auth_header"
    for raw in _TOKEN_SPLIT_RE.split(body):
        found = _token_shape(raw)
        if found is not None:
            return found
    return None


def _token_shape(raw: str) -> str | None:
    """Classify one token."""
    token = raw.lstrip(_SHELL).rstrip(_TRAILING_SHELL)
    if not token:
        return None
    lowered = token.lower()
    if "://" in lowered or _SCHEMELESS_URL_RE.match(token):
        found = _url_shape(token)
        if found is not None:
            return found
        # A URL that parsed clean is not then re-judged as one long opaque run:
        # its structure has already been inspected, part by part.
        return None
    if _JWT_RE.match(token):
        return "jwt"
    return _opaque_shape(token, minimum=_MIN_OPAQUE_CHARS)


def _url_shape(token: str) -> str | None:
    """Parse a URL and judge each slot a secret can occupy."""
    candidate = token if "://" in token else "https://" + token
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None
    if parts.username or parts.password:
        return "url_userinfo"
    for segment in parts.path.split("/"):
        if _slot_shape(segment) is not None:
            return "url_path_secret"
    for name, value in parse_qsl(parts.query, keep_blank_values=True):
        stripped = value.strip()
        if (name.strip().lower() in _SECRET_PARAM_NAMES
                and len(stripped) >= _MIN_SECRET_PARAM_CHARS):
            return "url_secret_parameter"
        if _slot_shape(stripped) is not None:
            return "url_query_secret"
        # The NAME is a slot as well. A bare ``?<token>`` has no ``=``, so the
        # whole secret arrives as a parameter name with an empty value and
        # judging values alone never saw it (cross-family review, 2026-09-30).
        if _slot_shape(name.strip()) is not None:
            return "url_query_secret"
    if _slot_shape(parts.fragment.strip()) is not None:
        return "url_fragment_secret"
    return None


def _slot_shape(value: str) -> str | None:
    """Judge one URL slot: a path segment, a query value, a fragment.

    Lower length bar than a bare word in a sentence, because the POSITION is
    evidence -- whoever composed the URL put a value in that slot.
    """
    return _opaque_shape(value, minimum=_MIN_URL_SEGMENT_CHARS)


def _opaque_shape(token: str, *, minimum: int) -> str | None:
    """Judge one run: published prefix, then encoding, then shape, then entropy."""
    core = token.strip("._-")
    if not core:
        return None
    prefixed = _published_prefix(core)
    if prefixed is not None:
        return prefixed
    # LENGTH ON THE RUN AS PASTED, shape on the trimmed core. Measuring the
    # trimmed core against the bar let a full-length token duck under it purely
    # because its last character was one of the trim set: a 20-character
    # ``…Igw-V3_`` became a 19-character core and went unjudged.
    if len(token) < minimum:
        return None
    # `not core.isdigit()` because every digit is also a hex digit: without it a
    # written number is "hex key material", which is both wrong and the wrong
    # label to hand a reader. A pure-digit run is judged as a NUMBER below.
    if _HEX_RE.match(core) and not core.isdigit():
        return "hex_key_material"
    # A base64 run is only evidence with a non-letter in it. Requiring one is
    # what keeps ``antidisestablishmentarianism`` -- 28 characters that match the
    # base64 alphabet exactly -- from being read as encoded key material. ``/``
    # is NOT evidence: it joins words in prose ("and/or",
    # "internationalization/localization") as often as it pads base64.
    if _BASE64_RE.match(core) and any(c.isdigit() or c in "+=" for c in core):
        return "base64_key_material"
    if _word_shaped(core):
        return None
    if _entropy_bits_per_char(core) < _MIN_ENTROPY_BITS:
        return None
    return "opaque_high_entropy"


def _published_prefix(core: str) -> str | None:
    """A published credential prefix carrying a body long enough to be a key."""
    lowered = core.lower()
    for prefix in _PREFIXES:
        subject = core if prefix in _CASE_SENSITIVE_PREFIXES else lowered
        needle = prefix if prefix in _CASE_SENSITIVE_PREFIXES else prefix.lower()
        if subject.startswith(needle) and len(core) - len(prefix) >= _MIN_PREFIX_BODY_CHARS:
            return "published_prefix"
    return None


def _word_shaped(core: str) -> bool:
    """Whether this run reads as one or more ordinary words.

    ``self-authenticating`` is two words joined by a hyphen; a credential is not.
    Two stages, because each catches what the other cannot:

    *Per part* -- alphabetic, ASCII, one of the three casings a written word
    takes, no consonant run longer than English allows. A single mixed-case or
    digit-bearing part disqualifies the whole run, which is what stops
    ``sk_live_51ABCDEFSECRET`` from reading as ``sk live 51ABCDEFSECRET``.

    *Across the run* -- the letters of every part, concatenated, have to be
    pronounceable by bigram frequency. Measuring per part instead put ordinary
    eight-letter words (``download``, ``judgment``, ``shutdown``) below the bar,
    because seven pairs is too few to measure: one unusual pair costs 0.14. The
    concatenation of a 20-character run gives nineteen.
    """
    parts = _SEPARATOR_RE.split(core)
    if not all(parts):
        return False
    if not all(_part_is_word(part) for part in parts):
        return False
    letters = "".join(c for c in core if c.isascii() and c.isalpha())
    if not letters:
        # No letters at all: a number, a date, a timestamp range. Already judged
        # part by part against _MAX_DIGIT_RUN, and there is no word claim to make.
        return True
    if len(letters) < _MIN_BIGRAM_CHARS:
        # Letters, but too few to measure -- so there is NO evidence this reads
        # as words, only that its parts were individually permissible. A run
        # that long, mixing a couple of letters into digits, is key material:
        # ``Qx2345_98762345_98374612`` is 24 characters of base64url whose only
        # letters are ``Qx``, and it passed on the strength of a skipped test
        # (cross-family review, 2026-09-30).
        return False
    return _bigram_ratio(letters) >= _MIN_BIGRAM_RATIO


def _part_is_word(part: str) -> bool:
    """One separator-delimited part of a run, judged on its own.

    Three structures count, all of them things writing has and key material does
    not. Without the second and third, an agent could not name a file it was
    talking about: ``ReportEngine/agent.py`` and
    ``docs/2026-04-25-session-additions.md`` were both refused as opaque runs.
    """
    if not part.isascii():
        # Non-ASCII letters are ordinary prose, never key material: a credential
        # is transport-safe by construction.
        return part.isalpha()
    if part.isdigit():
        # A date, a version, a count, a phone number. Bounded, because past that
        # length a digit run IS key material: 20 decimal digits is 66 bits.
        return len(part) <= _MAX_DIGIT_RUN
    if part.isalpha():
        return _alpha_part_is_word(part)
    if _SHORT_SUFFIXED_RE.match(part):
        # ``v1``, ``sp800``, ``mvcc2`` -- a short word with an index on it.
        return True
    return False


def _alpha_part_is_word(part: str) -> bool:
    if len(part) > _MAX_WORD_CHARS:
        return False
    if _longest_consonant_run(part) > _MAX_CONSONANT_RUN:
        return False
    if _natural_case(part):
        return True
    # CamelCase is how code writes a compound: judge the segments, each of which
    # must be a real word's length. ``ReportEngine`` -> ``Report`` + ``Engine``;
    # ``AbCdEfGh`` and ``wJalrXUtnFEMI`` fall apart into fragments too short to
    # be words, which is exactly the difference from key material.
    segments = _CAMEL_SPLIT_RE.findall(part)
    if len(segments) < 2 or "".join(segments) != part:
        return False
    return all(len(seg) >= _MIN_CAMEL_SEGMENT_CHARS and _natural_case(seg)
               and _longest_consonant_run(seg) <= _MAX_CONSONANT_RUN
               for seg in segments)


def _natural_case(part: str) -> bool:
    """``word``, ``WORD`` or ``Word`` -- the three shapes a written word takes."""
    if len(part) == 1:
        return True
    return part.islower() or part.isupper() or (part[0].isupper() and part[1:].islower())


def _longest_consonant_run(part: str) -> int:
    longest = run = 0
    for char in part:
        run = 0 if char in _VOWELS else run + 1
        longest = max(longest, run)
    return longest


def _bigram_ratio(part: str) -> float:
    lowered = part.lower()
    pairs = [lowered[i:i + 2] for i in range(len(lowered) - 1)]
    if not pairs:
        return 1.0
    return sum(1 for pair in pairs if pair in _COMMON_BIGRAMS) / len(pairs)


def _entropy_bits_per_char(core: str) -> float:
    counts: dict[str, int] = {}
    for char in core:
        counts[char] = counts.get(char, 0) + 1
    total = len(core)
    return -sum((n / total) * math.log2(n / total) for n in counts.values())
