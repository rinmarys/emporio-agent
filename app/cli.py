"""Minimal terminal chat for quick tests and as the interface plan B (D5).

Run: py -m app.cli   (use Windows Terminal: the old console breaks accents)
"""

import logging
import sys
import uuid

from app.agent import ask

EXIT_WORDS = {"sair", "exit", "quit"}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    # Errors go to a file, so the customer never sees a traceback in the chat.
    logging.basicConfig(filename="emporio.log", level=logging.INFO, encoding="utf-8")
    thread_id = f"cli-{uuid.uuid4()}"  # new conversation memory on every run (D6)
    print("Empório da Música 🎸 — digite sua mensagem (ou 'sair' para encerrar)\n")
    while True:
        try:
            message = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if message.lower() in EXIT_WORDS:
            break
        if message:
            print(f"\nEmpório: {ask(message, thread_id)}\n")
    print("\nAté mais! 🎶")


if __name__ == "__main__":
    main()
