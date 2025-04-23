#!/usr/bin/env python3
import os
import sys
import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional

import PyPDF2
import docx
from PIL import Image
import magic  # Assicurarsi che libmagic sia correttamente installato

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFileDialog, QTableWidget, QTableWidgetItem, QPlainTextEdit, QMessageBox, QProgressDialog
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QThread, pyqtSignal

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
def setup_logging() -> None:
    """Configura il logger globale sia per file che per console."""
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"file_checker_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s: %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()]
    )

# Inizializza il logging all'avvio
setup_logging()
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# SpecificheParser
# -----------------------------------------------------------------------------
class SpecificheParser:
    """
    Classe per l'analisi delle specifiche fornite in formato testo.
    Le specifiche vengono suddivise in due categorie: 'impaginato' e 'copertina'.
    """
    IMPAGINATO_KEYS = {"formato", "stampa", "pagine totali", "pagine colori", "interno"}
    COPERTINA_KEYS = {"copertina", "plastificazione", "rilegatura"}

    def __init__(self, testo_specifiche: str) -> None:
        if not testo_specifiche.strip():
            raise ValueError("Il testo delle specifiche è vuoto.")
        self.testo_originale = testo_specifiche
        self.specifiche: Dict[str, Dict[str, str]] = {"impaginato": {}, "copertina": {}}
        self.parse_specifiche()

    def parse_specifiche(self) -> None:
        """Analizza il testo riga per riga, assegnando le chiavi alla sezione corretta."""
        for line in self.testo_originale.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^(.*?):\s*(.+)$", line)
            if match:
                key = match.group(1).strip().lower()
                value = match.group(2).strip()
                if key in self.IMPAGINATO_KEYS:
                    self.specifiche["impaginato"][key] = value
                elif key in self.COPERTINA_KEYS:
                    self.specifiche["copertina"][key] = value
                else:
                    logger.warning(f"Chiave non riconosciuta nelle specifiche: {key}")
            else:
                logger.warning(f"Formato riga non valido nelle specifiche: {line}")

    def get_specifiche(self) -> Dict[str, Dict[str, str]]:
        return self.specifiche

# -----------------------------------------------------------------------------
# FileAnalyzer
# -----------------------------------------------------------------------------
class FileAnalyzer:
    """
    Classe per analizzare i file (PDF, DOCX, immagini) in base alle specifiche fornite.
    """
    def __init__(self, specifiche: Dict[str, Dict[str, str]]) -> None:
        self.specifiche = specifiche
        self.risultati_analisi: Dict[str, Dict[str, Any]] = {
            'impaginato': {},
            'copertina': {}
        }

    def analizza_file(self, percorso_file: str, tipo: str) -> Dict[str, Any]:
        if not os.path.exists(percorso_file):
            return {'esito': 'Errore', 'messaggio': f"File non trovato: {percorso_file}"}
        try:
            mime = magic.Magic(mime=True)
            tipo_mime = mime.from_file(percorso_file)
        except Exception as e:
            logger.error(f"Errore nel rilevamento del MIME type: {e}")
            return {'esito': 'Errore', 'messaggio': f"Impossibile determinare il formato del file: {e}"}

        analizzatori = {
            'application/pdf': self._analizza_pdf,
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': self._analizza_word,
            'image/jpeg': self._analizza_immagine,
            'image/png': self._analizza_immagine,
            'image/tiff': self._analizza_immagine
        }
        analizzatore = analizzatori.get(tipo_mime)
        if not analizzatore:
            return {'esito': 'Errore', 'messaggio': f'Formato file non supportato: {tipo_mime}'}
        return analizzatore(percorso_file, tipo)

    def _analizza_pdf(self, percorso_file: str, tipo: str) -> Dict[str, Any]:
        try:
            with open(percorso_file, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                protezione_ok = not pdf_reader.is_encrypted
                if not protezione_ok:
                    logger.error("Il file PDF è protetto da password.")
                    num_pagine = 0
                    unique_dimensions = "0x0 cm"
                    fonts_embedded = False
                    pagine_singole = False
                    numerazione_ok = False
                else:
                    fonts_embedded = self._check_all_fonts_incorporati(pdf_reader)
                    num_pagine = len(pdf_reader.pages)
                    if tipo == "impaginato":
                        dimensions_list = []
                        for page in pdf_reader.pages:
                            dimensioni = page.mediabox
                            larghezza = float(dimensioni.width) / 28.35
                            altezza = float(dimensioni.height) / 28.35
                            larghezza_str = f"{larghezza:.1f}".replace('.', ',')
                            altezza_str = f"{altezza:.1f}".replace('.', ',')
                            dimensions_list.append((larghezza_str, altezza_str))
                        if all(dim == dimensions_list[0] for dim in dimensions_list):
                            unique_dimensions = f"{dimensions_list[0][0]}x{dimensions_list[0][1]} cm"
                        else:
                            unique_dimensions = "non uniforme"
                    else:
                        dimensioni = pdf_reader.pages[0].mediabox
                        larghezza = float(dimensioni.width) / 28.35
                        altezza = float(dimensioni.height) / 28.35
                        larghezza_str = f"{larghezza:.1f}".replace('.', ',')
                        altezza_str = f"{altezza:.1f}".replace('.', ',')
                        unique_dimensions = f"{larghezza_str}x{altezza_str} cm"
                    if tipo == "impaginato":
                        pagine_singole = self._check_all_single_pages(pdf_reader)
                        numerazione_ok = self._check_page_numbering_consecutive(pdf_reader)
                        # Nuovo controllo: tipologia di stampa
                        esito_stampa, profilo_stampa = self._check_stampa_pdf(pdf_reader)
                    else:
                        pagine_singole = True
                        numerazione_ok = True
                        esito_stampa = True
                        profilo_stampa = ""
                specs = self.specifiche.get(tipo, {})
                esito_formato = self._verifica_formato(unique_dimensions, specs.get('formato', '')) if protezione_ok else False
                
                # Confronta il risultato del controllo stampa con la specifica ("Stampa: bianco e nero" o "Stampa: colori")
                expected_stampa = specs.get("stampa", "").lower().strip()
                if expected_stampa == "bianco e nero":
                    esito_stampa_final = esito_stampa
                elif expected_stampa == "colori":
                    esito_stampa_final = not esito_stampa
                else:
                    esito_stampa_final = True

                risultato = {
                    'formato_file': 'PDF',
                    'numero_pagine': num_pagine,
                    'dimensioni': unique_dimensions,
                    'esito_pagine': num_pagine == int(specs.get('pagine totali', 0)) if protezione_ok else False,
                    'esito_formato': esito_formato,
                    'esito_protezione': protezione_ok,
                    'esito_font_incorporati': fonts_embedded,
                    'esito_pagine_singole': pagine_singole,
                    'esito_numerazione': numerazione_ok,
                    'esito_stampa': esito_stampa_final,
                    'profilo_stampa': profilo_stampa
                }
                self.risultati_analisi[tipo] = risultato
                return risultato

        except Exception as e:
            logger.error(f"Errore nell'analisi del PDF: {e}")
            return {'esito': 'Errore', 'messaggio': str(e)}

    def _check_all_fonts_incorporati(self, pdf_reader: PyPDF2.PdfReader) -> bool:
        try:
            for page in pdf_reader.pages:
                resources = page.get("/Resources")
                if resources is None:
                    continue
                if hasattr(resources, "get_object"):
                    resources = resources.get_object()
                fonts = resources.get("/Font")
                if fonts is None:
                    continue
                if hasattr(fonts, "get_object"):
                    fonts = fonts.get_object()
                for font_key in fonts:
                    font = fonts[font_key]
                    if hasattr(font, "get_object"):
                        font = font.get_object()
                    if "/FontDescriptor" in font:
                        descriptor = font["/FontDescriptor"]
                        if hasattr(descriptor, "get_object"):
                            descriptor = descriptor.get_object()
                        if not ("/FontFile" in descriptor or "/FontFile2" in descriptor or "/FontFile3" in descriptor):
                            return False
                    else:
                        return False
            return True
        except Exception as e:
            logger.error("Errore nel controllo dei font incorporati: " + str(e))
            return False

    def _check_single_page(self, page) -> bool:
        try:
            dimensioni = page.mediabox
            larghezza = float(dimensioni.width) / 28.35
            altezza = float(dimensioni.height) / 28.35
            aspect_ratio = larghezza / altezza if altezza != 0 else 0
            return aspect_ratio <= 1.2
        except Exception as e:
            logger.error("Errore nel controllo pagina singola: " + str(e))
            return False

    def _check_all_single_pages(self, pdf_reader: PyPDF2.PdfReader) -> bool:
        try:
            for page in pdf_reader.pages:
                if not self._check_single_page(page):
                    return False
            return True
        except Exception as e:
            logger.error("Errore nel controllo pagine singole: " + str(e))
            return False

    def _check_page_numbering_consecutive(self, pdf_reader: PyPDF2.PdfReader) -> bool:
        try:
            numbering = []
            for page in pdf_reader.pages:
                text = page.extract_text() or ""
                numbers = re.findall(r'\b\d+\b', text)
                if numbers:
                    page_num = int(numbers[-1])
                    numbering.append(page_num)
                else:
                    return False
            for i in range(len(numbering) - 1):
                if numbering[i+1] != numbering[i] + 1:
                    return False
            return True
        except Exception as e:
            logger.error("Errore nel controllo della numerazione: " + str(e))
            return False

    def _check_stampa_pdf(self, pdf_reader: PyPDF2.PdfReader) -> (bool, str):
        """
        Controlla la tipologia di stampa del PDF esaminando i color spaces usati negli XObject immagini.
        Se tutte le immagini usano "/DeviceGray" o "/CalGray", il documento è considerato in bianco e nero.
        Restituisce una tupla: (True se BW, False se colori, profilo(s) rilevato/i).
        """
        try:
            color_spaces = set()
            for page in pdf_reader.pages:
                resources = page.get("/Resources")
                if not resources:
                    continue
                if hasattr(resources, "get_object"):
                    resources = resources.get_object()
                xobjects = resources.get("/XObject")
                if not xobjects:
                    continue
                if hasattr(xobjects, "get_object"):
                    xobjects = xobjects.get_object()
                for xobj_key in xobjects:
                    xobj = xobjects[xobj_key]
                    if hasattr(xobj, "get_object"):
                        xobj = xobj.get_object()
                    if xobj.get("/Subtype") == "/Image":
                        cs = xobj.get("/ColorSpace")
                        if cs:
                            if hasattr(cs, "get_object"):
                                cs = cs.get_object()
                            if isinstance(cs, list) and len(cs) > 0:
                                cs_val = cs[0]
                            else:
                                cs_val = cs
                            cs_str = str(cs_val)
                            color_spaces.add(cs_str)
            if not color_spaces:
                return (True, "Nessun elemento immagine rilevato")
            # Il documento è considerato BW se tutti i color space sono "/DeviceGray" o "/CalGray"
            is_bw = all(cs in ["/DeviceGray", "/CalGray"] for cs in color_spaces)
            profiles = ", ".join(sorted(color_spaces))
            return (is_bw, profiles)
        except Exception as e:
            logger.error("Errore nel controllo della tipologia di stampa: " + str(e))
            return (False, "Errore")
    
    def _analizza_word(self, percorso_file: str, tipo: str) -> Dict[str, Any]:
        try:
            num_pagine: int = 0
            try:
                import win32com.client  # type: ignore
                word = win32com.client.Dispatch("Word.Application")
                word.Visible = False
                try:
                    doc = word.Documents.Open(percorso_file)
                    num_pagine = doc.ComputeStatistics(2)
                    doc.Close(False)
                finally:
                    word.Quit()
            except ImportError:
                document = docx.Document(percorso_file)
                num_pagine = len(document.paragraphs)
            specs = self.specifiche.get(tipo, {})
            risultato = {
                'formato_file': 'WORD',
                'numero_pagine': num_pagine,
                'esito_pagine': num_pagine == int(specs.get('pagine totali', 0))
            }
            self.risultati_analisi[tipo] = risultato
            return risultato
        except Exception as e:
            logger.error(f"Errore nell'analisi del file Word: {e}")
            return {'esito': 'Errore', 'messaggio': f"Errore nell'analisi del file Word: {str(e)}"}

    def _analizza_immagine(self, percorso_file: str, tipo: str) -> Dict[str, Any]:
        try:
            with Image.open(percorso_file) as img:
                larghezza = float(img.width) / 118.11
                altezza = float(img.height) / 118.11
                larghezza_str = f"{larghezza:.1f}".replace('.', ',')
                altezza_str = f"{altezza:.1f}".replace('.', ',')
                specs = self.specifiche.get(tipo, {})
                risultato = {
                    'formato_file': img.format,
                    'dimensioni': f'{larghezza_str}x{altezza_str} cm',
                    'spazio_colore': {
                        'RGB': 'RGB',
                        'CMYK': 'CMYK',
                        'L': 'Scala di Grigi'
                    }.get(img.mode, 'Sconosciuto'),
                    'esito_formato': self._verifica_formato(f'{larghezza_str}x{altezza_str} cm', specs.get('formato', ''))
                }
                self.risultati_analisi[tipo] = risultato
                return risultato
        except Exception as e:
            logger.error(f"Errore nell'analisi dell'immagine: {e}")
            return {'esito': 'Errore', 'messaggio': str(e)}

    def _verifica_formato(self, formato_attuale: str, formato_richiesto: str) -> bool:
        if not formato_richiesto:
            return True
        return formato_attuale.replace(',', '.') == formato_richiesto.replace(',', '.')

    def get_risultati(self) -> Dict[str, Dict[str, Any]]:
        return self.risultati_analisi

# -----------------------------------------------------------------------------
# ReportGenerator (PDF Output Minimal & Modern)
# -----------------------------------------------------------------------------
class ReportGenerator:
    """
    Classe per generare report in PDF e log testuale a partire dalle specifiche e dai risultati dell'analisi.
    L'output PDF è diviso in blocchi e presenta un design minimal e moderno.
    """
    def __init__(self, specifiche: Dict[str, Dict[str, str]], risultati_analisi: Dict[str, Dict[str, Any]]) -> None:
        self.specifiche = specifiche
        self.risultati_analisi = risultati_analisi
        # I colori sono personalizzati (puoi modificarli se necessario)
        self.primary_color = colors.HexColor("#1E88E5")
        self.success_color = colors.HexColor("#4CAF50")
        self.error_color = colors.HexColor("#F44336")
        self.text_color = colors.HexColor("#212121")
        self.light_grey = colors.HexColor("#EEEEEE")

    def genera_report_pdf(self, percorso_output: Optional[str] = None) -> Optional[str]:
        percorso_output = percorso_output or 'report.pdf'
        try:
            doc = SimpleDocTemplate(
                percorso_output, 
                pagesize=(595.27, 841.89),  # A4 in punti
                rightMargin=50, leftMargin=50, 
                topMargin=50, bottomMargin=50
            )
            elementi = []
            styles = getSampleStyleSheet()
            
            # Stili personalizzati
            header_style = ParagraphStyle(
                'header_style',
                parent=styles['Heading1'],
                fontName='Helvetica-Bold',
                fontSize=20,
                textColor=self.primary_color,
                alignment=1,
                spaceAfter=25
            )
            
            title_style = ParagraphStyle(
                'title_style',
                parent=styles['Heading2'],
                fontName='Helvetica-Bold',
                fontSize=16,
                textColor=self.primary_color,
                spaceBefore=20,
                spaceAfter=15
            )
            
            subtitle_style = ParagraphStyle(
                'subtitle_style',
                parent=styles['Heading3'],
                fontName='Helvetica-Bold',
                fontSize=13,
                textColor=self.text_color,
                spaceBefore=12,
                spaceAfter=8
            )
            
            normal_style = ParagraphStyle(
                'normal_style',
                parent=styles['Normal'],
                fontName='Helvetica',
                fontSize=11,
                textColor=self.text_color,
                spaceAfter=6,
                leading=16
            )
            
            info_style = ParagraphStyle(
                'info_style',
                parent=normal_style,
                backColor=self.light_grey,
                borderPadding=8,
                alignment=0
            )
            
            footer_style = ParagraphStyle(
                'footer_style',
                parent=styles['Normal'],
                fontName='Helvetica-Oblique',
                fontSize=9,
                textColor=colors.gray,
                alignment=2
            )
            
            # Blocco Info
            elementi.append(Paragraph("VALUTAZIONE FILE", header_style))
            data_ora = datetime.now().strftime('%d/%m/%Y %H:%M')
            info_text = f"<b>Report generato:</b> {data_ora}<br/><b>Codice verifica:</b> {datetime.now().strftime('%Y%m%d%H%M%S')}"
            elementi.append(Paragraph(info_text, info_style))
            elementi.append(Spacer(1, 20))
            
            # Blocco PREVENTIVO
            elementi.append(Paragraph("PREVENTIVO", title_style))
            data = []
            headers = ["Categoria", "Dettaglio", "Valore"]
            data.append(headers)
            for sezione, specs in self.specifiche.items():
                for chiave, valore in specs.items():
                    data.append([sezione.capitalize(), chiave.capitalize(), valore])
            if len(data) == 1:
                data.append(["", "", ""])
            table_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.primary_color),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, -1), self.text_color),
                ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.light_grey]),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
            ])
            colWidths = [doc.width * 0.25, doc.width * 0.35, doc.width * 0.4]
            specs_table = Table(data, colWidths=colWidths)
            specs_table.setStyle(table_style)
            elementi.append(specs_table)
            elementi.append(Spacer(1, 20))
            
            # Funzione helper per simboli di controllo
            def get_check_mark(value):
                if isinstance(value, bool):
                    return '<font color="green">V</font>' if value else '<font color="red">X</font>'
                return str(value)
            
            # Blocco IMPAGINATO
            if "impaginato" in self.risultati_analisi:
                elementi.append(Paragraph("IMPAGINATO", subtitle_style))
                for chiave, valore in self.risultati_analisi["impaginato"].items():
                    # Per i campi booleani (i controlli) sostituisco con il simbolo
                    if chiave.startswith("esito_"):
                        elementi.append(Paragraph(f"{chiave[6:].replace('_', ' ').capitalize()}: {get_check_mark(valore)}", normal_style))
                    elif chiave not in ["dimensioni", "formato_file", "numero_pagine"]:
                        elementi.append(Paragraph(f"{chiave.replace('_', ' ').capitalize()}: {valore}", normal_style))
                elementi.append(Spacer(1, 15))
            
            # Blocco COPERTINA
            if "copertina" in self.risultati_analisi:
                elementi.append(Paragraph("COPERTINA", subtitle_style))
                for chiave, valore in self.risultati_analisi["copertina"].items():
                    if chiave.startswith("esito_"):
                        elementi.append(Paragraph(f"{chiave[6:].replace('_', ' ').capitalize()}: {get_check_mark(valore)}", normal_style))
                    elif chiave not in ["dimensioni", "formato_file", "numero_pagine"]:
                        elementi.append(Paragraph(f"{chiave.replace('_', ' ').capitalize()}: {valore}", normal_style))
                elementi.append(Spacer(1, 15))
            
            # Esito finale
            esito_complessivo = True
            for sezione, risultati in self.risultati_analisi.items():
                for chiave, valore in risultati.items():
                    if chiave.startswith('esito_') and not valore:
                        esito_complessivo = False
                        break
            esito_style = ParagraphStyle(
                'esito_style',
                parent=title_style,
                fontSize=18,
                alignment=1,
                spaceBefore=30,
                textColor=self.success_color if esito_complessivo else self.error_color
            )
            elementi.append(Paragraph(
                "ESITO FINALE: " + ("CONFORME" if esito_complessivo else "NON CONFORME"), 
                esito_style
            ))
            
            # Footer con firma
            elementi.append(Spacer(1, 50))
            elementi.append(Paragraph("Youcanprint Self-Publishing", footer_style))
            elementi.append(Paragraph(f"Report generato il {data_ora}", footer_style))
            
            doc.build(elementi)
            logger.info(f"Report PDF generato: {percorso_output}")
            return percorso_output
        except Exception as e:
            logger.error(f"Errore generazione report PDF: {e}")
            return None

    def genera_log_testuale(self, percorso_output: Optional[str] = None) -> Optional[str]:
        percorso_output = percorso_output or 'report.txt'
        try:
            with open(percorso_output, 'w', encoding='utf-8') as f:
                f.write("=== REPORT VERIFICA FILE ===\n")
                f.write(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n")
                f.write("--- SPECIFICHE INSERITE ---\n")
                for sezione, specs in self.specifiche.items():
                    f.write(f"{sezione.upper()}:\n")
                    for chiave, valore in specs.items():
                        f.write(f"  {chiave.capitalize()}: {valore}\n")
                f.write("\n--- RISULTATI ANALISI ---\n")
                for sezione, risultato in self.risultati_analisi.items():
                    f.write(f"{sezione.upper()}:\n")
                    for chiave, valore in risultato.items():
                        f.write(f"  {chiave.replace('_', ' ').capitalize()}: {valore}\n")
                f.write("\nYoucanprint Self-Publishing\n")
            logger.info(f"Report testuale generato: {percorso_output}")
            return percorso_output
        except Exception as e:
            logger.error(f"Errore generazione report testuale: {e}")
            return None

    # La duplicazione del metodo genera_log_testuale è stata evitata

# -----------------------------------------------------------------------------
# Worker per l'Analisi in Background
# -----------------------------------------------------------------------------
class AnalysisWorker(QThread):
    finished = pyqtSignal(dict, dict)
    error = pyqtSignal(str)

    def __init__(self, testo_specifiche: str, percorso_impaginato: Optional[str], percorso_copertina: Optional[str]) -> None:
        super().__init__()
        self.testo_specifiche = testo_specifiche
        self.percorso_impaginato = percorso_impaginato
        self.percorso_copertina = percorso_copertina

    def run(self) -> None:
        try:
            parser = SpecificheParser(self.testo_specifiche)
            specifiche = parser.get_specifiche()
            analyzer = FileAnalyzer(specifiche)
            risultati: Dict[str, Any] = {}
            if self.percorso_impaginato:
                risultati['impaginato'] = analyzer.analizza_file(self.percorso_impaginato, 'impaginato')
            if self.percorso_copertina:
                risultati['copertina'] = analyzer.analizza_file(self.percorso_copertina, 'copertina')
            self.finished.emit(specifiche, risultati)
        except Exception as e:
            logger.error(f"Errore nell'analisi in background: {e}")
            self.error.emit(str(e))

# -----------------------------------------------------------------------------
# Interfaccia Grafica (GUI)
# -----------------------------------------------------------------------------
class FileCheckerApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("File Checker Aziendale")
        self.setGeometry(100, 100, 1000, 700)
        self.setStyleSheet("""
            QMainWindow { background-color: #f4f4f4; }
            QLabel { color: #333; font-size: 16px; font-weight: 500; }
            QPushButton { background-color: #3498db; color: white; border: none; padding: 10px 15px; border-radius: 4px; }
            QPushButton:hover { background-color: #2980b9; }
            QPlainTextEdit { background-color: white; border: 1px solid #ddd; border-radius: 4px; padding: 8px; }
        """)
        self.percorso_impaginato: Optional[str] = None
        self.percorso_copertina: Optional[str] = None
        self.report_generator: Optional[ReportGenerator] = None
        self.worker: Optional[AnalysisWorker] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        specifiche_label = QLabel("Inserisci Specifiche")
        self.specifiche_text = QPlainTextEdit()
        self.specifiche_text.setPlaceholderText(
            "Incolla qui le specifiche del documento\n"
            "Esempio:\n"
            "Formato: 21x29,7\n"
            "Stampa: bianco e nero\n"
            "Pagine totali: 64\n"
            "Interno: 170gr - patinata opaca\n"
            "Copertina: patinata 300gr, plastificata lucida"
        )
        file_layout = QHBoxLayout()
        self.impaginato_btn = QPushButton("Seleziona File Impaginato")
        self.impaginato_btn.clicked.connect(self.seleziona_impaginato)
        self.copertina_btn = QPushButton("Seleziona File Copertina")
        self.copertina_btn.clicked.connect(self.seleziona_copertina)
        file_layout.addWidget(self.impaginato_btn)
        file_layout.addWidget(self.copertina_btn)
        risultati_label = QLabel("Risultati Verifica")
        self.risultati_table = QTableWidget(0, 5)
        self.risultati_table.setHorizontalHeaderLabels(["Tipo", "Nome File", "Formato", "Dimensioni", "Stato"])
        azioni_layout = QHBoxLayout()
        self.verifica_btn = QPushButton("Avvia Verifica")
        self.verifica_btn.clicked.connect(self.avvia_verifica)
        self.esporta_btn = QPushButton("Esporta Report")
        self.esporta_btn.clicked.connect(self.esporta_report)
        azioni_layout.addStretch()
        azioni_layout.addWidget(self.verifica_btn)
        azioni_layout.addWidget(self.esporta_btn)
        main_layout.addWidget(specifiche_label)
        main_layout.addWidget(self.specifiche_text)
        main_layout.addLayout(file_layout)
        main_layout.addWidget(risultati_label)
        main_layout.addWidget(self.risultati_table)
        main_layout.addLayout(azioni_layout)
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def seleziona_impaginato(self) -> None:
        percorso, _ = QFileDialog.getOpenFileName(
            self, "Seleziona File Impaginato", "", "File Supportati (*.pdf *.docx *.jpg *.png *.tiff)"
        )
        if percorso:
            self.percorso_impaginato = percorso
            self.impaginato_btn.setText(os.path.basename(percorso))

    def seleziona_copertina(self) -> None:
        percorso, _ = QFileDialog.getOpenFileName(
            self, "Seleziona File Copertina", "", "File Supportati (*.pdf *.docx *.jpg *.png *.tiff)"
        )
        if percorso:
            self.percorso_copertina = percorso
            self.copertina_btn.setText(os.path.basename(percorso))

    def avvia_verifica(self) -> None:
        testo_specifiche = self.specifiche_text.toPlainText()
        if not testo_specifiche.strip():
            QMessageBox.critical(self, "Errore", "Inserisci le specifiche prima di avviare la verifica.")
            return
        progress = QProgressDialog("Analisi in corso...", "Annulla", 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setCancelButton(None)
        progress.show()
        self.verifica_btn.setEnabled(False)
        self.worker = AnalysisWorker(testo_specifiche, self.percorso_impaginato, self.percorso_copertina)
        self.worker.finished.connect(lambda specs, risultati: self._on_analysis_finished(specs, risultati, progress))
        self.worker.error.connect(lambda msg: self._on_analysis_error(msg, progress))
        self.worker.start()

    def _on_analysis_finished(self, specifiche: Dict[str, Dict[str, str]], risultati: Dict[str, Any], progress: QProgressDialog) -> None:
        progress.close()
        self.verifica_btn.setEnabled(True)
        self.risultati_table.setRowCount(0)
        for tipo, res in risultati.items():
            row = self.risultati_table.rowCount()
            self.risultati_table.insertRow(row)
            nome_file = os.path.basename(self.percorso_impaginato if tipo == 'impaginato' else self.percorso_copertina)
            self.risultati_table.setItem(row, 0, QTableWidgetItem(tipo.capitalize()))
            self.risultati_table.setItem(row, 1, QTableWidgetItem(nome_file))
            self.risultati_table.setItem(row, 2, QTableWidgetItem(str(res.get('formato_file', ''))))
            self.risultati_table.setItem(row, 3, QTableWidgetItem(str(res.get('dimensioni', ''))))
            stato = "Conforme" if all(v is True for k, v in res.items() if k.startswith('esito_')) else "Non Conforme"
            self.risultati_table.setItem(row, 4, QTableWidgetItem(stato))
        self.report_generator = ReportGenerator(specifiche, risultati)

    def _on_analysis_error(self, msg: str, progress: QProgressDialog) -> None:
        progress.close()
        self.verifica_btn.setEnabled(True)
        QMessageBox.critical(self, "Errore", msg)

    def esporta_report(self) -> None:
        if not self.report_generator:
            QMessageBox.warning(self, "Avviso", "Esegui prima la verifica per generare il report.")
            return
        directory = QFileDialog.getExistingDirectory(self, "Seleziona Directory di Salvataggio")
        if not directory:
            return
        pdf_path = os.path.join(directory, "report.pdf")
        txt_path = os.path.join(directory, "report.txt")
        pdf_generated = self.report_generator.genera_report_pdf(pdf_path)
        txt_generated = self.report_generator.genera_log_testuale(txt_path)
        if pdf_generated and txt_generated:
            QMessageBox.information(self, "Report Generati", f"Report PDF: {pdf_generated}\nLog: {txt_generated}")
        else:
            QMessageBox.critical(self, "Errore", "Si è verificato un errore nella generazione dei report.")

# -----------------------------------------------------------------------------
# Funzione Principale
# -----------------------------------------------------------------------------
def main() -> None:
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = FileCheckerApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
