"""แบ่งเอกสารเป็น chunk พร้อม metadata (เวิร์กช็อป 1)

แต่ละ chunk เป็น dict ที่มีอย่างน้อย:
chunk_id ("<doc_id>#<ลำดับ>"), doc_id, title, section, status, effective_date, text
"""
from rag.ingest import load_docs

MAX_CHARS = 600


def split_sections(body: str) -> list[tuple[str, str]]:
    """แยกเนื้อหาเป็น (หัวข้อ ##, ข้อความ) ข้อความก่อน ## แรกที่ไม่ใช่หัวเรื่อง # ใช้หัวข้อว่าง"""
    sections, section, lines = [], "", []
    for line in body.splitlines():
        if line.startswith("## "):
            sections.append((section, "\n".join(lines).strip()))
            section, lines = line[3:].strip(), []
        elif not line.startswith("# "):
            lines.append(line)
    sections.append((section, "\n".join(lines).strip()))
    return [(s, t) for s, t in sections if t]


def split_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """ตัดข้อความยาวตามบรรทัดให้แต่ละส่วนไม่เกิน max_chars บรรทัดที่ยาวเกินเองถูกตัดตามจำนวนตัวอักษร"""
    pieces, buf = [], ""
    for line in text.splitlines():
        while len(line) > max_chars:
            if buf:
                pieces.append(buf)
                buf = ""
            pieces.append(line[:max_chars])
            line = line[max_chars:]
        if buf and len(buf) + 1 + len(line) > max_chars:
            pieces.append(buf)
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf.strip():
        pieces.append(buf)
    return [p.strip() for p in pieces if p.strip()]


def chunk_docs(docs: list[dict] | None = None, max_chars: int = MAX_CHARS) -> list[dict]:
    """หนึ่งหัวข้อ ## ต่อหนึ่ง chunk (หัวข้อที่ยาวเกิน max_chars แบ่งเป็นหลาย chunk) ทุก chunk มี metadata ของเอกสาร"""
    chunks = []
    for doc in load_docs() if docs is None else docs:
        meta = {k: v for k, v in doc.items() if k != "body"}
        n = 0
        for section, text in split_sections(doc["body"]):
            for piece in split_text(text, max_chars):
                n += 1
                chunks.append({**meta, "chunk_id": f"{doc['doc_id']}#{n}", "section": section or doc["title"], "text": piece})
    return chunks


if __name__ == "__main__":
    cs = chunk_docs()
    print(len(cs), "chunks · ยาวสุด", max(len(c["text"]) for c in cs), "ตัวอักษร")
