"""Umwandlung zwischen Zeitmess-Notation und Millisekunden.

Rundenzeiten werden im Fahrbetrieb als "m:ss.mmm" notiert (1:23.456),
Sektorzeiten meist ohne Minutenanteil (38.412). Beide Formen werden hier auf
ganzzahlige Millisekunden abgebildet, damit im System nur ein Zeitformat
existiert.
"""

import re

# Erlaubt "38", "38.4", "38.412", "1:23.456" und "1:23,456".
PATTERN = re.compile(r"^\s*(?:(\d{1,2}):)?(\d{1,3})(?:[.,](\d{1,3}))?\s*$")


class TimeFormatError(ValueError):
    """Nicht interpretierbare Zeitangabe in einer Eingabe."""


def parse_time_to_ms(value):
    """Wandelt eine Zeitangabe in Millisekunden um.

    Ganzzahlen werden als Millisekunden uebernommen, damit API-Clients Zeiten
    auch numerisch uebergeben koennen.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        if value <= 0:
            raise TimeFormatError("Zeitangabe muss groesser als 0 sein.")
        return value

    match = PATTERN.match(str(value))
    if not match:
        raise TimeFormatError(f"Zeitangabe '{value}' entspricht nicht dem Format m:ss.mmm.")

    minutes = int(match.group(1) or 0)
    seconds = int(match.group(2))
    if minutes and seconds >= 60:
        raise TimeFormatError("Bei angegebener Minute muss der Sekundenanteil unter 60 liegen.")

    # "4" bedeutet 400 ms, "41" bedeutet 410 ms, "412" bedeutet 412 ms.
    millis = int((match.group(3) or "0").ljust(3, "0"))

    total = (minutes * 60 + seconds) * 1000 + millis
    if total <= 0:
        raise TimeFormatError("Zeitangabe muss groesser als 0 sein.")
    return total


def format_ms(ms):
    """Formatiert Millisekunden als "m:ss.mmm"."""
    if ms is None:
        return "-"
    minutes, rest = divmod(int(ms), 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def format_sector(ms):
    """Formatiert eine Sektorzeit, unter einer Minute ohne Minutenanteil."""
    if ms is None:
        return "-"
    if abs(int(ms)) < 60_000:
        seconds, millis = divmod(abs(int(ms)), 1000)
        return f"{'-' if ms < 0 else ''}{seconds}.{millis:03d}"
    return format_ms(ms)


def format_gap(ms):
    """Formatiert eine Zeitdifferenz mit Vorzeichen."""
    if ms is None:
        return "-"
    return ("+" if ms >= 0 else "-") + format_sector(abs(int(ms)))
