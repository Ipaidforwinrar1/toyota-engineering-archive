from knowledge.normalize import normalize_term

def search_components(conn, query, limit=20):
    q = normalize_term(query)
    like = f"%{q}%"
    return conn.execute(
        '''
        WITH matched_components AS (
            SELECT DISTINCT c.component_id
            FROM components c
            LEFT JOIN component_aliases a ON a.component_id=c.component_id
            WHERE c.normalized_name LIKE ? OR a.normalized_alias LIKE ?
        ),
        component_hits AS (
            SELECT component_id,
                   COUNT(DISTINCT document_id) AS document_count,
                   COALESCE(SUM(occurrence_count),0) AS occurrence_count,
                   COALESCE(SUM(occurrence_count * confidence),0) AS weighted_score,
                   COALESCE(AVG(confidence),0) AS average_confidence
            FROM document_components
            GROUP BY component_id
        )
        SELECT c.component_id,
               c.canonical_name,
               c.system_name,
               COALESCE(h.document_count,0) AS document_count,
               COALESCE(h.occurrence_count,0) AS occurrence_count,
               COALESCE(h.weighted_score,0) AS weighted_score,
               COALESCE(h.average_confidence,0) AS average_confidence,
               COALESCE(q.is_generic,0) AS is_generic,
               COALESCE(q.quality_weight,1.0) AS quality_weight
        FROM matched_components m
        JOIN components c ON c.component_id=m.component_id
        LEFT JOIN component_hits h ON h.component_id=c.component_id
        LEFT JOIN component_quality q ON q.component_id=c.component_id
        ORDER BY CASE WHEN c.normalized_name=? THEN 0 ELSE 1 END,
                 weighted_score DESC, document_count DESC, c.canonical_name
        LIMIT ?
        ''', (like, like, q, limit)
    ).fetchall()

def component_details(conn, component_id, limit=100):
    c = conn.execute("SELECT * FROM components WHERE component_id=?", (component_id,)).fetchone()
    docs = conn.execute(
        '''
        SELECT dc.document_id,
               d.title,
               dc.reference_id,
               d.manual_type_normalized,
               d.system_name,
               d.section_path,
               dc.page_number,
               dc.occurrence_count,
               dc.confidence,
               dc.first_context
        FROM document_components dc
        JOIN documents d ON d.id = dc.document_id
        WHERE dc.component_id=?
        ORDER BY dc.occurrence_count DESC, d.reference_id, dc.page_number LIMIT ?
        ''', (component_id, limit)
    ).fetchall()
    return c, docs
