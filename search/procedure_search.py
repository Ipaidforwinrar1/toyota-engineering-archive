def procedure_details(conn, component_id, procedure_type=None, limit=50):
    values = [component_id]
    where = ["p.component_id=?"]
    if procedure_type:
        where.append("p.procedure_type=?")
        values.append(procedure_type.title())
    values.append(limit)
    return conn.execute(
        f'''
        SELECT p.procedure_id,
               p.procedure_type,
               p.title,
               p.context,
               p.step_count,
               p.confidence,
               p.page_number,
               d.reference_id,
               d.title AS document_title,
               d.manual_type_normalized,
               d.system_name,
               d.section_path
        FROM procedures p
        JOIN documents d ON d.id = p.document_id
        WHERE {' AND '.join(where)}
        ORDER BY p.procedure_type, d.reference_id, p.page_number
        LIMIT ?
        ''',
        values,
    ).fetchall()


def procedure_type_counts(conn, component_id):
    return conn.execute(
        '''
        SELECT procedure_type, COUNT(*) AS procedure_count
        FROM procedures
        WHERE component_id=?
        GROUP BY procedure_type
        ORDER BY procedure_type
        ''',
        (component_id,),
    ).fetchall()
