"""พิมพ์คำถามประเมินเฉพาะ qid และ question ไม่แสดงคอลัมน์เฉลย (ใช้ใน skill /ask-eval)

python -m rag.questions dev 10   # ไม่ระบุจำนวนข้อ = ทุกข้อ
"""
import csv
import sys

from rag.evaluate import QUESTIONS


def main(split: str = "dev", n: int = 0):
    with open(QUESTIONS, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["split"] == split]
    for r in rows[:n] if n else rows:
        print(r["qid"], r["question"], sep="\t")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dev", int(sys.argv[2]) if len(sys.argv) > 2 else 0)
