"""Fachlogik: Plausibilisierung und Auswertung von Runden.

Eigene Geschaeftslogik der Applikation:
* validate_lap      Regelwerk V1 bis V3 fuer eine erfasste Runde
* analyse_session   Bestzeit, Sektorbestzeiten, theoretische Bestzeit, Streuung
* record_lap        Runde erfassen, Bestzeit erkennen (Web und API rufen dieselbe Funktion)
* leaderboard       Rangliste einer Strecke ueber alle Benutzer

Die Funktionen validate_lap und analyse_session brauchen weder Flask noch eine
Datenbank und lassen sich deshalb direkt mit unittest pruefen.
"""
from statistics import stdev

import sqlalchemy as sa

from app import db
from app.models import User, Lap, TrackSession

# Grenzwerte der Plausibilisierung
MIN_SECTOR_MS = 2000    # V1: kuerzere Sektorzeiten entstehen nur durch Messfehler
MIN_FACTOR = 0.65       # V2: untere Grenze relativ zur Streckenreferenz
MAX_FACTOR = 2.50       # V3: obere Grenze relativ zur Streckenreferenz


def validate_lap(sectors, reference_lap_ms, lap_type='flying'):
    """Prueft eine Runde und liefert (total_ms, is_valid, reason).

    V1  Jede Sektorzeit betraegt mindestens 2000 ms.
    V2  Die Rundenzeit betraegt mindestens 65 Prozent der Streckenreferenz.
    V3  Die Rundenzeit betraegt hoechstens 250 Prozent der Streckenreferenz.
    V2 und V3 gelten nur fuer fliegende Runden; Out- und In-Laps sind durch
    Boxenaus- und -einfahrt systematisch langsamer.
    """
    total = int(sum(sectors))
    for nr, sector in enumerate(sectors, start=1):
        if sector < MIN_SECTOR_MS:
            return total, False, f'Sektor {nr} unter {MIN_SECTOR_MS} ms (V1)'
    if lap_type == 'flying':
        if total < reference_lap_ms * MIN_FACTOR:
            return total, False, 'Rundenzeit unter 65 % der Streckenreferenz (V2)'
        if total > reference_lap_ms * MAX_FACTOR:
            return total, False, 'Rundenzeit ueber 250 % der Streckenreferenz (V3)'
    return total, True, None


def analyse_session(laps):
    """Wertet die Runden einer Session aus und liefert die Kennzahlen als dict.

    Gewertet werden nur gueltige fliegende Runden. Die theoretische Bestzeit
    ist die Summe der schnellsten Sektorzeiten; die Differenz zur real
    gefahrenen Bestzeit ist das noch nicht abgerufene Potenzial. Der
    Konsistenzindex setzt die Standardabweichung ins Verhaeltnis zum
    Mittelwert (0 bis 100) und ist damit streckenunabhaengig lesbar.
    """
    counted = [lap for lap in laps if lap.counts]
    result = {'lap_count': len(laps), 'counted_laps': len(counted),
              'best_lap_ms': None, 'best_lap_number': None, 'sector_bests': {},
              'ideal_lap_ms': None, 'ideal_sources': [], 'potential_ms': None,
              'mean_ms': None, 'stdev_ms': None, 'spread_ms': None,
              'consistency_index': None}
    if not counted:
        return result

    best = min(counted, key=lambda lap: lap.total_ms)
    result['best_lap_ms'] = best.total_ms
    result['best_lap_number'] = best.lap_number

    for nr in (1, 2, 3):
        fastest = min(counted, key=lambda lap: lap.sectors[nr - 1])
        result['sector_bests'][nr] = fastest.sectors[nr - 1]
        result['ideal_sources'].append(fastest.lap_number)
    result['ideal_lap_ms'] = sum(result['sector_bests'].values())
    result['potential_ms'] = best.total_ms - result['ideal_lap_ms']

    times = [lap.total_ms for lap in counted]
    result['mean_ms'] = round(sum(times) / len(times))
    result['spread_ms'] = max(times) - min(times)
    if len(times) >= 2:
        deviation = stdev(times)
        result['stdev_ms'] = round(deviation)
        index = 100 * (1 - deviation / result['mean_ms'])
        result['consistency_index'] = round(max(0.0, min(100.0, index)), 1)
    return result


def personal_best_ms(user_id, track_id):
    """Schnellste gueltige fliegende Runde eines Benutzers auf einer Strecke."""
    return db.session.scalar(
        sa.select(sa.func.min(Lap.total_ms))
        .join(TrackSession, Lap.session_id == TrackSession.id)
        .where(TrackSession.user_id == user_id, TrackSession.track_id == track_id,
               Lap.is_valid == True, Lap.lap_type == 'flying'))  # noqa: E712


def record_lap(session, sectors, lap_type='flying'):
    """Erfasst eine Runde und liefert (lap, is_new_personal_best, previous_best_ms).

    Eine unplausible Runde wird nicht abgewiesen, sondern gespeichert, als
    ungueltig markiert und begruendet. Die Rohdaten bleiben damit vollstaendig.
    """
    total, is_valid, reason = validate_lap(sectors, session.track.reference_lap_ms, lap_type)
    previous_best = personal_best_ms(session.user_id, session.track_id)
    lap = Lap(session=session, lap_number=session.next_lap_number,
              sector1_ms=sectors[0], sector2_ms=sectors[1], sector3_ms=sectors[2],
              total_ms=total, lap_type=lap_type, is_valid=is_valid, invalid_reason=reason)
    db.session.add(lap)
    db.session.commit()
    is_new_best = lap.counts and (previous_best is None or lap.total_ms < previous_best)
    return lap, is_new_best, previous_best


def leaderboard(track_id):
    """Rangliste einer Strecke: ein Eintrag je Benutzer mit Bestzeit und Rueckstand.

    Die Bestzeit je Benutzer wird als Aggregat (MIN, GROUP BY) in der Datenbank
    ermittelt; der Join liefert Benutzername, Fahrzeug und Datum der Bestrunde.
    """
    best_per_user = (
        sa.select(TrackSession.user_id.label('user_id'), sa.func.min(Lap.total_ms).label('best_ms'))
        .join(Lap, Lap.session_id == TrackSession.id)
        .where(TrackSession.track_id == track_id, Lap.is_valid == True, Lap.lap_type == 'flying')  # noqa: E712
        .group_by(TrackSession.user_id).subquery())
    rows = db.session.execute(
        sa.select(User.username, TrackSession.car, Lap.total_ms, TrackSession.session_date)
        .join(TrackSession, TrackSession.id == Lap.session_id)
        .join(User, User.id == TrackSession.user_id)
        .join(best_per_user, (best_per_user.c.user_id == TrackSession.user_id)
              & (best_per_user.c.best_ms == Lap.total_ms))
        .where(TrackSession.track_id == track_id)
        .order_by(Lap.total_ms, TrackSession.session_date)).all()

    entries, seen = [], set()
    for username, car, total_ms, session_date in rows:
        if username in seen:      # dieselbe Zeit kann mehrfach gefahren worden sein
            continue
        seen.add(username)
        entries.append({'rank': len(entries) + 1, 'username': username, 'car': car,
                        'total_ms': total_ms,
                        'gap_ms': total_ms - entries[0]['total_ms'] if entries else 0,
                        'date': session_date})
    return entries
