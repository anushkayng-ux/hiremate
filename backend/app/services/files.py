"""Generate downloadable .docx files (e.g. a JD written by Asha)."""
from __future__ import annotations

import re
from pathlib import Path

import docx
from docx.shared import Pt, RGBColor

from .. import db
from ..config import FILES_DIR


def make_docx(title: str, text: str) -> dict:
    d = docx.Document()
    st = d.styles["Normal"]
    st.font.name = "Arial"
    st.font.size = Pt(11)
    h = d.add_heading(title, level=1)
    for r in h.runs:
        r.font.color.rgb = RGBColor(0x2F, 0x4A, 0x3A)
    for line in text.splitlines():
        line = line.rstrip()
        if not line or line.strip() == title.strip():
            continue
        if re.match(r"^[-•*]\s+", line):
            d.add_paragraph(re.sub(r"^[-•*]\s+", "", line), style="List Bullet")
        elif re.match(r"^[A-Za-z /&-]{2,40}:\s*$", line):
            d.add_heading(line.rstrip(":"), level=2)
        elif re.match(r"^[A-Za-z /&-]{2,30}:\s+\S", line):
            k, v = line.split(":", 1)
            p = d.add_paragraph()
            p.add_run(k + ": ").bold = True
            p.add_run(v.strip())
        else:
            d.add_paragraph(line)
    safe = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")[:50] or "document"
    fid = db.run("INSERT INTO generated_files(name,path,mime,created_at) VALUES(?,?,?,?)",
                 (f"{safe}.docx", "", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", db.now()))
    path = FILES_DIR / f"{fid}_{safe}.docx"
    d.save(path)
    db.run("UPDATE generated_files SET path=? WHERE id=?", (str(path), fid))
    return {"id": fid, "name": f"{safe}.docx"}


def get_file(fid: int) -> dict | None:
    f = db.one("SELECT * FROM generated_files WHERE id=?", (fid,))
    if f and Path(f["path"]).exists():
        return f
    return None
