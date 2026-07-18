from dataclasses import dataclass, field

from search.component_search import component_details, search_components
from search.procedure_search import procedure_details, procedure_type_counts


@dataclass(frozen=True)
class ComponentSummary:
    component_id: int
    canonical_name: str
    system_name: str
    document_count: int
    occurrence_count: int
    weighted_score: float
    average_confidence: float
    is_generic: bool
    quality_weight: float


@dataclass(frozen=True)
class ComponentQuality:
    is_generic: bool
    quality_weight: float
    average_confidence: float
    weighted_score: float


@dataclass(frozen=True)
class ComponentDocument:
    document_id: int
    title: str
    reference_id: str
    category: str
    system_name: str
    section_path: str
    page_number: int | None
    occurrence_count: int
    confidence: float
    first_context: str


@dataclass(frozen=True)
class ComponentProcedure:
    procedure_id: int
    procedure_type: str
    title: str
    document_title: str
    reference_id: str
    category: str
    system_name: str
    section_path: str
    page_number: int
    step_count: int
    confidence: float
    context: str


@dataclass(frozen=True)
class ComponentKnowledge:
    component: ComponentSummary
    aliases: tuple[str, ...] = field(default_factory=tuple)
    quality: ComponentQuality | None = None
    documents: tuple[ComponentDocument, ...] = field(default_factory=tuple)
    procedures: tuple[ComponentProcedure, ...] = field(default_factory=tuple)
    procedure_counts: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    statistics: dict[str, int | float] = field(default_factory=dict)
    related_items: tuple[str, ...] = field(default_factory=tuple)


def _summary_from_row(row):
    return ComponentSummary(
        component_id=row["component_id"],
        canonical_name=row["canonical_name"],
        system_name=row["system_name"] or "",
        document_count=row["document_count"],
        occurrence_count=row["occurrence_count"],
        weighted_score=float(row["weighted_score"]),
        average_confidence=float(row["average_confidence"]),
        is_generic=bool(row["is_generic"]),
        quality_weight=float(row["quality_weight"]),
    )


def _document_from_row(row):
    return ComponentDocument(
        document_id=row["document_id"],
        title=row["title"] or "",
        reference_id=row["reference_id"] or str(row["document_id"]),
        category=row["manual_type_normalized"] or row["system_name"] or "",
        system_name=row["system_name"] or "",
        section_path=row["section_path"] or "",
        page_number=row["page_number"],
        occurrence_count=row["occurrence_count"],
        confidence=float(row["confidence"]),
        first_context=row["first_context"] or "",
    )


def _procedure_from_row(row):
    return ComponentProcedure(
        procedure_id=row["procedure_id"],
        procedure_type=row["procedure_type"],
        title=row["title"] or "",
        document_title=row["document_title"] or "",
        reference_id=row["reference_id"] or "",
        category=row["manual_type_normalized"] or row["system_name"] or "",
        system_name=row["system_name"] or "",
        section_path=row["section_path"] or "",
        page_number=row["page_number"],
        step_count=row["step_count"],
        confidence=float(row["confidence"]),
        context=row["context"] or "",
    )


class KnowledgeBase:
    def __init__(self, conn):
        self.conn = conn

    def search_components(self, query, limit=20):
        return tuple(_summary_from_row(row) for row in search_components(self.conn, query, limit))

    def get_component(
        self,
        query,
        document_limit=100,
        procedure_limit=50,
        procedure_type=None,
    ):
        matches = self.search_components(query, limit=1)
        if not matches:
            return None
        summary = matches[0]
        component_row, document_rows = component_details(
            self.conn,
            summary.component_id,
            document_limit,
        )
        if component_row is None:
            return None

        aliases = tuple(
            row["alias"]
            for row in self.conn.execute(
                """
                SELECT alias
                FROM component_aliases
                WHERE component_id=?
                ORDER BY alias COLLATE NOCASE
                """,
                (summary.component_id,),
            )
        )
        procedures = tuple(
            _procedure_from_row(row)
            for row in procedure_details(self.conn, summary.component_id, procedure_type, procedure_limit)
        )
        counts = tuple(
            (row["procedure_type"], row["procedure_count"])
            for row in procedure_type_counts(self.conn, summary.component_id)
        )
        quality = ComponentQuality(
            is_generic=summary.is_generic,
            quality_weight=summary.quality_weight,
            average_confidence=summary.average_confidence,
            weighted_score=summary.weighted_score,
        )
        documents = tuple(_document_from_row(row) for row in document_rows)
        statistics = {
            "document_count": summary.document_count,
            "occurrence_count": summary.occurrence_count,
            "procedure_count": sum(count for _, count in counts),
        }
        return ComponentKnowledge(
            component=summary,
            aliases=aliases,
            quality=quality,
            documents=documents,
            procedures=procedures,
            procedure_counts=counts,
            statistics=statistics,
        )
