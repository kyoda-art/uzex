"""Terminalda botni sinash: python cli.py  (Telegram talab qilinmaydi)."""
import logging
import time

from core.data import load
from core.router import answer, make_llm

logging.basicConfig(level=logging.WARNING)

if __name__ == "__main__":
    t = time.time()
    ds = load()
    llm = make_llm()
    print(f"Ma'lumot yuklandi ({time.time() - t:.1f}s). Gemini: {'ulangan' if llm else 'yo‘q (qoidalar rejimi)'}")
    print("Savol yozing (chiqish: exit)\n")
    while True:
        try:
            q = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() == "exit":
            break
        print(answer(ds, q, llm), "\n")
