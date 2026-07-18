import re
import unicodedata

def normalize_term(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("&", " and ").lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()
