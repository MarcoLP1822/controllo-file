from __future__ import annotations

"""file_checker.core.report

Genera report (PDF e testuale) a partire da:
    • le *specifiche* fornite dall'utente (dataclass ``Specifiche``)
    • i risultati di analisi (``dict[str, AnalysisOutcome]``)

Il codice è isolato da qualsiasi interfaccia grafica; può essere usato da GUI,
CLI o API senza modifiche.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)

# Importa le strutture dati del progetto
try:
    from .parser import Specifiche  # type: ignore
    from .analyzer import AnalysisOutcome  # type: ignore
    from ..utils.logging_conf import logger  # type: ignore
except (ImportError, ValueError):  # fallback se eseguito isolato
    from dataclasses import asdict  # noqa: F401
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)

    # Stub (solo per evitare import error quando si testa il file isolatamente)

    @dataclass
    class Specifiche:  # type: ignore
        impaginato: Dict[str, str] = field(default_factory=dict)
        copertina: Dict[str, str] = field(default_factory=dict)
        extra: Dict[str, str] = field(default_factory=dict)

    @dataclass
    class AnalysisOutcome:  # type: ignore
        formato_file: str
        numero_pagine: Optional[int] = None
        dimensioni: Optional[str] = None
        spazio_colore: Optional[str] = None
        profilo_stampa: Optional[str] = None
        esito_pagine: Optional[bool] = None
        esito_formato: Optional[bool] = None
        esito_protezione: Optional[bool] = None
        esito_font_incorporati: Optional[bool] = None
        esito_pagine_singole: Optional[bool] = None
        esito_numerazione: Optional[bool] = None
        esito_stampa: Optional[bool] = None
        esito: str = "OK"
        messaggio: str = ""

# ---------------------------------------------------------------------------
# ReportGenerator
# ---------------------------------------------------------------------------


class ReportGenerator:
    """Genera report PDF e testo basati sui risultati dell'analisi."""

    def __init__(
        self,
        specifiche: Specifiche | Dict[str, Dict[str, str]],
        risultati: Dict[str, AnalysisOutcome | Dict[str, Any]],
    ) -> None:
        # Accetta sia la dataclass Specifiche sia un dict puro per comodità (GUI pre‑esistente)
        if isinstance(specifiche, Specifiche):
            self._specs_dict = {
                "impaginato": specifiche.impaginato,
                "copertina": specifiche.copertina,
            }
        else:
            self._specs_dict = specifiche  # type: ignore[assignment]

        # Normalizza risultati in AnalysisOutcome (se arrivano come dict)
        self._results: Dict[str, AnalysisOutcome] = {}
        for key, res in risultati.items():
            if isinstance(res, AnalysisOutcome):
                self._results[key] = res
            else:
                self._results[key] = AnalysisOutcome(**res)  # type: ignore[arg-type]

        # Palette colore (personalizzabile)
        self._primary = colors.HexColor("#1E88E5")
        self._success = colors.HexColor("#4CAF50")
        self._error = colors.HexColor("#F44336")
        self._text = colors.HexColor("#212121")
        self._light_grey = colors.HexColor("#EEEEEE")

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------

    def generate_pdf(self, output: str | Path = "report.pdf") -> Path | None:
        """Crea un PDF con layout minimal; ritorna Path se ok, altrimenti None."""

        path = Path(output).with_suffix(".pdf")
        try:
            doc = SimpleDocTemplate(
                str(path),
                pagesize=A4,
                rightMargin=50,
                leftMargin=50,
                topMargin=50,
                bottomMargin=50,
            )
            elems: list[Any] = []
            styles = getSampleStyleSheet()

            # Stili custom
            h_style = ParagraphStyle(
                "header",
                parent=styles["Heading1"],
                fontName="Helvetica-Bold",
                fontSize=20,
                textColor=self._primary,
                alignment=1,
                spaceAfter=25,
            )
            title_style = ParagraphStyle(
                "title",
                parent=styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=15,
                textColor=self._primary,
                spaceBefore=20,
                spaceAfter=15,
            )
            normal = ParagraphStyle(
                "normal",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=10.5,
                textColor=self._text,
                spaceAfter=6,
            )

            # Header
            elems.append(Paragraph("VALUTAZIONE FILE", h_style))
            now = datetime.now().strftime("%d/%m/%Y %H:%M")
            code = datetime.now().strftime("%Y%m%d%H%M%S")
            elems.append(Paragraph(f"<b>Report generato:</b> {now}<br/><b>Codice:</b> {code}", normal))
            elems.append(Spacer(1, 16))

            # --- PREVENTIVO (specifiche) ---
            elems.append(Paragraph("PREVENTIVO", title_style))
            table_data: list[list[str]] = [["Categoria", "Chiave", "Valore"]]
            for cat, d in self._specs_dict.items():
                for k, v in d.items():
                    table_data.append([cat.capitalize(), k.capitalize(), v])
            if len(table_data) == 1:
                table_data.append(["", "", ""])
            colw = [doc.width * 0.25, doc.width * 0.35, doc.width * 0.4]
            t = Table(table_data, colWidths=colw)
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), self._primary),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 11),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                        ("TEXTCOLOR", (0, 1), (-1, -1), self._text),
                        ("ALIGN", (0, 1), (-1, -1), "LEFT"),
                        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 1), (-1, -1), 9.5),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, self._light_grey]),
                    ]
                )
            )
            elems.append(t)
            elems.append(Spacer(1, 18))

            # --- RISULTATI ---
            def check(val: Optional[bool] | Any) -> str:
                return "<font color='green'>✔</font>" if val is True else (
                    "<font color='red'>✘</font>" if val is False else str(val)
                )

            for section in ("impaginato", "copertina"):
                if section not in self._results:
                    continue
                elems.append(Paragraph(section.upper(), title_style))
                res = self._results[section]
                for field, value in res.__dict__.items():
                    if value is None or field in ("esito", "messaggio", "extra"):
                        continue
                    # simboli solo per boolean
                    txt_val = check(value) if field.startswith("esito_") else value
                    pretty_field = field.replace("_", " ").capitalize()
                    elems.append(Paragraph(f"{pretty_field}: {txt_val}", normal))
                elems.append(Spacer(1, 12))

            # Esito globale
            globale = all(r.conforme for r in self._results.values())
            global_style = ParagraphStyle(
                "global_esito",
                parent=styles["Heading2"],
                fontSize=17,
                alignment=1,
                textColor=self._success if globale else self._error,
                spaceBefore=25,
            )
            elems.append(Paragraph("ESITO FINALE: " + ("CONFORME" if globale else "NON CONFORME"), global_style))

            # Footer
            elems.append(Spacer(1, 40))
            footer = ParagraphStyle(
                "footer",
                parent=styles["Normal"],
                fontName="Helvetica-Oblique",
                fontSize=9,
                textColor=colors.gray,
                alignment=2,
            )
            elems.append(Paragraph("Youcanprint Self‑Publishing", footer))
            elems.append(Paragraph(f"Generato il {now}", footer))

            doc.build(elems)
            logger.info("Report PDF generato: %s", path)
            return path
        except Exception as exc:
            logger.exception("Errore generazione report PDF: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Testo semplice
    # ------------------------------------------------------------------

    def generate_text(self, output: str | Path = "report.txt") -> Path | None:
        """Salva un file di testo con i dettagli dell'analisi."""

        path = Path(output).with_suffix(".txt")
        try:
            with path.open("w", encoding="utf-8") as fp:
                fp.write("=== REPORT VERIFICA FILE ===\n")
                fp.write(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n")

                fp.write("--- SPECIFICHE INSERITE ---\n")
                for sec, d in self._specs_dict.items():
                    fp.write(f"{sec.upper()}:\n")
                    for k, v in d.items():
                        fp.write(f"  {k.capitalize()}: {v}\n")

                fp.write("\n--- RISULTATI ANALISI ---\n")
                for sec, res in self._results.items():
                    fp.write(f"{sec.upper()}:\n")
                    for k, v in res.__dict__.items():
                        if v is None or k in ("extra",):
                            continue
                        fp.write(f"  {k.replace('_', ' ').capitalize()}: {v}\n")
                fp.write("\nYoucanprint Self‑Publishing\n")

            logger.info("Report testuale generato: %s", path)
            return path
        except Exception as exc:
            logger.exception("Errore generazione report TXT: %s", exc)
            return None
