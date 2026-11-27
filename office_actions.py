"""Create and validate plain Office documents in a single project directory."""
import hashlib
import math
import os
import re
import tempfile
from pathlib import Path, PureWindowsPath


def target(folder, name, suffix):
    if not isinstance(name, str) or not re.fullmatch(r"[\w -][\w .-]{0,115}", name) or name.endswith((" ", ".")):
        raise ValueError("El nombre debe ser un archivo simple del proyecto.")
    if not Path(name).suffix:
        name += suffix
    if Path(name).suffix.lower() != suffix or PureWindowsPath(name).is_reserved():
        raise ValueError("Nombre o extensión no admitidos.")
    path = Path(folder).resolve() / name
    if path.is_symlink() or path.resolve().parent != Path(folder).resolve():
        raise ValueError("Ruta no admitida.")
    return path


def publish(path, write, verify):
    if path.exists():
        raise FileExistsError("Ya existe ese archivo. Elegí otro nombre.")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".jarvis-", suffix=path.suffix, delete=False) as handle:
        staging = Path(handle.name)
    try:
        write(staging)
        verify(staging)
        digest = hashlib.sha256(staging.read_bytes()).hexdigest()
        if os.name == "nt":
            os.rename(staging, path)  # Windows refuses to replace an existing destination.
        else:
            os.link(staging, path)
        return {"path": path.name, "bytes": path.stat().st_size, "sha256": digest}
    finally:
        staging.unlink(missing_ok=True)


def create_spreadsheet(folder, filename, headers, rows):
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font
    if not isinstance(headers, list) or not 1 <= len(headers) <= 64 or not all(isinstance(v, str) and 0 < len(v) <= 256 for v in headers):
        raise ValueError("Indicá entre 1 y 64 encabezados de texto.")
    if not isinstance(rows, list) or len(rows) > 2000:
        raise ValueError("Se admiten hasta 2000 filas.")
    if any(not isinstance(row, list) or len(row) != len(headers) for row in rows):
        raise ValueError("Cada fila debe coincidir con los encabezados.")
    values = [headers, *rows]
    for row in rows:
        for v in row:
            if not (v is None or isinstance(v, str) and len(v) <= 4096 or type(v) is bool or type(v) in (int, float) and math.isfinite(v) and abs(v) <= 1e15):
                raise ValueError("Valor de celda no admitido.")
    book = Workbook()
    sheet = book.active
    sheet.title = "Datos"
    for i, row in enumerate(values, 1):
        for j, value in enumerate(row, 1):
            cell = sheet.cell(i, j, value)
            if isinstance(value, str):
                cell.data_type = "s"
            if i == 1:
                cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    def verify(path):
        loaded = load_workbook(path, read_only=True)
        try:
            expected = [tuple(None if v == "" else v for v in row) for row in values]
            if list(loaded.active.iter_rows(min_row=1, max_row=len(values), max_col=len(headers), values_only=True)) != expected:
                raise ValueError("Los datos reabiertos difieren del pedido.")
        finally:
            loaded.close()
    return publish(target(folder, filename, ".xlsx"), book.save, verify)


def create_document(folder, filename, title, paragraphs):
    from docx import Document
    if not isinstance(title, str) or not 1 <= len(title) <= 250 or not isinstance(paragraphs, list) or len(paragraphs) > 500 or not all(isinstance(p, str) and len(p) <= 12000 for p in paragraphs):
        raise ValueError("Revisá el título y los párrafos del documento.")
    doc = Document()
    doc.add_heading(title, 0)
    for content in paragraphs:
        doc.add_paragraph(content)
    def verify(path):
        if [p.text for p in Document(path).paragraphs] != [title, *paragraphs]:
            raise ValueError("Los párrafos reabiertos difieren del pedido.")
    return publish(target(folder, filename, ".docx"), doc.save, verify)
