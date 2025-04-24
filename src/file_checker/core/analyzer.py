from __future__ import annotations

"""file_checker.core.analyzer

Contiene la classe ``FileAnalyzer`` responsabile dell'analisi dei file (PDF, DOCX,
immagini) rispetto alle specifiche fornite dall'utente.

La logica è estratta dal vecchio script monolitico e resa autonoma da qualsiasi
interfaccia grafica, così da poter essere:
    • testata (pytest)
    • ri‑utilizzata da altre front‑end (CLI, API, GUI Qt)

Dipendenze esterne (da aggiungere a requirements.txt / pyproject.toml):
    pypdf               # oppure PyPDF2 (vedi commento sotto)
    python‑magic‑bin    # MIME detection cross‑platform
    python‑docx         # lettura DOCX
    Pillow              # gestione immagini

Nota su PyPDF:
    È preferibile usare ``pypdf`` (fork moderno di PyPDF2). Tuttavia la classe
    qui sotto importa prima ``pypdf`` e, in fallback, ``PyPDF2`` per
    compatibilità.
"""

from dataclasses import dataclass, field
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

try:
    from pypdf import PdfReader  # type: ignore
except ModuleNotFoundError:  # fallback
    from PyPDF2 import PdfReader  # type: ignore

import magic  # type: ignore
from PIL import Image
import docx  # type: ignore

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
try:
    # quando il pacchetto completo è installato
    from ..utils.logging_conf import logger  # type: ignore
except (ImportError, ValueError):
    # fallback in fase di sviluppo stand‑alone
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structure per l'esito dell'analisi
# ---------------------------------------------------------------------------


@dataclass
class AnalysisOutcome:
    """Risultato normalizzato di qualunque analisi file."""

    formato_file: str
    numero_pagine: Optional[int] = None
    dimensioni: Optional[str] = None
    spazio_colore: Optional[str] = None
    profilo_stampa: Optional[str] = None

    # Flag di validità (None = non applicabile)
    esito_pagine: Optional[bool] = None
    esito_formato: Optional[bool] = None
    esito_protezione: Optional[bool] = None
    esito_font_incorporati: Optional[bool] = None
    esito_pagine_singole: Optional[bool] = None
    esito_numerazione: Optional[bool] = None
    esito_stampa: Optional[bool] = None

    # In caso di errore
    esito: str = "OK"  # oppure "Errore"
    messaggio: str = ""

    # Extra libero, se servono dati aggiuntivi
    extra: Dict[str, Any] = field(default_factory=dict)

    # Convenienza: proprietà per capire se tutto è conforme
    @property
    def conforme(self) -> bool:
        for k, v in self.__dict__.items():
            if k.startswith("esito_") and v is False:
                return False
        return self.esito != "Errore"


# ---------------------------------------------------------------------------
# FileAnalyzer
# ---------------------------------------------------------------------------


class FileAnalyzer:
    """Analizza file PDF, Word o immagini in base alle specifiche di progetto."""

    #: Mapping MIME → funzione di analisi (riempito in __init__)
    _ANALIZZATORI: Dict[str, str] = {
        "application/pdf": "_analizza_pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "_analizza_word",
        "image/jpeg": "_analizza_immagine",
        "image/png": "_analizza_immagine",
        "image/tiff": "_analizza_immagine",
    }

    def __init__(self, specifiche: Dict[str, Dict[str, str]]):
        self.specifiche = specifiche  # es. {"impaginato": {...}, "copertina": {...}}
        self._risultati: Dict[str, AnalysisOutcome] = {}
        self._mime_detector = magic.Magic(mime=True)

    # ------------------------------------------------------------------
    # API pubblica
    # ------------------------------------------------------------------

    def analizza_file(self, percorso: str, tipo: str) -> AnalysisOutcome:
        """Analizza *percorso* che appartiene alla sezione *tipo* (impaginato/coper…)."""
        if not os.path.exists(percorso):
            outcome = AnalysisOutcome(
                formato_file="sconosciuto",
                esito="Errore",
                messaggio=f"File non trovato: {percorso}",
            )
            self._risultati[tipo] = outcome
            return outcome

        try:
            mime_type = self._mime_detector.from_file(percorso)
        except Exception as exc:  # pragma: no cover
            logger.error("Errore MIME detection: %s", exc)
            outcome = AnalysisOutcome(
                formato_file="sconosciuto",
                esito="Errore",
                messaggio=str(exc),
            )
            self._risultati[tipo] = outcome
            return outcome

        method_name = self._ANALIZZATORI.get(mime_type)
        if not method_name:
            outcome = AnalysisOutcome(
                formato_file=mime_type,
                esito="Errore",
                messaggio=f"Formato non supportato: {mime_type}",
            )
            self._risultati[tipo] = outcome
            return outcome

        # Chiama il metodo appropriato
        try:
            outcome: AnalysisOutcome = getattr(self, method_name)(percorso, tipo)
        except Exception as exc:  # pragma: no cover
            logger.exception("Errore nell'analisi di %s", percorso)
            outcome = AnalysisOutcome(
                formato_file=mime_type,
                esito="Errore",
                messaggio=str(exc),
            )

        self._risultati[tipo] = outcome
        return outcome

    def get_risultati(self) -> Dict[str, AnalysisOutcome]:
        """Ritorna i risultati di tutte le analisi svolte."""
        return self._risultati

    # ------------------------------------------------------------------
    # Analizzatori specifici
    # ------------------------------------------------------------------

    # ----- PDF -----

    def _analizza_pdf(self, percorso: str, tipo: str) -> AnalysisOutcome:
        reader: PdfReader
        with open(percorso, "rb") as fp:
            reader = PdfReader(fp)

        protezione_ok = not reader.is_encrypted
        fonts_ok = protezione_ok and self._check_all_fonts_incorporati(reader)
        num_pagine = len(reader.pages) if protezione_ok else 0

        # Dimensioni pagina → cm (2 decimali, , italiano)
        if tipo == "impaginato":
            dimensioni, pagine_singole = self._dimensioni_impaginato(reader)
            numerazione_ok = self._check_page_numbering_consecutive(reader) if protezione_ok else False
            stampa_bw, profilo_stampa = self._check_stampa_pdf(reader)
        else:  # copertina
            dimensioni = self._dimensioni_prima_pagina(reader)
            pagine_singole = True
            numerazione_ok = True
            stampa_bw, profilo_stampa = True, ""

        specs = self.specifiche.get(tipo, {})
        esito_formato = self._verifica_formato(dimensioni, specs.get("formato", "")) if protezione_ok else False
        esito_n_pagine = num_pagine == int(specs.get("pagine totali", 0)) if protezione_ok else False

        expected_stampa = specs.get("stampa", "").lower().strip()
        if expected_stampa == "bianco e nero":
            esito_stampa = stampa_bw
        elif expected_stampa == "colori":
            esito_stampa = not stampa_bw
        else:
            esito_stampa = True  # non specificato → ok

        return AnalysisOutcome(
            formato_file="PDF",
            numero_pagine=num_pagine,
            dimensioni=dimensioni,
            profilo_stampa=profilo_stampa,
            esito_pagine=esito_n_pagine,
            esito_formato=esito_formato,
            esito_protezione=protezione_ok,
            esito_font_incorporati=fonts_ok,
            esito_pagine_singole=pagine_singole,
            esito_numerazione=numerazione_ok,
            esito_stampa=esito_stampa,
        )

    # ----- Word -----

    def _analizza_word(self, percorso: str, tipo: str) -> AnalysisOutcome:
        # Tentativo con COM (solo Windows) → fallback a python‑docx
        num_pagine = 0
        try:
            import win32com.client  # type: ignore
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            doc = word.Documents.Open(percorso)
            num_pagine = doc.ComputeStatistics(2)  # 2 = wdStatisticPages
            doc.Close(False)
            word.Quit()
        except Exception:
            document = docx.Document(percorso)
            num_pagine = len(document.paragraphs)

        specs = self.specifiche.get(tipo, {})
        esito_n_pagine = num_pagine == int(specs.get("pagine totali", 0))

        return AnalysisOutcome(
            formato_file="WORD",
            numero_pagine=num_pagine,
            esito_pagine=esito_n_pagine,
        )

    # ----- Immagine -----

    def _analizza_immagine(self, percorso: str, tipo: str) -> AnalysisOutcome:
        with Image.open(percorso) as img:
            larg_cm, alt_cm = img.width / 118.11, img.height / 118.11  # px → cm (300 dpi)
            dimensioni = f"{larg_cm:.1f}x{alt_cm:.1f} cm".replace(".", ",")
            spazio_colore = {"RGB": "RGB", "CMYK": "CMYK", "L": "Scala di Grigi"}.get(img.mode, "Sconosciuto")

        specs = self.specifiche.get(tipo, {})
        esito_formato = self._verifica_formato(dimensioni, specs.get("formato", ""))

        return AnalysisOutcome(
            formato_file=img.format or "IMG",
            dimensioni=dimensioni,
            spazio_colore=spazio_colore,
            esito_formato=esito_formato,
        )

    # ------------------------------------------------------------------
    # Helper interni
    # ------------------------------------------------------------------

    # ---------- PDF helpers ----------

    def _check_all_fonts_incorporati(self, reader: PdfReader) -> bool:
        try:
            for page in reader.pages:
                resources = page.get("/Resources") or {}
                if hasattr(resources, "get_object"):
                    resources = resources.get_object()
                fonts = resources.get("/Font") or {}
                if hasattr(fonts, "get_object"):
                    fonts = fonts.get_object()
                for font_key in fonts:
                    font = fonts[font_key].get_object() if hasattr(fonts[font_key], "get_object") else fonts[font_key]
                    descriptor = font.get("/FontDescriptor")
                    if not descriptor:
                        return False
                    descriptor = descriptor.get_object() if hasattr(descriptor, "get_object") else descriptor
                    if not any(x in descriptor for x in ("/FontFile", "/FontFile2", "/FontFile3")):
                        return False
            return True
        except Exception as exc:  # pragma: no cover
            logger.error("Errore controllo font: %s", exc)
            return False

    def _dimensioni_impaginato(self, reader: PdfReader) -> Tuple[str, bool]:
        dims: list[Tuple[str, str]] = []
        pagine_singole_ok = True
        for page in reader.pages:
            box = page.mediabox
            larg, alt = float(box.width) / 28.35, float(box.height) / 28.35  # pt → cm
            larg_s, alt_s = f"{larg:.1f}".replace(".", ","), f"{alt:.1f}".replace(".", ",")
            dims.append((larg_s, alt_s))
            pagine_singole_ok &= self._check_single_page(larg, alt)
        uniforme = all(d == dims[0] for d in dims)
        dim_finale = f"{dims[0][0]}x{dims[0][1]} cm" if uniforme else "non uniforme"
        return dim_finale, pagine_singole_ok

    def _dimensioni_prima_pagina(self, reader: PdfReader) -> str:
        box = reader.pages[0].mediabox
        larg, alt = float(box.width) / 28.35, float(box.height) / 28.35
        return f"{larg:.1f}x{alt:.1f} cm".replace(".", ",")

    def _check_single_page(self, larg_cm: float, alt_cm: float) -> bool:
        aspect_ratio = larg_cm / alt_cm if alt_cm else 0
        return aspect_ratio <= 1.2

    def _check_page_numbering_consecutive(self, reader: PdfReader) -> bool:
        numbering: list[int] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            nums = re.findall(r"\b\d+\b", text)
            if not nums:
                return False
            numbering.append(int(nums[-1]))
        return all(b == a + 1 for a, b in zip(numbering, numbering[1:]))

    def _check_stampa_pdf(self, reader: PdfReader) -> Tuple[bool, str]:
        color_spaces: set[str] = set()
        for page in reader.pages:
            resources = page.get("/Resources") or {}
            if hasattr(resources, "get_object"):
                resources = resources.get_object()
            xobjects = resources.get("/XObject") or {}
            if hasattr(xobjects, "get_object"):
                xobjects = xobjects.get_object()
            for obj in xobjects.values():
                xobj = obj.get_object() if hasattr(obj, "get_object") else obj
                if xobj.get("/Subtype") == "/Image":
                    cs = xobj.get("/ColorSpace")
                    if isinstance(cs, list):
                        cs = cs[0]
                    cs = str(cs)
                    if cs:
                        color_spaces.add(cs)
        if not color_spaces:
            return True, "Nessuna immagine"
        is_bw = all(cs in ("/DeviceGray", "/CalGray") for cs in color_spaces)
        return is_bw, ", ".join(sorted(color_spaces))

    # ---------- Varie ----------

    @staticmethod
    def _verifica_formato(attuale: str, richiesto: str) -> bool:
        if not richiesto:
            return True
        return attuale.replace(",", ".") == richiesto.replace(",", ".")
