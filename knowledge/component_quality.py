from knowledge.normalize import normalize_term


def text_contains_term(text, term):
    return normalize_term(term) in normalize_term(text or "")


def load_quality_by_component(conn):
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='component_quality'"
    ).fetchone():
        return {}
    rows = conn.execute(
        """
        SELECT component_id, is_generic, quality_weight
        FROM component_quality
        """
    ).fetchall()
    return {
        row["component_id"]: {
            "is_generic": bool(row["is_generic"]),
            "quality_weight": float(row["quality_weight"]),
        }
        for row in rows
    }


def load_terms_by_component(conn):
    rows = conn.execute(
        """
        SELECT c.component_id, c.canonical_name AS term
        FROM components c
        UNION
        SELECT a.component_id, a.alias AS term
        FROM component_aliases a
        """
    ).fetchall()
    result = {}
    for row in rows:
        result.setdefault(row["component_id"], set()).add(row["term"])
    return {component_id: sorted(terms, key=len, reverse=True) for component_id, terms in result.items()}


def contains_any_term(text, terms):
    return any(text_contains_term(text, term) for term in terms)


def component_confidence(
    canonical_name,
    occurrence_count,
    title="",
    section_path="",
    context="",
    quality=None,
    terms=None,
):
    terms = terms or [canonical_name]
    score = 0.55
    if contains_any_term(title, terms):
        score += 0.30
    if contains_any_term(section_path, terms):
        score += 0.20
    if contains_any_term(context[:350], terms):
        score += 0.10
    if occurrence_count > 1:
        score += 0.05

    quality_weight = 1.0
    if quality:
        quality_weight = quality.get("quality_weight", 1.0)

    return round(max(0.05, min(score * quality_weight, 1.0)), 3)
