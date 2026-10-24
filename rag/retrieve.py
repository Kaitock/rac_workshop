"""ค้นคืน chunk ที่เกี่ยวข้องกับคำถาม (เวิร์กช็อป 2 และ 4) ทำงานในเครื่องทั้งหมด ไม่เรียก API

python -m rag.retrieve "คำถาม" -k 4 [--method tfidf|hybrid] [--include-superseded] [--json]
"""
import argparse
import json

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from rag.chunk import chunk_docs


def index_text(c: dict) -> str:
    """ข้อความที่ใช้ทำดัชนี: ชื่อเอกสาร + หัวข้อ + เนื้อหา"""
    return f"{c['title']}\n{c['section']}\n{c['text']}"


class Retriever:
    def __init__(self, chunks: list[dict] | None = None, method: str = "tfidf"):
        """method="tfidf": TF-IDF ระดับตัวอักษร (W2) · method="hybrid": วิธีที่ปรับปรุงแล้ว (W4)"""
        if method == "hybrid":
            raise NotImplementedError("เพิ่ม method hybrid ใน W4")
        if method != "tfidf":
            raise ValueError(f"ไม่รู้จัก method: {method}")
        self.method = method
        self.chunks = chunk_docs() if chunks is None else chunks
        # ภาษาไทยไม่เว้นวรรคระหว่างคำ จึงใช้ n-gram ระดับตัวอักษรแทนการตัดคำ
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        self.matrix = self.vectorizer.fit_transform([index_text(c) for c in self.chunks])
        self.active = np.array([c["status"] == "active" for c in self.chunks])

    def search(self, query: str, k: int = 4, include_superseded: bool = True) -> list[dict]:
        """คืน chunk k อันที่คะแนนสูงสุด เรียงจากมากไปน้อย แต่ละอันเพิ่มช่อง "score" """
        scores = cosine_similarity(self.vectorizer.transform([query]), self.matrix).ravel()
        idx = np.argsort(-scores, kind="stable")
        if not include_superseded:
            idx = idx[self.active[idx]]
        return [{**self.chunks[i], "score": float(scores[i])} for i in idx[:k]]


def main():
    ap = argparse.ArgumentParser(description="ค้นคืน chunk จากเอกสารบริษัท")
    ap.add_argument("query")
    ap.add_argument("-k", type=int, default=4)
    ap.add_argument("--method", default="tfidf", choices=["tfidf", "hybrid"])
    ap.add_argument("--include-superseded", action="store_true")
    ap.add_argument("--json", action="store_true", help="พิมพ์ผลเป็น JSON")
    a = ap.parse_args()
    # baseline tfidf แสดงฉบับ superseded ด้วยเสมอ (เหมือน rag.evaluate) เพื่อให้เห็นปัญหาเรื่องเวอร์ชัน
    inc = a.include_superseded or a.method == "tfidf"
    res = Retriever(method=a.method).search(a.query, k=a.k, include_superseded=inc)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    for i, r in enumerate(res, 1):
        print(f"{i}. [{r['chunk_id']}] {r['score']:.3f} · {r['title']} › {r['section']} ({r['status']}, {r['effective_date']})")
        print("   " + r["text"].replace("\n", "\n   "))


if __name__ == "__main__":
    main()
