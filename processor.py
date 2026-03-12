import os
import re
import csv
import sys
import html
from pathlib import Path
from collections import defaultdict

try:
    from docx import Document  # pip install python-docx
except ImportError:
    print("Missing dependency: python-docx\nInstall it with: pip install python-docx")
    sys.exit(1)

# ===================== PATHS & ENV =====================

# In CI, we’ll provide INPUT_DOCX_PATH and OUT_DIR via environment variables
BASE_TXT_PATH = Path(os.environ.get("BASE_TXT_PATH", "data/rules.txt"))
INPUT_DOCX_PATH = Path(os.environ.get("INPUT_DOCX_PATH", "input.docx"))

OUT_DIR = Path(os.environ.get("OUT_DIR", "outputs"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_CSV_PATH = OUT_DIR / "output.csv"
UPDATED_RULES_PATH = OUT_DIR / "updated_rules.txt"
LATEST_ENTRIES_TXT = OUT_DIR / "latest_entries.txt"

# ===================== TOKENIZATION =====================
# words = a letter followed by letters or ' or -
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]*", flags=re.UNICODE)

# ===================== OUTPUT PREFERENCES ===============
CSV_DELIMITER = "\t"  # use "," if you prefer
WRITE_PRETTY_TSV = False
PRETTY_TSV_PATH = OUT_DIR / "output_readable.tsv"

# ===================== SPECIAL CATEGORY =================
UNASSIGNED_CATEGORY_NAME = "UNSSIGNED CATEGORY"
UNASSIGNED_HEADER_EXACT = "#-- UNSSIGNED CATEGORY --#"  # exact header line

# ===================== FLAGS ============================
WRITE_LATEST_TXT = True
WRITE_UPDATED_TXX = True  # kept for backward compatibility if referenced elsewhere
WRITE_UPDATED_TXT = True  # actual flag (used below)

# ===================== PARSERS ==========================
CATEGORY_HEADER_RE = re.compile(
    r"^\s*#\s*--\s*(?P<name>.+?)\s*--\s*#\s*$"
)
ENTRY_RE = re.compile(
    r"""^\s*\d+\s+\[(?P<word>.+?)\]\s*~=\s*(?P<code>[^\s-]+)""",
    flags=re.UNICODE,
)

def load_base_lexicon(txt_path: Path):
    """
    Parse base .txt of the form:
        # -- CATEGORY -- #
        1 [WORD]~=CODE -
    Returns:
        categories: dict[str, list[dict(word, code)]]
        word_index: dict[word_upper] -> (category, code)
    """
    categories = defaultdict(list)
    word_index = {}

    if not txt_path.exists():
        print(f"⚠️ Base file not found; starting with empty base: {txt_path}")
        return categories, word_index

    current_category = None
    with txt_path.open(encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            m_cat = CATEGORY_HEADER_RE.match(line)
            if m_cat:
                current_category = html.unescape(m_cat.group("name")).strip()
                continue

            if not line or line.lstrip().startswith("#"):
                continue

            m_entry = ENTRY_RE.match(line)
            if not m_entry:
                continue

            raw_word = html.unescape(m_entry.group("word")).strip()
            raw_code = html.unescape(m_entry.group("code")).strip()
            idx_word = raw_word.upper()
            cat = current_category if current_category else "UNCATEGORIZED"

            # Keep first occurrence only (avoid duplication)
            if idx_word not in word_index:
                categories[cat].append({"word": raw_word, "code": raw_code})
                word_index[idx_word] = (cat, raw_code)

    return categories, word_index


def extract_words_from_docx(docx_path: Path):
    """
    Extract alphabetic tokens (no digits) from .docx and return a set of uppercase tokens.
    """
    if not docx_path.exists():
        print(f"❌ DOCX not found: {docx_path}")
        sys.exit(1)
    if docx_path.suffix.lower() != ".docx":
        print(f"❌ Not a .docx file: {docx_path}")
        sys.exit(1)

    # Quick probe for locks
    with docx_path.open("rb"):
        pass

    doc = Document(docx_path)
    tokens = set()
    for p in doc.paragraphs:
        for t in TOKEN_RE.findall(p.text):
            if any(ch.isdigit() for ch in t):
                continue
            tokens.add(t.upper())
    return tokens


# ===================== CODE GENERATION ==================
# New words must get a 3-ASCII code with digits allowed ONLY in the 2nd position.
UPPER = [chr(c) for c in range(ord('A'), ord('Z') + 1)]
PUNCT = list("!#$%&'()*+,-./:;<=?@[]\\^_")
DIGIT = list("0123456789")

FIRST_POOL = UPPER + PUNCT         # no digits
SECOND_POOL = DIGIT + UPPER + PUNCT # digits allowed here
THIRD_POOL = UPPER + PUNCT          # no digits

def iter_new_codes_3(used_codes: set[str]):
    """
    Yields new 3-char codes (A..Z + punctuation; digits allowed ONLY in position 2),
    skipping any code already present in used_codes.
    """
    for a in FIRST_POOL:
        for b in SECOND_POOL:
            for c in THIRD_POOL:
                code = a + b + c
                if code not in used_codes:
                    yield code


def add_new_words(categories, word_index, new_words):
    """
    Add only truly new tokens under the UNSSIGNED CATEGORY.
    Returns the list of newly added entries (dicts with word, code="") for later reporting.
    """
    added_entries = []
    if UNASSIGNED_CATEGORY_NAME not in categories:
        categories[UNASSIGNED_CATEGORY_NAME] = []

    for token in sorted(new_words):  # deterministic order
        if token in word_index:
            continue
        entry = {"word": token, "code": ""}
        categories[UNASSIGNED_CATEGORY_NAME].append(entry)
        word_index[token] = (UNASSIGNED_CATEGORY_NAME, "")
        added_entries.append(entry)
    return added_entries


def assign_codes_only_to_missing(categories):
    """
    Assign 3-char codes ONLY to entries with an empty code.
    Uniqueness is global across ALL existing codes (any length).
    Digits are allowed only in the second position for newly assigned codes.
    """
    used = set()
    missing = []
    for cat, entries in categories.items():
        for i, e in enumerate(entries):
            code = (e.get("code") or "").strip()
            if code:
                used.add(code)
            else:
                missing.append((cat, i))

    if not missing:
        return 0

    gen = iter_new_codes_3(used)
    assigned = 0
    for cat, idx in sorted(
        missing,
        key=lambda x: (x[0].upper(), categories[x[0]][x[1]]["word"].upper()),
    ):
        try:
            code = next(gen)
        except StopIteration:
            print("❌ Ran out of 3-cell codes — expand pools.")
            sys.exit(1)
        categories[cat][idx]["code"] = code
        used.add(code)
        assigned += 1
    return assigned


def write_csv(categories, csv_path: Path):
    """
    Write a CSV with stable ordering and NO duplicates.
    Columns: Category, Word, ASCII code
    Encoding: UTF-8 with BOM for Excel compatibility.
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    seen = set()
    rows = []
    for cat in sorted(categories.keys(), key=lambda s: s.upper()):
        for e in sorted(categories[cat], key=lambda x: x["word"].upper()):
            key = e["word"].upper()
            if key in seen:
                continue
            rows.append([cat, e["word"], e["code"]])
            seen.add(key)

    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(
            f,
            delimiter=CSV_DELIMITER,
            quotechar='"',
            quoting=csv.QUOTE_NONE,  # no quotes at all
            escapechar='\\',         # required with QUOTE_NONE
            lineterminator="\n",
        )
        writer.writerow(["Category", "Word", "ASCII code"])
        writer.writerows(rows)
    print(f"✅ CSV written: {csv_path.resolve()} (rows: {len(rows)})")


def write_tsv_pretty(categories, tsv_path: Path):
    """
    Optional: Write a visually aligned TSV for humans (Category, Word, ASCII code).
    Encoding: UTF-8 with BOM.
    """
    tsv_path.parent.mkdir(parents=True, exist_ok=True)

    seen = set()
    rows = []
    for cat in sorted(categories.keys(), key=lambda s: s.upper()):
        for e in sorted(categories[cat], key=lambda x: x["word"].upper()):
            key = e["word"].upper()
            if key in seen:
                continue
            rows.append((cat, e["word"], e["code"]))
            seen.add(key)

    max_cat = min(max((len(k) for k, _, _ in rows), default=8), 40)
    max_word = min(max((len(w) for _, w, _ in rows), default=4), 40)
    max_code = min(max((len(c) for _, _, c in rows), default=4), 12)

    header = ("Category", "Word", "ASCII code")
    lines = []

    def _fmt_row(k, w, c):
        return (
            k.ljust(max_cat) + "\t" +
            w.ljust(max_word) + "\t" +
            c.ljust(max_code)
        )

    lines.append(_fmt_row(*header))
    lines.append(_fmt_row("-" * max_cat, "-" * max_word, "-" * max_code))
    for k, w, c in rows:
        lines.append(_fmt_row(k, w, c))

    with tsv_path.open("w", encoding="utf-8-sig", newline="\n") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    print(f"✅ Pretty TSV written: {tsv_path.resolve()} (rows: {len(rows)})")


def write_latest_entries_txt(latest_entries, txt_path: Path):
    """
    Write only the newly added entries (word -> code) to a separate TXT.
    Escape only words; codes are written raw.
    """
    if not latest_entries:
        print("ℹ️ No new entries to write for latest_entries.")
        return

    def _normalize_code(raw: str) -> str:
        return html.unescape(raw or "")

    lines = [UNASSIGNED_HEADER_EXACT]  # '#-- UNSSIGNED CATEGORY --#'
    for e in sorted(latest_entries, key=lambda x: x["word"].upper()):
        word_txt = html.escape(e["word"], quote=False)
        code_txt = _normalize_code(e["code"])
        lines.append(f"1 [{word_txt}]~={code_txt} -")

    txt_path.parent.mkdir(parents=True, exist_ok=True)
    with txt_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    print(f"✅ Latest entries TXT written: {txt_path.resolve()}")


def write_updated_txt(categories, txt_path: Path):
    """
    Regenerate clean .txt with exact line shape:
        # -- CATEGORY -- #
        1 [WORD]~=CODE -
    Special case: the UNSSIGNED CATEGORY header must be EXACTLY '#-- UNSSIGNED CATEGORY --#'
    """
    lines = []
    for cat in sorted(categories.keys(), key=lambda s: s.upper()):
        if cat == UNASSIGNED_CATEGORY_NAME:
            lines.append(UNASSIGNED_HEADER_EXACT)
        else:
            lines.append(f"# -- {cat} -- #")

        entries = sorted(categories[cat], key=lambda e: e["word"].upper())
        for e in entries:
            word_txt = html.escape(e["word"], quote=False)
            code_txt = e["code"]  # write raw code
            lines.append(f"1 [{word_txt}]~={code_txt} -")
        lines.append("")  # blank line between categories

    txt_path.parent.mkdir(parents=True, exist_ok=True)
    with txt_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    print(f"✅ Updated rules TXT written: {txt_path.resolve()}")


def main():
    base_path = Path(BASE_TXT_PATH)
    docx_path = Path(INPUT_DOCX_PATH)

    # 1) Load base rules
    categories, word_index = load_base_lexicon(base_path)
    print(f"Base categories loaded: {len(categories)}")

    # 2) Extract tokens and keep only truly new
    docx_words = extract_words_from_docx(docx_path)
    print(f"Unique non-numeric tokens from DOCX: {len(docx_words)}")
    new_tokens = {w for w in docx_words if w not in word_index}
    print(f"➕ New words detected: {len(new_tokens)}")

    # 3) Add new words under UNSSIGNED CATEGORY (no codes yet)
    latest_entries = add_new_words(categories, word_index, new_tokens)
    print(f"Added under '{UNASSIGNED_CATEGORY_NAME}': {len(latest_entries)}")

    # 4) Assign new 3-char codes only where missing
    assigned = assign_codes_only_to_missing(categories)
    print(f"Assigned new 3-cell codes: {assigned}")

    # 5) CSV
    write_csv(categories, OUTPUT_CSV_PATH)

    # 6) Optional pretty TSV
    if WRITE_PRETTY_TSV:
        write_tsv_pretty(categories, PRETTY_TSV_PATH)

    # 7) Latest entries (if any)
    if WRITE_LATEST_TXT:
        write_latest_entries_txt(latest_entries, LATEST_ENTRIES_TXT)

    # 8) Updated rules
    if WRITE_UPDATED_TXT:
        write_updated_txt(categories, UPDATED_RULES_PATH)


if __name__ == "__main__":
    main()