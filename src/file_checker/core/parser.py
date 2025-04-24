from __future__ import annotations

"""file_checker.core.parser

Parser delle specifiche testuali fornite dall'utente.

L'input atteso è un blocco di righe "chiave: valore" (case‑insensitive) che
vengono smistate nelle due macro‑categorie *impaginato* e *copertina*.
Qualsiasi chiave sconosciuta viene riportata in un dizionario `extra` in modo
che nessuna informazione vada persa — ma l'evento viene loggato come warning.

Esempio di specifiche accettate::

    Formato: 21x29,7
    Stampa: bianco e nero
    Pagine totali: 64
    Interno: 170gr - patinata opaca
    Copertina: patinata 300gr
    Plastificazione: lucida
    Rilegatura: brossura

Il parser non compie validazioni formali su valori e unità di misura; queste
spettano agli analizzatori lato *core*.
"""

from dataclasses import dataclass, field
import re
import logging
from typing import Dict, Tuple

# ---------------------------------------------------------------------------
# Logging (usa quello del progetto se disponibile)
# ---------------------------------------------------------------------------
try:
    from ..utils.logging_conf import logger  # type: ignore
except (ImportError, ValueError):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Costanti di sezione
# ---------------------------------------------------------------------------

IMPAGINATO_KEYS = {
    "formato",
    "stampa",
    "pagine totali",
    "pagine colori",
    "interno",
}

COPERTINA_KEYS = {
    "copertina",
    "plastificazione",
    "rilegatura",
}

__all__ = [
    "Specifiche",
    "SpecificheParser",
]

# ---------------------------------------------------------------------------
# Data‑class
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Specifiche:
    """Struttura dati normalizzata delle specifiche di progetto."""

    impaginato: Dict[str, str] = field(default_factory=dict)
    copertina: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, str] = field(default_factory=dict)

    def as_tuple(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Restituisce una tupla ``(impaginato, copertina)``."""

        return self.impaginato, self.copertina


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class SpecificheParser:
    """Converte il testo in un oggetto :class:`Specifiche`."""

    _key_val_re = re.compile(r"^(.*?):\s*(.+)$")

    def __init__(self, raw_text: str) -> None:
        if not raw_text.strip():
            raise ValueError("Il testo delle specifiche è vuoto.")
        self.raw_text = raw_text
        self.specifiche = Specifiche()
        self._parse()

    # ------------------------------------------------------------------
    # API pubblica
    # ------------------------------------------------------------------

    def get_specifiche(self) -> Specifiche:  # noqa: D401
        """Restituisce l'oggetto :class:`Specifiche` risultante."""

        return self.specifiche

    # ------------------------------------------------------------------
    # Logica interna
    # ------------------------------------------------------------------

    def _parse(self) -> None:
        for line in self.raw_text.splitlines():
            line = line.strip()
            if not line:
                continue

            match = self._key_val_re.match(line)
            if not match:
                logger.warning("Formato riga non valido nelle specifiche: %s", line)
                continue

            key, value = match.group(1).strip().lower(), match.group(2).strip()

            if key in IMPAGINATO_KEYS:
                self.specifiche.impaginato[key] = value
            elif key in COPERTINA_KEYS:
                self.specifiche.copertina[key] = value
            else:
                logger.warning("Chiave non riconosciuta nelle specifiche: %s", key)
                self.specifiche.extra[key] = value
