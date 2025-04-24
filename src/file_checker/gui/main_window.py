from __future__ import annotations

"""file_checker.gui.main_window

Finestra principale dell'applicazione Qt.
Contiene l'interfaccia grafica, il collegamento ai moduli *core* e il worker di
analisi in background.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QProgressDialog,
)

# Import core components
from ..core.parser import SpecificheParser
from ..core.analyzer import FileAnalyzer, AnalysisOutcome
from ..core.report import ReportGenerator
from ..utils.logging_conf import logger  # type: ignore
from ..gui.worker import AnalysisWorker

__all__ = ["FileCheckerMainWindow"]

# ---------------------------------------------------------------------------
# Worker thread (analisi in background)
# ---------------------------------------------------------------------------


class AnalysisWorker(QThread):
    """Esegue il parsing e l'analisi dei file in un thread separato."""

    finished = pyqtSignal(object, dict)  # SpecificheParser | Exception, risultati
    error = pyqtSignal(str)

    def __init__(
        self,
        testo_specifiche: str,
        file_impaginato: Optional[Path],
        file_copertina: Optional[Path],
    ) -> None:
        super().__init__()
        self._testo = testo_specifiche
        self._impaginato = file_impaginato
        self._copertina = file_copertina

    # ------------------------------------------------------------------
    # Thread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:  # noqa: D401
        try:
            parser = SpecificheParser(self._testo)
            specifiche = parser.get_specifiche()
            analyzer = FileAnalyzer(specifiche.__dict__)  # usa dict interno
            risultati: Dict[str, AnalysisOutcome] = {}
            if self._impaginato:
                risultati["impaginato"] = analyzer.analizza_file(str(self._impaginato), "impaginato")
            if self._copertina:
                risultati["copertina"] = analyzer.analizza_file(str(self._copertina), "copertina")
            self.finished.emit(specifiche, risultati)  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover
            logger.exception("Errore AnalisiWorker: %s", exc)
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Finestra principale
# ---------------------------------------------------------------------------


class FileCheckerMainWindow(QMainWindow):
    """Interfaccia grafica principale del File Checker."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("File Checker Aziendale")
        self.setMinimumSize(1000, 700)

        # Percorsi file selezionati
        self._file_impaginato: Optional[Path] = None
        self._file_copertina: Optional[Path] = None

        # Generator di report (dopo la verifica)
        self._report_generator: Optional[ReportGenerator] = None

        # UI
        self._build_ui()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background-color: #f4f4f4; }
            QLabel { color: #333; font-size: 15px; font-weight: 500; }
            QPushButton { background-color: #3498db; color: white; border: none; padding: 9px 14px; border-radius: 4px; }
            QPushButton:hover { background-color: #2980b9; }
            QPlainTextEdit { background-color: white; border: 1px solid #ddd; border-radius: 4px; padding: 8px; }
            """
        )

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # --- Specifiche text box ---
        layout.addWidget(QLabel("Inserisci Specifiche"))
        self._txt_specs = QPlainTextEdit()
        self._txt_specs.setPlaceholderText(
            "Incolla qui le specifiche del documento\n"
            "Esempio:\n"
            "Formato: 21x29,7\n"
            "Stampa: bianco e nero\n"
            "Pagine totali: 64\n"
            "Interno: 170gr - patinata opaca\n"
            "Copertina: patinata 300gr, plastificata lucida"
        )
        layout.addWidget(self._txt_specs)

        # --- Selezione file ---
        btn_layout = QHBoxLayout()
        self._btn_impaginato = QPushButton("Seleziona File Impaginato")
        self._btn_impaginato.clicked.connect(self._select_impaginato)
        self._btn_copertina = QPushButton("Seleziona File Copertina")
        self._btn_copertina.clicked.connect(self._select_copertina)
        btn_layout.addWidget(self._btn_impaginato)
        btn_layout.addWidget(self._btn_copertina)
        layout.addLayout(btn_layout)

        # --- Tabella risultati ---
        layout.addWidget(QLabel("Risultati Verifica"))
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Tipo", "Nome File", "Formato", "Dimensioni", "Stato"])
        layout.addWidget(self._table)

        # --- Azioni ---
        action_layout = QHBoxLayout()
        self._btn_verify = QPushButton("Avvia Verifica")
        self._btn_verify.clicked.connect(self._start_analysis)
        self._btn_export = QPushButton("Esporta Report")
        self._btn_export.clicked.connect(self._export_report)
        action_layout.addStretch()
        action_layout.addWidget(self._btn_verify)
        action_layout.addWidget(self._btn_export)
        layout.addLayout(action_layout)

        self.setCentralWidget(central)

    # ------------------------------------------------------------------
    # File selection
    # ------------------------------------------------------------------

    def _select_impaginato(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona File Impaginato", str(Path.home()), "File Supportati (*.pdf *.docx *.jpg *.png *.tiff)"
        )
        if path:
            self._file_impaginato = Path(path)
            self._btn_impaginato.setText(self._file_impaginato.name)

    def _select_copertina(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona File Copertina", str(Path.home()), "File Supportati (*.pdf *.docx *.jpg *.png *.tiff)"
        )
        if path:
            self._file_copertina = Path(path)
            self._btn_copertina.setText(Path(path).name)

    # ------------------------------------------------------------------
    # Avvio Analisi
    # ------------------------------------------------------------------

    def _start_analysis(self) -> None:
        specs_txt = self._txt_specs.toPlainText().strip()
        if not specs_txt:
            QMessageBox.critical(self, "Errore", "Inserisci le specifiche prima di avviare la verifica.")
            return

        self._progress = QProgressDialog("Analisi in corso…", "Annulla", 0, 0, self)
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setCancelButton(None)
        self._progress.show()
        self._btn_verify.setEnabled(False)

        self._worker = AnalysisWorker(specs_txt, self._file_impaginato, self._file_copertina)
        self._worker.finished.connect(self._on_analysis_finished)
        self._worker.error.connect(self._on_analysis_error)
        self._worker.start()

    def _on_analysis_finished(self, specifiche: Any, risultati: Dict[str, AnalysisOutcome]) -> None:  # noqa: ANN401
        self._progress.close()
        self._btn_verify.setEnabled(True)

        # Popola tabella
        self._table.setRowCount(0)
        for tipo, outcome in risultati.items():
            row = self._table.rowCount()
            self._table.insertRow(row)
            nome_file = (
                self._file_impaginato.name if tipo == "impaginato" else (self._file_copertina.name if self._file_copertina else "-")
            )
            self._table.setItem(row, 0, QTableWidgetItem(tipo.capitalize()))
            self._table.setItem(row, 1, QTableWidgetItem(nome_file))
            self._table.setItem(row, 2, QTableWidgetItem(str(outcome.formato_file)))
            self._table.setItem(row, 3, QTableWidgetItem(str(outcome.dimensioni or "")))
            stato = "Conforme" if outcome.conforme else "Non Conforme"
            self._table.setItem(row, 4, QTableWidgetItem(stato))

        # Salva generatore report per export
        self._report_generator = ReportGenerator(specifiche, risultati)

    def _on_analysis_error(self, msg: str) -> None:
        self._progress.close()
        self._btn_verify.setEnabled(True)
        QMessageBox.critical(self, "Errore", msg)

    # ------------------------------------------------------------------
    # Export Report
    # ------------------------------------------------------------------

    def _export_report(self) -> None:
        if not self._report_generator:
            QMessageBox.warning(self, "Avviso", "Esegui prima la verifica per generare il report.")
            return
        directory = QFileDialog.getExistingDirectory(self, "Seleziona Directory di Salvataggio")
        if not directory:
            return
        pdf_path = Path(directory) / "report.pdf"
        txt_path = Path(directory) / "report.txt"
        pdf_ok = self._report_generator.generate_pdf(pdf_path)
        txt_ok = self._report_generator.generate_text(txt_path)
        if pdf_ok and txt_ok:
            QMessageBox.information(
                self, "Report Generati", f"Report PDF: {pdf_ok}\nReport TXT: {txt_ok}")
        else:
            QMessageBox.critical(self, "Errore", "Si è verificato un errore nella generazione dei report.")


# ---------------------------------------------------------------------------
# Eseguibile standalone per sviluppo rapido
# ---------------------------------------------------------------------------


def main() -> None:  # pragma: no cover
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    win = FileCheckerMainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":  # pragma: no cover
    main()
