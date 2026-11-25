import os
import tempfile
from typing import Callable, TypeVar

from fastapi import HTTPException, UploadFile

from ..importers import ResultadoB1, ResultadoEspecificaciones, parse_b1, parse_especificaciones
from ..importers.biblioteca_excel import ResultadoBiblioteca, leer_biblioteca_excel

TAMANO_MAXIMO_MB = 25
T = TypeVar("T")


def _leer_pdf_subido(archivo: UploadFile, lector: Callable[[str], T]) -> T:
    """Valida el PDF subido y lo procesa con el lector indicado."""
    if not (archivo.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF.")
    limite = TAMANO_MAXIMO_MB * 1024 * 1024
    contenido = archivo.file.read(limite + 1)
    if len(contenido) > limite:
        raise HTTPException(status_code=413, detail=f"El PDF supera {TAMANO_MAXIMO_MB} MB.")

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)  # compatible con Windows
    try:
        tmp.write(contenido)
        tmp.close()
        return lector(tmp.name)
    except Exception as exc:  # PDF dañado, protegido, etc.
        raise HTTPException(status_code=422, detail=f"No se pudo leer el PDF: {exc}") from exc
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def leer_b1_subido(archivo: UploadFile) -> ResultadoB1:
    resultado = _leer_pdf_subido(archivo, parse_b1)
    if resultado.total_items == 0:
        raise HTTPException(status_code=422, detail="No se encontraron ítems. ¿Es el PDF del Formulario B-1?")
    return resultado


def leer_especificaciones_subidas(archivo: UploadFile) -> ResultadoEspecificaciones:
    resultado = _leer_pdf_subido(archivo, parse_especificaciones)
    if not resultado.items:
        raise HTTPException(
            status_code=422,
            detail="No se encontraron ítems con especificación. ¿Es el PDF de especificaciones técnicas?",
        )
    return resultado


def leer_biblioteca_subida(archivo: UploadFile) -> ResultadoBiblioteca:
    if not (archivo.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="El archivo debe ser un Excel .xlsx (si es .xls, guárdalo como .xlsx).")
    limite = TAMANO_MAXIMO_MB * 1024 * 1024
    contenido = archivo.file.read(limite + 1)
    if len(contenido) > limite:
        raise HTTPException(status_code=413, detail=f"El archivo supera {TAMANO_MAXIMO_MB} MB.")
    try:
        resultado = leer_biblioteca_excel(contenido)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"No se pudo leer el Excel: {exc}") from exc
    if not resultado.apus:
        primero = resultado.alertas[0].mensaje if resultado.alertas else "No se encontraron APU."
        raise HTTPException(status_code=422, detail=primero)
    return resultado
