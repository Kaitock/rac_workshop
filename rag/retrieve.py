"""ค้นคืน chunk ที่เกี่ยวข้องกับคำถาม (เวิร์กช็อป 2 และ 4) ทำงานในเครื่องทั้งหมด ไม่เรียก API

python -m rag.retrieve "คำถาม" -k 4 [--method tfidf|hybrid] [--include-superseded] [--json]
"""
import argparse
import json
import re

import numpy as np
from pythainlp.tokenize import word_tokenize
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from rag.chunk import chunk_docs

# น้ำหนักของ TF-IDF ตัวอักษรในคะแนน hybrid ส่วนที่เหลือเป็นของ BM25
HYBRID_WEIGHT = 0.5

# คำพ้องสำหรับขยายคำค้น: คำที่ผู้ใช้พิมพ์ → คำที่เอกสารบริษัทใช้
# ได้มาจากคำถามชุด dev ที่ค้นพลาดเท่านั้น
SYNONYMS: dict[str, str] = {
    "พาสเวิร์ด": "รหัสผ่าน",
    "อีวี": "รถยนต์ไฟฟ้า",
    "เสียบชาร์จ": "จุดชาร์จ",
}


def index_text(c: dict) -> str:
    """ข้อความที่ใช้ทำดัชนี: ชื่อเอกสาร + หัวข้อ + เนื้อหา"""
    return f"{c['title']}\n{c['section']}\n{c['text']}"


def tokenize(text: str) -> list[str]:
    """ตัดคำภาษาไทยด้วย pythainlp (newmm) ตัดช่องว่างและเครื่องหมายออก"""
    return [t for t in word_tokenize(text.lower(), engine="newmm", keep_whitespace=False) if re.search(r"\w", t)]


def expand_query(query: str) -> str:
    """ต่อท้ายคำค้นด้วยคำพ้องที่ตรงกับคำในคำถาม"""
    extra = [v for k, v in SYNONYMS.items() if k in query.lower()]
    return " ".join([query, *extra])


def normalize(scores: np.ndarray) -> np.ndarray:
    """ปรับให้คะแนนสูงสุดเป็น 1 เพื่อรวมคะแนนต่างสเกลกันได้"""
    top = scores.max()
    return scores / top if top > 0 else scores


class Retriever:
    def __init__(self, chunks: list[dict] | None = None, method: str = "tfidf"):
        """method="tfidf": TF-IDF ระดับตัวอักษร (W2) · method="hybrid": วิธีที่ปรับปรุงแล้ว (W4)"""
        if method not in {"tfidf", "hybrid"}:
            raise ValueError(f"ไม่รู้จัก method: {method}")
        self.method = method
        self.chunks = chunk_docs() if chunks is None else chunks
        texts = [index_text(c) for c in self.chunks]
        # ภาษาไทยไม่เว้นวรรคระหว่างคำ จึงใช้ n-gram ระดับตัวอักษรแทนการตัดคำ
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        self.matrix = self.vectorizer.fit_transform(texts)
        self.active = np.array([c["status"] == "active" for c in self.chunks])
        if method == "hybrid":
            self.bm25 = BM25Okapi([tokenize(t) for t in texts])

    def search(self, query: str, k: int = 4, include_superseded: bool = True) -> list[dict]:
        """คืน chunk k อันที่คะแนนสูงสุด เรียงจากมากไปน้อย แต่ละอันเพิ่มช่อง "score" """
        if self.method == "hybrid":
            query = expand_query(query)
        scores = cosine_similarity(self.vectorizer.transform([query]), self.matrix).ravel()
        if self.method == "hybrid":
            bm25 = self.bm25.get_scores(tokenize(query))
            scores = HYBRID_WEIGHT * normalize(scores) + (1 - HYBRID_WEIGHT) * normalize(bm25)
        idx = np.argsort(-scores, kind="stable")
        if not include_superseded:
            idx = idx[self.active[idx]]
        return [{**self.chunks[i], "score": float(scores[i])} for i in idx[:k]]


def main():
    ap = argparse.ArgumentParser(description="ค้นคืน chunk จากเอกสารบริษัท")
    ap.add_argument("query")
    ap.add_argument("-k", type=int, default=4)
    ap.add_argument("--method", default="hybrid", choices=["tfidf", "hybrid"])
    ap.add_argument("--include-superseded", action="store_true", help="แสดงฉบับที่ถูกแทนที่แล้วด้วย (ค่าเริ่มต้นกรองออก)")
    ap.add_argument("--json", action="store_true", help="พิมพ์ผลเป็น JSON")
    a = ap.parse_args()
    res = Retriever(method=a.method).search(a.query, k=a.k, include_superseded=a.include_superseded)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    for i, r in enumerate(res, 1):
        print(f"{i}. [{r['chunk_id']}] {r['score']:.3f} · {r['title']} › {r['section']} ({r['status']}, {r['effective_date']})")
        print("   " + r["text"].replace("\n", "\n   "))


if __name__ == "__main__":
    main()
