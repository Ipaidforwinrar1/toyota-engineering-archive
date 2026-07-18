from dataclasses import dataclass
import re

PROCEDURE_TYPES = (
    "REMOVAL",
    "INSTALLATION",
    "DISASSEMBLY",
    "REASSEMBLY",
    "INSPECTION",
    "ADJUSTMENT",
    "REPLACEMENT",
)

TITLE_TYPES = {t.title() for t in PROCEDURE_TYPES}
HEADING_RE = re.compile(
    rf"^\s*(?:[A-Z]{{1,4}}\d{{0,4}}[-\s]*)?({'|'.join(PROCEDURE_TYPES)})\s*$"
)
STEP_RE = re.compile(r"(?:^|\s)(?:\d{1,2}[\.\)]|\([a-z]\))\s+(?=[A-Z])")


@dataclass(frozen=True)
class ProcedureBlock:
    procedure_type: str
    title: str
    context: str
    step_count: int


def clean_text(value):
    return " ".join((value or "").split())


def count_steps(text):
    return len(STEP_RE.findall(text or ""))


def find_heading_blocks(text):
    lines = (text or "").splitlines()
    matches = []
    offset = 0
    for line in lines:
        match = HEADING_RE.match(line.strip())
        if match:
            matches.append((offset, match.group(1).title()))
        offset += len(line) + 1

    blocks = []
    for index, (start, procedure_type) in enumerate(matches):
        end = matches[index + 1][0] if index + 1 < len(matches) else len(text or "")
        context = clean_text((text or "")[start:end])
        if context:
            blocks.append((procedure_type, context))
    return blocks


def extract_procedure_blocks(text, document_title="", section_path="", max_chars=4000):
    title = clean_text(document_title)
    blocks = find_heading_blocks(text)

    if not blocks and title.upper() in PROCEDURE_TYPES:
        blocks = [(title.title(), clean_text(text))]

    result = []
    for procedure_type, context in blocks:
        if not context:
            continue
        if len(context) > max_chars:
            context = context[:max_chars].rsplit(" ", 1)[0]
        display_title = title or procedure_type
        if section_path:
            display_title = f"{display_title} - {clean_text(section_path)}"
        result.append(
            ProcedureBlock(
                procedure_type=procedure_type,
                title=display_title,
                context=context,
                step_count=count_steps(context),
            )
        )
    return result
