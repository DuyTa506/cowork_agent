from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator

@dataclass
class Block:
    kind: str  # para | list_item | table
    text: str
    pi: int = -1  # index of the first source paragraph (doccheck DocModel.Para.pi)

@dataclass
class Section:
    kind: str  # root | phan | chuong | muc | dieu | roman | upper | number | decimal | letter
    marker: str = ""
    heading: str = ""
    pi: int = -1
    blocks: list[Block] = field(default_factory=list)
    children: list["Section"] = field(default_factory=list)

    def walk(self) -> Iterator["Section"]:
        yield self
        for child in self.children:
            yield from child.walk()

    def own_text(self) -> str:
        return "\n".join(b.text for b in self.blocks)

    def full_text(self) -> str:
        parts = [self.heading] if self.heading else []
        parts += [b.text for b in self.blocks]
        parts += [c.full_text() for c in self.children]
        return "\n".join(p for p in parts if p)

@dataclass
class Metadata:
    doc_type: str = ""
    doc_type_code: str = ""
    number: str = ""
    symbol: str = ""
    place: str = ""
    date_text: str = ""
    date: str = ""  # ISO yyyy-mm-dd, empty when the day/month is blank (drafts)
    date_partial: str = ""  # "2026-01" or "2026" when the printed date has blanks (a draft): what is known of it
    parent_agency: str = ""
    issuing_agency: str = ""
    title: str = ""
    subject: str = ""  # trích yếu as printed: "V/v ..." of a công văn, the lines under the type name of the others
    recipients_to: list[str] = field(default_factory=list)
    legal_bases: list[str] = field(default_factory=list)
    distribution: list[str] = field(default_factory=list)
    signer_role: str = ""
    signer_name: str = ""  # rank and name as printed under the signature: "Đại tá Nguyễn Ngọc Yên"
    signer_lines: list[str] = field(default_factory=list)  # the title lines above the name, one per printed line
    signer_rank: str = ""  # cấp bậc taken out of `signer_name`: "Đại tá"
    signer: str = ""  # what is shown to people: "Phó Tham mưu trưởng, Đại tá, Nguyễn Ngọc Yên" (parts that are unknown are left out)
    stamped: bool = False  # a seal or signature image sits on the first or last page (the number/date/signer are then expected to exist)
    is_draft: bool = False
    classification: str = ""  # "" | mat | toi_mat | tuyet_mat: the secrecy stamp printed on the document

@dataclass
class ParsedDocument:
    path: str
    format: str
    metadata: Metadata
    root: Section
    footer: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    page_count_hint: int | None = None
    ocr: bool = False  # the text comes from OCR of a scan, so it may contain recognition errors

    def text(self) -> str:
        return self.root.full_text()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
