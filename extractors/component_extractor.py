from dataclasses import dataclass
import re

@dataclass
class Mention:
    component_id: int
    canonical_name: str
    count: int
    first_context: str

def compile_patterns(rows):
    result = []
    for component_id, canonical_name, alias in rows:
        tokens = re.findall(r"[A-Za-z0-9]+", alias)
        if not tokens:
            continue
        body = r"[\W_]+".join(re.escape(t) for t in tokens)
        pattern = re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.I)
        result.append((len(alias), component_id, canonical_name, pattern))
    return sorted(result, key=lambda x: x[0],reverse=True)

def extract_components(text, patterns, context_chars=100):
    found = {}
    occupied = []
    for _, component_id, canonical_name, pattern in patterns:
        accepted = []
        for match in pattern.finditer(text or ""):
            a, b = match.span()
            if any(not (b <= x or a >= y) for x, y in occupied):
                continue
            accepted.append(match)
            occupied.append((a, b))
        if not accepted:
            continue
        first = accepted[0]
        context = " ".join(text[max(0, first.start()-context_chars):
                                min(len(text), first.end()+context_chars)].split())
        if component_id in found:
            found[component_id].count += len(accepted)
        else:
            found[component_id] = Mention(component_id, canonical_name, len(accepted), context)
    return list(found.values())
