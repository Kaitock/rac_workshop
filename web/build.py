"""สร้าง web/index.html จาก template.html + engine.js + chunk ของเอกสารใน data/docs (ไม่เรียก API)

python -m web.build              # หน้าเว็บเปิดในเบราว์เซอร์ได้เลย
python -m web.build --fragment   # เฉพาะเนื้อหาหน้า สำหรับเผยแพร่เป็น artifact
"""
import json
import sys
from pathlib import Path

from rag.chunk import chunk_docs
from rag.retrieve import SYNONYMS

WEB = Path(__file__).resolve().parent
KEYS = ["chunk_id", "doc_id", "title", "department", "version", "effective_date", "status", "section", "text"]
NODE_EXPORT = "if (typeof module !== 'undefined') module.exports = { createEngine: createEngine };\n"
HEAD = '<!doctype html>\n<html lang="th">\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'


def to_js(obj) -> str:
    """JSON ที่ฝังใน <script> ได้ปลอดภัย"""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def build(fragment: bool = False) -> str:
    chunks = [{k: c[k] for k in KEYS} for c in chunk_docs()]
    engine = (WEB / "engine.js").read_text(encoding="utf-8").replace(NODE_EXPORT, "")
    page = (WEB / "template.html").read_text(encoding="utf-8")
    page = page.replace("/*__CHUNKS__*/", to_js(chunks)).replace("/*__SYNONYMS__*/", to_js(SYNONYMS)).replace("/*__ENGINE__*/", engine)
    assert "/*__" not in page, "template มีตัวแทนที่ยังไม่ถูกแทนค่า"
    return page if fragment else HEAD + page + "\n</html>\n"


if __name__ == "__main__":
    out = WEB / "index.html"
    out.write_text(build("--fragment" in sys.argv), encoding="utf-8")
    print(out.relative_to(WEB.parent), out.stat().st_size, "bytes")
