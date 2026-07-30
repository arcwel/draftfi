"""Turn a raw bank descriptor into a stable merchant key.

This is the foundation the rest of categorization stands on. Raw descriptors
carry per-transaction entropy — order ids, terminal numbers, dates, store
numbers — so using them as a cache key gives cardinality roughly equal to
transaction count. Measured on a real 10,371-transaction corpus: 4,787 distinct
raw strings collapse to ~2,100 canonical keys, and with alias folding the four
Amazon spellings covering 1,191 transactions become one decision instead of four.

Two things come out of here:

* ``key``     — the canonical, uppercase merchant identity. Used for cache
                lookups, rule matching, and "one merchant, one category".
* ``display`` — a human-readable merchant name for the ledger.

Field layout is not arbitrary; card descriptors are fixed-width fields
concatenated by the issuer (Visa Merchant Data Standards: 25-char merchant name,
13-char city, 2-char state), and ACH descriptors follow NACHA company-name /
entry-description / individual-name ordering. Knowing that is what makes the
stripping rules principled rather than guesswork.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Payment facilitators. Visa requires "Facilitator*SponsoredMerchant", so for
# these the interesting name is on the RIGHT of the asterisk. For everyone else
# (e.g. "AMAZON KIDS*B26ME6RT2") the merchant is on the LEFT and the right side
# is a reference id. Getting this direction wrong is the classic bug — a blanket
# split("*")[1] turns Amazon into a random token.
AGGREGATOR_PREFIXES = frozenset(
    {
        "SQ", "SQUARE", "TST", "TOAST", "WPY", "WORLDPAY", "PP", "PAYPAL",
        "SP", "SHOPIFY", "IDP", "GOOGLE", "APL", "APLPAY", "APPLE PAY",
        "LEVELUP", "COMENITY PAY", "FSPRG.COM", "2CO.COM", "PADDLE.NET",
        "XSOLLA", "CRV", "EB", "EVENTBRITE", "STRIPE", "SUMUP", "IZETTLE",
        "CLOVER", "VENMO",
    }
)

# Transaction-type chatter the bank prepends. Never part of the merchant.
_NOISE_PREFIX = re.compile(
    r"^(POS DEBIT|POS PURCHASE|POS WD|POS|CHECKCARD|CHKCARD|CHECK CARD|"
    r"DEBIT PURCHASE VISA|DEBIT CARD PURCHASE|DEBIT PURCHASE|DEBIT|CREDIT|"
    r"VISA|MASTERCARD|MC|PURCHASE AUTHORIZED ON|PURCHASE|SALE|PAYMENT TO|"
    r"RECURRING PMT|RECURRING PAYMENT|RECURRING|PREAUTH|PRE-AUTH|PENDING|"
    r"ACH DEBIT|ACH CREDIT|ACH|WEB PYMT|WEB PAYMENT|ONLINE PAYMENT|ONLINE|"
    r"PPD|TEL|IAT|EFT|WITHDRAWAL|DEPOSIT)\b[\s:*-]*",
    re.IGNORECASE,
)

# Bank of America tags its ACH subfields explicitly; Wells Fargo does not.
# Cutting at the first tag keeps the company name and drops the rest.
_ACH_TAGS = re.compile(
    r"\s(DES|INDN|CO ID|ID|ORIG CO NAME|ORIG ID)\s*:.*$", re.IGNORECASE
)

_STRIPPERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b"),        # dates
    re.compile(r"\b\d{2}:\d{2}(:\d{2})?\b"),                     # times
    re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),                # phone numbers
    re.compile(r"X{3,}\d*", re.IGNORECASE),                      # masked card
    re.compile(r"\*{2,}\d{0,4}"),
    # From the dot onward, NOT from the start of the word: "AMAZON.COM ..."
    # must leave "AMAZON" behind, not nothing.
    re.compile(r"\.(COM|NET|ORG|CO|IO|GOV|US)\b.*$", re.IGNORECASE),
    re.compile(
        r"\s(PAYMENT ID|PMT ID|REF|TRACE|CONF|AUTH)\s*#?:?\s*\S+", re.IGNORECASE
    ),
    re.compile(r"\s(STORE|STR|ST|TERM|TERMINAL)\s*#?\s*\d+\b", re.IGNORECASE),
    re.compile(r"\s#\s*\d+\b"),                                  # "#1234"
    re.compile(r"\s\d{2,}$"),                                    # trailing store no
    re.compile(r"\b\d+\.\d{2}\b"),                               # amounts
    re.compile(r"\b(USD|EUR|GBP|CAD|AUD)\b"),
)

_US_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS "
    "MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV "
    "WI WY DC PR".split()
)

# Short/odd tokens that ARE merchants. Without this the junk-token filter eats
# them: "76" is numeric, "CVS" and "TJX" are vowel-free.
_KEEP_TOKENS = frozenset(
    {
        "3M", "H2O", "76", "AT&T", "H&M", "CVS", "BP", "KFC", "IHOP", "REI",
        "IKEA", "TJX", "GNC", "AMC", "HP", "GM", "UPS", "DSW", "TJ", "BJS",
        "QVC", "HEB", "ALDI", "LYFT", "AAA", "DMV", "IRS", "USPS", "FEDEX",
        "PG&E", "SDG&E", "T-MOBILE", "XFINITY", "MTA", "BART", "SFO", "LAX",
    }
)

# Common US city tokens, used only to strip a "CITY ST" tail. Deliberately a
# fixed list rather than a heuristic: guessing here silently truncates merchant
# names, and a missed city merely leaves a slightly longer (still stable) key.
_CITY_NAMES = frozenset(
    {
        "SAN DIEGO", "SAN FRANCISCO", "SAN JOSE", "SAN ANTONIO", "SANTA ANA",
        "SANTA CLARA", "SANTA MONICA", "SANTA BARBARA", "LOS ANGELES",
        "LA JOLLA", "LAS VEGAS", "NEW YORK", "NEW ORLEANS", "SALT LAKE CITY",
        "KANSAS CITY", "OKLAHOMA CITY", "COLORADO SPRINGS", "FORT WORTH",
        "EL PASO", "LONG BEACH", "VIRGINIA BEACH", "CHULA VISTA", "SAN MATEO",
        "PALO ALTO", "MOUNTAIN VIEW", "SUNNYVALE", "CULVER CITY", "WEST HOLLYWOOD",
        "NEWPORT BEACH", "HUNTINGTON BEACH", "COSTA MESA", "COMMERCE CITY",
        "CHICAGO", "HOUSTON", "PHOENIX", "PHILADELPHIA", "DALLAS", "AUSTIN",
        "JACKSONVILLE", "COLUMBUS", "CHARLOTTE", "INDIANAPOLIS", "SEATTLE",
        "DENVER", "BOSTON", "NASHVILLE", "DETROIT", "PORTLAND", "MEMPHIS",
        "LOUISVILLE", "MILWAUKEE", "ALBUQUERQUE", "TUCSON", "FRESNO",
        "SACRAMENTO", "MESA", "ATLANTA", "OMAHA", "RALEIGH", "MIAMI",
        "OAKLAND", "MINNEAPOLIS", "TULSA", "WICHITA", "ARLINGTON", "TAMPA",
        "AURORA", "ANAHEIM", "HONOLULU", "RIVERSIDE", "CORPUS CHRISTI",
        "LEXINGTON", "HENDERSON", "STOCKTON", "SAINT PAUL", "CINCINNATI",
        "PITTSBURGH", "GREENSBORO", "ANCHORAGE", "PLANO", "ORLANDO", "IRVINE",
        "NEWARK", "DURHAM", "CHANDLER", "LAREDO", "LUBBOCK", "MADISON",
        "GILBERT", "RENO", "HIALEAH", "GARLAND", "GLENDALE", "SCOTTSDALE",
        "IRVING", "FREMONT", "BOISE", "RICHMOND", "BALTIMORE", "MILPITAS",
        "CARLSBAD", "ESCONDIDO", "OCEANSIDE", "VISTA", "POWAY", "ENCINITAS",
        "BROOKLYN", "QUEENS", "BRONX", "MANHATTAN", "CAMBRIDGE", "BERKELEY",
        "PASADENA", "BURBANK", "TORRANCE", "INGLEWOOD", "COMPTON", "NORWALK",
    }
)

_VOWELS = frozenset("AEIOUY")


@dataclass(frozen=True)
class Descriptor:
    key: str      # canonical merchant identity (uppercase)
    display: str  # title-cased name for the UI


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _is_junk_token(token: str) -> bool:
    """True for tokens that are reference ids rather than words.

    The mixed-alphanumeric and vowel-free heuristics are what kill
    ``B26ME6RT2`` and ``164QPBFEQ8G`` while leaving real names intact. They are
    heuristics, hence _KEEP_TOKENS for the known exceptions.
    """
    if token in _KEEP_TOKENS:
        return False
    if token.isdigit():
        return True
    if len(token) == 1:
        return True
    has_digit = any(c.isdigit() for c in token)
    has_alpha = any(c.isalpha() for c in token)
    if len(token) >= 5 and has_digit and has_alpha:
        return True
    if len(token) >= 6 and not (_VOWELS & set(token)):
        return True
    return False


def _resolve_asterisks(text: str) -> str:
    """Pick the merchant side of a facilitator*merchant descriptor.

    Loops because chains happen in the wild: ``APPLE PAY *SQ *BLUE BOTTLE``.
    """
    for _ in range(3):
        if "*" not in text:
            break
        parts = [p.strip() for p in text.split("*") if p.strip()]
        if not parts:
            break
        head = parts[0]
        is_aggregator = (
            head in AGGREGATOR_PREFIXES or head.rstrip(".") in AGGREGATOR_PREFIXES
        )
        if len(parts) > 1 and is_aggregator:
            text = "*".join(parts[1:])
        else:
            text = head
            break
    return text.strip()


# Variants of one merchant that should share a single category decision. Keys
# are matched as prefixes against the normalized key, longest first, so
# "AMAZON MKTPL" and "AMAZON MARKETPLACE" both fold into "AMAZON".
#
# Sub-brands are deliberately NOT folded when they mean different spending:
# AMAZON KIDS and PRIME VIDEO stay distinct from AMAZON.
MERCHANT_ALIASES: dict[str, str] = {
    "AMAZON MKTPL": "AMAZON",
    "AMAZON MKTPLACE PMTS": "AMAZON",
    "AMAZON MARKETPLACE": "AMAZON",
    "AMAZON RETA": "AMAZON",
    "AMAZON RET": "AMAZON",
    "AMAZON DIGITAL SVCS": "AMAZON DIGITAL",
    "AMZN MKTP": "AMAZON",
    "AMZN": "AMAZON",
    "WAL-MART": "WALMART",
    "WM SUPERCENTER": "WALMART",
    "WALMART GROCERY": "WALMART",
    "TARGET T": "TARGET",
    "THE HOME DEPOT": "HOME DEPOT",
    "MCDONALD'S": "MCDONALDS",
    "TRADER JOE'S": "TRADER JOES",
    "WHOLEFDS": "WHOLE FOODS",
    "WHOLE FOODS MARKET": "WHOLE FOODS",
    "SAFEWAY STORE": "SAFEWAY",
    "STARBUCKS STORE": "STARBUCKS",
    "SBUX": "STARBUCKS",
    "CHICK-FIL-A": "CHICK FIL A",
    "CHICKFILA": "CHICK FIL A",
    "CHKFILA": "CHICK FIL A",
    "UBER EATS": "UBER EATS",
    "UBER TRIP": "UBER",
    "LYFT RIDE": "LYFT",
    "NETFLIX.COM": "NETFLIX",
    "SPOTIFY USA": "SPOTIFY",
    "APPLE STORE": "APPLE",
    "GOOGLE STORAGE": "GOOGLE",
    "GOOGLE YOUTUBEPREMIUM": "YOUTUBE PREMIUM",
    "AT&T PAYMENT": "AT&T",
    "ATT PAYMENT": "AT&T",
    "ATT": "AT&T",
    "T MOBILE": "T-MOBILE",
    "TMOBILE": "T-MOBILE",
    "SEVEN-ELEVEN": "7-ELEVEN",
    "7 ELEVEN": "7-ELEVEN",
    "COSTCO WHSE": "COSTCO",
    "COSTCO GAS": "COSTCO GAS",
}

_ALIAS_KEYS = sorted(MERCHANT_ALIASES, key=len, reverse=True)


def apply_aliases(key: str) -> str:
    """Fold a normalized key onto its canonical merchant, if known."""
    if key in MERCHANT_ALIASES:
        return MERCHANT_ALIASES[key]
    for alias in _ALIAS_KEYS:
        if key.startswith(alias):
            return MERCHANT_ALIASES[alias]
    return key


def _titleise(key: str) -> str:
    """Readable display name. Keeps all-caps acronyms and brand punctuation."""
    words = []
    for word in key.split():
        if word in _KEEP_TOKENS or not word.isalpha():
            # Known acronyms, and anything with punctuation or digits, keep
            # their exact casing: AT&T, 7-ELEVEN, H2O, PG&E.
            words.append(word)
        else:
            words.append(word.capitalize())
    return " ".join(words)


def normalize(raw: str) -> Descriptor:
    """Reduce a raw descriptor to a canonical merchant key + display name.

    Never returns an empty key: if stripping removes everything, the collapsed
    original is used instead. An empty key would merge unrelated transactions
    into one bucket, which is far worse than a noisy one.
    """
    original = re.sub(r"\s+", " ", (raw or "").strip())
    if not original:
        return Descriptor(key="UNKNOWN", display="Unknown")

    text = _strip_accents(original).upper()
    text = _ACH_TAGS.sub("", text)

    previous = None
    while previous != text:
        previous = text
        text = _NOISE_PREFIX.sub("", text).strip()

    text = _resolve_asterisks(text)

    for pattern in _STRIPPERS:
        text = pattern.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()

    tokens = text.split()
    # Trailing state code, but never the only token left.
    dropped_state = False
    while len(tokens) >= 2 and tokens[-1] in _US_STATES:
        tokens.pop()
        dropped_state = True
    # A city only counts when it sat right before that state code, and only when
    # something is left over to identify the merchant by.
    if dropped_state:
        for span in (3, 2, 1):
            if len(tokens) > span and " ".join(tokens[-span:]) in _CITY_NAMES:
                del tokens[-span:]
                break
    tokens = [t for t in tokens if not _is_junk_token(t)]

    key = " ".join(tokens).strip(" -_,.#*")
    if not key:
        key = original.upper()
    key = apply_aliases(key)
    return Descriptor(key=key, display=_titleise(key))


def canonical_key(raw: str) -> str:
    """Convenience wrapper — just the key."""
    return normalize(raw).key
