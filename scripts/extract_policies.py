"""One-off: extract the store policy PDF into a markdown draft for manual review.

Usage: python scripts/extract_policies.py [--force]
Output: knowledge/policies.md. Review it by hand afterwards (D3).
The reviewed file is the source of truth: the script refuses to overwrite it without --force.
"""

import re
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "data" / "políticas_da_loja.pdf"
OUT = ROOT / "knowledge" / "policies.md"
PAGE_HEADER = "Empório da Música Manual de Políticas e Procedimentos"


def to_markdown(line: str) -> str:
    if re.match(r"^\d+\.\d+ \S", line):  # "3.1 Regras de Parcelamento"
        return f"### {line}"
    if re.match(r"^\d+\. [A-ZÀ-Ú]", line):  # "3. Formas de Pagamento"
        return f"## {line}"
    if line.startswith("• "):
        return f"- {line[2:]}"
    return line


def main() -> None:
    if OUT.exists() and "--force" not in sys.argv:
        sys.exit(f"{OUT.relative_to(ROOT)} exists and was reviewed by hand; use --force to overwrite it")
    lines = []
    with pdfplumber.open(PDF) as pdf:
        for page in pdf.pages[1:]:  # page 1 is the cover
            for line in (page.extract_text() or "").splitlines():
                line = line.strip()
                if line and line != PAGE_HEADER and not re.match(r"^Página \d+$", line):
                    lines.append(to_markdown(line))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
