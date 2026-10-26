"""One page image in, its text out, against an OpenAI-compatible chat server."""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any

import httpx


class OcrServerError(RuntimeError):
    """The OCR server did not give a usable answer."""


# Grounding mode writes each block of the page behind a label and its box: "![title]<c77><c62><c328><c88> BỘ QUỐC PHÒNG" (the model's own
# token form) or "![title](77,62,328,88)" (LightOnOCR's). Pictures carry a description of the picture, not text of the document.
_BLOCK = re.compile(r"!\[([a-z_]+)(\+?)\]((?:<c\d+>){4})|!\[([a-z_]+)(\+?)\]\((\d+),(\d+),(\d+),(\d+)\)")
_PICTURES = {"image", "chart", "header_image", "footer_image"}


@dataclass(frozen=True)
class Block:
    """One block of a page as the model read it: its label, its box (x0, y0, x1, y1 on a 0-1000 scale of the page) and its text."""

    label: str
    box: tuple[int, int, int, int]
    text: str

    def as_dict(self) -> dict[str, Any]:
        return {"label": self.label, "box": list(self.box), "text": self.text}


def parse_blocks(raw: str) -> list[Block]:
    """The blocks of a grounding-mode answer, in reading order. Pictures are kept (their text is the model's description of them).
    A "text+" block goes on from the block before it and is merged into it (the box grows to cover both)."""
    marks = list(_BLOCK.finditer(raw))
    blocks: list[Block] = []
    for number, mark in enumerate(marks):
        if mark.group(1):
            label, continued = mark.group(1), mark.group(2)
            box = tuple(int(n) for n in re.findall(r"\d+", mark.group(3)))
        else:
            label, continued = mark.group(4), mark.group(5)
            box = tuple(int(mark.group(k)) for k in range(6, 10))
        end = marks[number + 1].start() if number + 1 < len(marks) else len(raw)
        body = raw[mark.end():end].strip()
        if not body:
            continue
        if continued and blocks:
            before = blocks[-1]
            merged = (min(before.box[0], box[0]), min(before.box[1], box[1]), max(before.box[2], box[2]), max(before.box[3], box[3]))
            blocks[-1] = Block(before.label, merged, before.text + " " + body)
        else:
            blocks.append(Block(label, box, body))  # type: ignore[arg-type]
    return blocks


def blocks_to_text(raw: str) -> str:
    """Text of a grounding-mode answer: one paragraph per block, in reading order, pictures left out. Anything that is not in
    grounding format (a server that ignores the prompt) is returned as it is."""
    blocks = parse_blocks(raw)
    if not blocks:
        return raw.strip()
    return "\n\n".join(b.text for b in blocks if b.label not in _PICTURES)


class OcrClient:
    """Sends each page alone, greedy, the way the model was trained and benchmarked.

    In grounding mode (the default) the page comes with the prompt "grounding": the model then reads it block by block (title, text,
    table...), which keeps the header lines of a Vietnamese document apart instead of running them into one paragraph.

    Args:
        values: The ``ocr`` settings section (base_url, model, api_key, grounding).
    """

    def __init__(self, values: dict[str, Any], timeout: float = 600.0, max_tokens: int = 4096):
        self.model, self.max_tokens = values["model"], max_tokens
        self.grounding = bool(values.get("grounding", True))
        headers = {"Authorization": f"Bearer {values['api_key']}"} if values.get("api_key") else {}
        self._client = httpx.Client(base_url=values["base_url"], timeout=timeout, headers=headers)

    def read(self, png: bytes) -> str:
        """The page's text (Markdown as the model writes it); see `read_page` for the blocks with their positions."""
        return self.read_page(png)[0]

    def read_page(self, png: bytes) -> tuple[str, list[Block]]:
        """The page's text and, in grounding mode, its blocks with their boxes.

        Raises:
            OcrServerError: transport failure, error status, empty answer.
        """
        url = "data:image/png;base64," + base64.b64encode(png).decode()
        content: list[dict[str, Any]] = [{"type": "image_url", "image_url": {"url": url}}]
        if self.grounding:
            content.append({"type": "text", "text": "grounding"})
        body = {"model": self.model, "temperature": 0, "max_tokens": self.max_tokens,
                "messages": [{"role": "user", "content": content}],
                "chat_template_kwargs": {"enable_thinking": False}}
        try:
            response = self._client.post("/chat/completions", json=body)
            if response.status_code == 400:  # a server that rejects the extra option
                body.pop("chat_template_kwargs")
                response = self._client.post("/chat/completions", json=body)
            response.raise_for_status()
            text = (response.json()["choices"][0]["message"].get("content") or "").strip()
            if not self.grounding:
                return text, []
            blocks = parse_blocks(text)
            return (blocks_to_text(text), blocks) if blocks else (text, [])
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise OcrServerError(f"Không gọi được máy chủ OCR: {type(exc).__name__}") from exc

    def close(self) -> None:
        self._client.close()
