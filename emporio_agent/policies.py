"""Lookup of sections of the store policy manual."""
import re
from pathlib import Path

from pypdf import PdfReader

from emporio_agent.config import POLICIES_PDF

# Matched against whole lines: the manual also has numbered lists ("1. Saudação: ...").
SECTION_TITLES = {
    "1. Sobre a Empório da Música": "about",
    "2. Horário de Funcionamento": "hours",
    "3. Formas de Pagamento": "payment",
    "4. Política de Trocas e Devoluções": "returns",
    "5. Política de Frete e Entregas": "shipping",
    "6. Promoções e Descontos": "promotions",
    "7. Atendimento via WhatsApp": "customer_service",
    "8. Garantia": "warranty",
    "9. Privacidade e Proteção de Dados": "privacy",
    "10. Disposições Finais": None,
}
PAGE_HEADER = "Empório da Música Manual de Políticas e Procedimentos"
PAGE_FOOTER = re.compile(r"^Página \d+$")


def _clean_line(line: str) -> str:
    line = re.sub(r"^•\s+", "- ", line.strip())
    line = re.sub(r"^(\d+\.)\s+", r"\1 ", line)
    return re.sub(r" {2,}", " | ", line)


def _is_page_furniture(line: str) -> bool:
    return line == PAGE_HEADER or bool(PAGE_FOOTER.match(line))


class PolicyManual:
    def __init__(self, path: Path = POLICIES_PDF) -> None:
        # The default extraction mode returns one word per line for this PDF.
        pages = [page.extract_text(extraction_mode="layout") for page in PdfReader(path).pages]
        self._sections = self._split_sections("\n".join(pages))

    @staticmethod
    def _split_sections(text: str) -> dict[str, str]:
        sections: dict[str, list[str]] = {}
        current: list[str] | None = None
        for raw_line in text.splitlines():
            line = _clean_line(raw_line)
            if not line or _is_page_furniture(line):
                continue
            if line in SECTION_TITLES:
                topic = SECTION_TITLES[line]
                current = sections.setdefault(topic, [line]) if topic else None
            elif current is not None:
                current.append(line)
        return {topic: "\n".join(lines) for topic, lines in sections.items()}

    @property
    def topics(self) -> list[str]:
        return list(self._sections)

    def section(self, topic: str) -> str | None:
        return self._sections.get(topic)
