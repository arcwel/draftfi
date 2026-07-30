"""Deterministic merchant → category rules, and transfer/income detection.

Why rules at all, when there's an LLM? Three reasons, in order of importance:

1. **Determinism.** A user forgives a wrong category they can fix. They do not
   forgive a category that changes between refreshes. Published work makes the
   same trade: one retail-bank study found rules *less* accurate than ML (39% vs
   56%) and still shipped rules first, because stability beats a few points.
2. **Coverage for free.** Merchant frequency is Zipf-ish. An open-source
   reference implementation found its top-100 hand-labelled merchants covered
   35% of all transactions; a single household is far more repetitive than a
   population, so the real figure here should be higher.
3. **The tail is where models fail.** An LLM benchmark on this exact task scored
   80% overall but **0% on rare categories** — it guesses confidently rather
   than abstaining. Rules pin the things we actually know.

Transfers are handled *before* categorization, which is the other half of the
problem. A credit-card payment out of checking is not spending — the purchases
it settles were already counted — and counting both double-counts every dollar.
Same for internal transfers, Venmo reimbursements, and payroll deposits.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Non-spending buckets. TRANSFERS is excluded from spending aggregates entirely
# (see categories.is_transfer); INCOME is separated by sign already.
CATEGORY_TRANSFERS = "Transfers"
CATEGORY_INCOME = "Income"
UNCATEGORIZED = "Uncategorized"


@dataclass(frozen=True)
class Match:
    category: str
    source: str  # 'rule' | 'transfer'


# --------------------------------------------------------------------------- #
# Transfers, card payments, and income
# --------------------------------------------------------------------------- #
# Money moving between the user's own accounts, or between them and a person.
# Neither side is consumption.
_TRANSFER_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^VENMO",
        r"^ZELLE",
        r"\bZELLE\b",
        r"^CASH APP",
        r"^SQUARE CASH",
        r"^APPLE CASH",
        r"^PAYPAL TRANSFER",
        r"^TRANSFER (FROM|TO)\b",
        r"^ONLINE TRANSFER",
        r"^INTERNAL TRANSFER",
        r"^WIRE (TRANSFER|IN|OUT)\b",
        r"^ATM (WITHDRAWAL|DEPOSIT|CASH)",
        r"^CASH WITHDRAWAL",
        r"^WITHDRAWAL TRANSFER",
        r"^OVERDRAFT PROTECTION",
        r"\bE-?PAYMENT\b",
        r"\bINTERNET PAYMENT\b",
        r"\bMOBILE PMT\b",
        r"\bMOBILE PAYMENT\b",
        r"\bAUTOPAY\b.*\bPAYMENT\b",
        # Card issuers seen as an outbound payment from a checking account.
        r"^(CAPITAL ONE|CHASE|DISCOVER|AMEX|AMERICAN EXPRESS|CITI|BARCLAYCARD|"
        r"SYNCHRONY|WELLS FARGO|BANK OF AMERICA|USAA|NAVY FEDERAL|APPLE CARD)\b"
        r".*\b(PAYMENT|PMT|E-PAYMENT|EPAY|AUTOPAY|TRANSFER)\b",
        r"^PAYMENT THANK YOU",
        r"^THANK YOU PAYMENT",
    )
)

# Deposits that are earnings rather than transfers.
_INCOME_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bPAYROLL\b",
        r"\bDIRECT DEP\b",
        r"\bDIR DEP\b",
        r"\bSALARY\b",
        r"\bPAYCHECK\b",
        r"\bGUSTO\b",
        r"\bADP\b",
        r"\bPAYCHEX\b",
        r"\bTRINET\b",
        r"\bRIPPLING\b",
        r"\bIRS TREAS\b",
        r"\bTAX REF\b",
        r"\bUNEMPLOYMENT\b",
        r"\bSSA TREAS\b",
        r"\bDIVIDEND\b",
        r"\bINTEREST PAID\b",
    )
)


def classify_flow(key: str, amount: float | None = None) -> Match | None:
    """Detect transfers/card payments/income before any categorization.

    Runs first because these are structural facts about the transaction, not
    judgements about it — and because getting them wrong corrupts every
    downstream total.
    """
    for pattern in _INCOME_PATTERNS:
        if pattern.search(key):
            # A payroll *reversal* is negative; treat that as a transfer rather
            # than negative income, which would understate earnings.
            if amount is not None and amount < 0:
                return Match(CATEGORY_TRANSFERS, "transfer")
            return Match(CATEGORY_INCOME, "transfer")
    for pattern in _TRANSFER_PATTERNS:
        if pattern.search(key):
            return Match(CATEGORY_TRANSFERS, "transfer")
    return None


# --------------------------------------------------------------------------- #
# Seeded merchant rules
# --------------------------------------------------------------------------- #
# Matched against the canonical key from services.descriptors: exact first, then
# longest-prefix. Deliberately conservative — a merchant that genuinely spans
# categories (Costco: groceries AND gas AND shopping) is left to the model
# unless a sub-brand key disambiguates it.
MERCHANT_CATEGORIES: dict[str, str] = {
    # ---- Groceries ----
    "SAFEWAY": "Groceries", "VONS": "Groceries", "ALBERTSONS": "Groceries",
    "KROGER": "Groceries", "RALPHS": "Groceries", "TRADER JOES": "Groceries",
    "WHOLE FOODS": "Groceries", "SPROUTS": "Groceries", "ALDI": "Groceries",
    "PUBLIX": "Groceries", "HEB": "Groceries", "WEGMANS": "Groceries",
    "FOOD LION": "Groceries", "GIANT": "Groceries", "MEIJER": "Groceries",
    "WINCO": "Groceries", "STATER BROS": "Groceries", "SMART FINAL": "Groceries",
    "GROCERY OUTLET": "Groceries", "FRESH MARKET": "Groceries",
    "INSTACART": "Groceries", "SAFEWAY FUEL": "Transportation",
    # ---- Dining ----
    "STARBUCKS": "Dining", "MCDONALDS": "Dining", "CHIPOTLE": "Dining",
    "CHICK FIL A": "Dining", "SUBWAY": "Dining", "TACO BELL": "Dining",
    "PANERA": "Dining", "DUNKIN": "Dining", "WENDYS": "Dining",
    "BURGER KING": "Dining", "IN-N-OUT": "Dining", "IN N OUT": "Dining",
    "SHAKE SHACK": "Dining", "PANDA EXPRESS": "Dining", "POPEYES": "Dining",
    "KFC": "Dining", "DOMINOS": "Dining", "PIZZA HUT": "Dining",
    "PAPA JOHNS": "Dining", "ROUND TABLE PIZZA": "Dining", "IHOP": "Dining",
    "DENNYS": "Dining", "OLIVE GARDEN": "Dining", "CHEESECAKE FACTORY": "Dining",
    "DOORDASH": "Dining", "UBER EATS": "Dining", "GRUBHUB": "Dining",
    "POSTMATES": "Dining", "SEAMLESS": "Dining", "CAVIAR": "Dining",
    "SWEETGREEN": "Dining", "PEETS": "Dining", "DUTCH BROS": "Dining",
    "JAMBA": "Dining", "COLD STONE": "Dining", "BASKIN": "Dining",
    # ---- Shopping ----
    "AMAZON": "Shopping", "WALMART": "Shopping", "TARGET": "Shopping",
    "COSTCO": "Shopping", "BEST BUY": "Shopping", "HOME DEPOT": "Shopping",
    "LOWES": "Shopping", "IKEA": "Shopping", "WAYFAIR": "Shopping",
    "ETSY": "Shopping", "EBAY": "Shopping", "TEMU": "Shopping",
    "SHEIN": "Shopping", "NORDSTROM": "Shopping", "MACYS": "Shopping",
    "KOHLS": "Shopping", "ROSS": "Shopping", "TJ MAXX": "Shopping",
    "MARSHALLS": "Shopping", "OLD NAVY": "Shopping", "GAP": "Shopping",
    "H&M": "Shopping", "UNIQLO": "Shopping", "ZARA": "Shopping",
    "NIKE": "Shopping", "ADIDAS": "Shopping", "LULULEMON": "Shopping",
    "REI": "Shopping", "DICKS SPORTING": "Shopping", "MICHAELS": "Shopping",
    "STAPLES": "Shopping", "OFFICE DEPOT": "Shopping", "PETCO": "Shopping",
    "PETSMART": "Shopping", "CHEWY": "Shopping", "ACE HARDWARE": "Shopping",
    "HARBOR FREIGHT": "Shopping", "DOLLAR TREE": "Shopping",
    "DOLLAR GENERAL": "Shopping", "FIVE BELOW": "Shopping",
    "BED BATH": "Shopping", "WILLIAMS SONOMA": "Shopping",
    "CRATE BARREL": "Shopping", "WEST ELM": "Shopping",
    # ---- Transportation ----
    "UBER": "Transportation", "LYFT": "Transportation", "SHELL": "Transportation",
    "CHEVRON": "Transportation", "EXXON": "Transportation", "MOBIL": "Transportation",
    "ARCO": "Transportation", "VALERO": "Transportation", "TEXACO": "Transportation",
    "BP": "Transportation", "SUNOCO": "Transportation", "CITGO": "Transportation",
    "76": "Transportation", "COSTCO GAS": "Transportation",
    "SPEEDWAY": "Transportation", "WAWA": "Transportation",
    "CIRCLE K": "Transportation", "QUIKTRIP": "Transportation",
    "7-ELEVEN": "Transportation", "AMPM": "Transportation",
    "PARKING": "Transportation", "SPOTHERO": "Transportation",
    "FASTRAK": "Transportation", "EZPASS": "Transportation",
    "DMV": "Transportation", "JIFFY LUBE": "Transportation",
    "VALVOLINE": "Transportation", "DISCOUNT TIRE": "Transportation",
    "AUTOZONE": "Transportation", "OREILLY": "Transportation",
    "NAPA AUTO": "Transportation", "TESLA SUPERCHARGER": "Transportation",
    "CHARGEPOINT": "Transportation", "EVGO": "Transportation",
    "BART": "Transportation", "MTA": "Transportation", "CLIPPER": "Transportation",
    "AMTRAK": "Transportation", "TURO": "Transportation", "ZIPCAR": "Transportation",
    # ---- Utilities ----
    "AT&T": "Utilities", "T-MOBILE": "Utilities", "VERIZON": "Utilities",
    "SPRINT": "Utilities", "MINT MOBILE": "Utilities", "VISIBLE": "Utilities",
    "GOOGLE FI": "Utilities", "COMCAST": "Utilities", "XFINITY": "Utilities",
    "SPECTRUM": "Utilities", "COX COMM": "Utilities", "CENTURYLINK": "Utilities",
    "FRONTIER COMM": "Utilities", "STARLINK": "Utilities",
    "PG&E": "Utilities", "SDG&E": "Utilities", "SOCALGAS": "Utilities",
    "EDISON": "Utilities", "DUKE ENERGY": "Utilities", "CON EDISON": "Utilities",
    "NATIONAL GRID": "Utilities", "WASTE MANAGEMENT": "Utilities",
    "REPUBLIC SERVICES": "Utilities", "CITY OF": "Utilities",
    "WATER DEPT": "Utilities", "WATER DISTRICT": "Utilities",
    # ---- Software Subscriptions ----
    "NETFLIX": "Entertainment", "HULU": "Entertainment",
    "DISNEY PLUS": "Entertainment", "HBO MAX": "Entertainment",
    "MAX": "Entertainment", "PARAMOUNT": "Entertainment",
    "PEACOCK": "Entertainment", "SPOTIFY": "Entertainment",
    "YOUTUBE PREMIUM": "Entertainment", "APPLE TV": "Entertainment",
    "AUDIBLE": "Entertainment", "TWITCH": "Entertainment",
    "PRIME VIDEO": "Entertainment", "STEAM": "Entertainment",
    "PLAYSTATION": "Entertainment", "XBOX": "Entertainment",
    "NINTENDO": "Entertainment", "AMC": "Entertainment",
    "REGAL CINEMAS": "Entertainment", "CINEMARK": "Entertainment",
    "TICKETMASTER": "Entertainment", "STUBHUB": "Entertainment",
    "EVENTBRITE": "Entertainment", "PATREON": "Entertainment",
    "GITHUB": "Software Subscriptions", "OPENAI": "Software Subscriptions",
    "ANTHROPIC": "Software Subscriptions", "CLAUDE": "Software Subscriptions",
    "ADOBE": "Software Subscriptions", "MICROSOFT": "Software Subscriptions",
    "GOOGLE": "Software Subscriptions", "DROPBOX": "Software Subscriptions",
    "NOTION": "Software Subscriptions", "SLACK": "Software Subscriptions",
    "ZOOM": "Software Subscriptions", "FIGMA": "Software Subscriptions",
    "ATLASSIAN": "Software Subscriptions", "LINEAR": "Software Subscriptions",
    "VERCEL": "Software Subscriptions", "NETLIFY": "Software Subscriptions",
    "DIGITALOCEAN": "Software Subscriptions", "LINODE": "Software Subscriptions",
    "CLOUDFLARE": "Software Subscriptions", "NAMECHEAP": "Software Subscriptions",
    "GODADDY": "Software Subscriptions", "AWS": "Software Subscriptions",
    "APPLE": "Software Subscriptions", "1PASSWORD": "Software Subscriptions",
    "LASTPASS": "Software Subscriptions", "NORDVPN": "Software Subscriptions",
    "GRAMMARLY": "Software Subscriptions", "CANVA": "Software Subscriptions",
    # ---- Healthcare ----
    "CVS": "Healthcare", "WALGREENS": "Healthcare", "RITE AID": "Healthcare",
    "KAISER": "Healthcare", "QUEST DIAGNOSTICS": "Healthcare",
    "LABCORP": "Healthcare", "ONE MEDICAL": "Healthcare",
    "ZOCDOC": "Healthcare", "GOODRX": "Healthcare", "DENTAL": "Healthcare",
    "OPTOMETRY": "Healthcare", "PHARMACY": "Healthcare",
    "BLUE SHIELD": "Healthcare", "BLUE CROSS": "Healthcare",
    "UNITEDHEALTH": "Healthcare", "AETNA": "Healthcare", "CIGNA": "Healthcare",
    # ---- Housing ----
    "RENT": "Housing", "PROPERTY MGMT": "Housing", "HOA": "Housing",
    "MORTGAGE": "Housing", "ZILLOW RENTAL": "Housing",
    "PUBLIC STORAGE": "Housing", "EXTRA SPACE": "Housing",
    "STATE FARM": "Housing", "GEICO": "Transportation",
    "PROGRESSIVE": "Transportation", "ALLSTATE": "Housing",
    "LEMONADE INS": "Housing",
    # ---- Travel ----
    "AIRBNB": "Travel", "VRBO": "Travel", "BOOKING.COM": "Travel",
    "EXPEDIA": "Travel", "HOTELS.COM": "Travel", "MARRIOTT": "Travel",
    "HILTON": "Travel", "HYATT": "Travel", "IHG": "Travel",
    "UNITED AIRLINES": "Travel", "DELTA AIR": "Travel",
    "AMERICAN AIR": "Travel", "SOUTHWEST": "Travel", "ALASKA AIR": "Travel",
    "JETBLUE": "Travel", "FRONTIER AIR": "Travel", "SPIRIT AIR": "Travel",
    "HERTZ": "Travel", "AVIS": "Travel", "ENTERPRISE RENT": "Travel",
    "TSA PRE": "Travel", "GLOBAL ENTRY": "Travel", "CLEAR": "Travel",
    # ---- Savings & Investments ----
    "ROBINHOOD": "Savings & Investments", "VANGUARD": "Savings & Investments",
    "FIDELITY": "Savings & Investments", "SCHWAB": "Savings & Investments",
    "ETRADE": "Savings & Investments", "COINBASE": "Savings & Investments",
    "KRAKEN": "Savings & Investments", "BETTERMENT": "Savings & Investments",
    "WEALTHFRONT": "Savings & Investments", "ACORNS": "Savings & Investments",
    "M1 FINANCE": "Savings & Investments", "FUNDRISE": "Savings & Investments",
    # ---- Fees & Interest ----
    "OVERDRAFT FEE": "Fees & Interest", "MONTHLY SERVICE FEE": "Fees & Interest",
    "MAINTENANCE FEE": "Fees & Interest", "ATM FEE": "Fees & Interest",
    "FOREIGN TRANSACTION FEE": "Fees & Interest",
    "LATE FEE": "Fees & Interest", "INTEREST CHARGE": "Fees & Interest",
    "FINANCE CHARGE": "Fees & Interest", "ANNUAL MEMBERSHIP FEE": "Fees & Interest",
    "WIRE FEE": "Fees & Interest", "RETURNED ITEM FEE": "Fees & Interest",
}

# Merchants that genuinely span categories. The rule table still gives them a
# default for brand-new rows, but a repair pass must never overwrite an existing
# category for one of these: a warehouse club is groceries AND household AND
# petrol, and a convenience store is snacks AND fuel. Our guess is not better
# than whatever is already there, and silently "correcting" 337 Costco rows is
# imposing an opinion rather than fixing an error.
AMBIGUOUS_MERCHANTS = frozenset(
    {
        "COSTCO", "COSTCO GAS", "WALMART", "TARGET", "SAMS CLUB", "BJS",
        "7-ELEVEN", "CIRCLE K", "WAWA", "QUIKTRIP", "SPEEDWAY", "AMPM",
        "VONS FUEL", "SAFEWAY FUEL", "KROGER FUEL", "MEIJER", "CVS",
        "WALGREENS", "RITE AID", "DOLLAR GENERAL", "DOLLAR TREE",
        "PAYPAL", "VENMO", "SQUARE", "APPLE", "GOOGLE", "AMAZON",
    }
)


def is_ambiguous(key: str) -> bool:
    """True when this merchant's category is a judgement call, not a fact."""
    if key in AMBIGUOUS_MERCHANTS:
        return True
    return any(key.startswith(m) for m in AMBIGUOUS_MERCHANTS)


_RULE_KEYS = sorted(MERCHANT_CATEGORIES, key=len, reverse=True)


def lookup(key: str) -> Match | None:
    """Exact match, then longest prefix. Returns None when nothing is known."""
    category = MERCHANT_CATEGORIES.get(key)
    if category:
        return Match(category, "rule")
    for rule_key in _RULE_KEYS:
        if key.startswith(rule_key):
            return Match(MERCHANT_CATEGORIES[rule_key], "rule")
    return None


def resolve(key: str, amount: float | None = None) -> Match | None:
    """Full deterministic pass: flow detection first, then merchant rules.

    Order matters. "CAPITAL ONE MOBILE PMT" must read as a transfer, not as
    whatever a Capital One merchant rule might say.
    """
    flow = classify_flow(key, amount)
    if flow is not None:
        return flow
    return lookup(key)


def rule_count() -> int:
    """Number of seeded merchant rules — surfaced in diagnostics."""
    return len(MERCHANT_CATEGORIES)
