from __future__ import annotations

"""file_checker.gui.worker

Thread di analisi in background per non bloccare la GUI Qt.
"""

from pathlib import Path
from typing import Dict, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from ..core.parser import SpecificheParser
from ..core.analyzer import FileAnalyzer, AnalysisOutcome
from ..utils.logging_conf import logger  # type: ignore

__all__ = ["AnalysisWorker"]


class AnalysisWorker(QThread):
    """Esegue il parsing e l'analisi dei file in un thread separato."""

    finished = pyqtSignal(object, dict)  # Specifiche | Exception, risultati
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
            analyzer = FileAnalyzer(specifiche.__dict__)  # usa dict interno per compatibilità
            risultati: Dict[str, AnalysisOutcome] = {}
            if self._impaginato:
                risultati["impaginato"] = analyzer.analizza_file(str(self._impaginato), "impaginato")
            if self._copertina:
                risultati["copertina"] = analyzer.analizza_file(str(self._copertina), "copertina")
            self.finished.emit(specifiche, risultati)  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover
            logger.exception("Errore AnalysisWorker: %s", exc)
            self.error.emit(str(exc))
