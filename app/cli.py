"""Kommando 'flask seed': Streckendaten und Demokonto anlegen (mehrfach ausfuehrbar)."""
from datetime import date

import click
import sqlalchemy as sa

from app import app, db
from app.models import User, Track, TrackSession
from app.analysis import record_lap

# slug, Name, Land, Laenge in m, Referenzrunde in ms (Richtwert fuer V2/V3)
TRACKS = [
    ('hockenheim-gp', 'Hockenheimring GP', 'DE', 4574, 125000),
    ('nuerburgring-gp', 'Nuerburgring GP', 'DE', 5148, 122000),
    ('bilster-berg', 'Bilster Berg', 'DE', 4200, 125000),
    ('anneau-du-rhin', 'Anneau du Rhin', 'FR', 3700, 112000),
    ('red-bull-ring', 'Red Bull Ring', 'AT', 4318, 105000),
]

# Demorunden: Out-Lap, fuenf fliegende Runden, eine ungueltige Runde (V1), In-Lap
DEMO_LAPS = [
    ((55000, 62000, 48000), 'out'),
    ((41200, 52800, 38900), 'flying'),
    ((40500, 51900, 38100), 'flying'),
    ((40100, 51200, 37800), 'flying'),
    ((39800, 51500, 37900), 'flying'),
    ((40300, 51000, 38400), 'flying'),
    ((1500, 51000, 38000), 'flying'),
    ((48000, 58000, 52000), 'in'),
]


@app.cli.command('seed')
def seed():
    """Streckendaten laden und Demokonto (demo / Trackday2026!) erzeugen."""
    added = 0
    for slug, name, country, length_m, reference in TRACKS:
        if db.session.scalar(sa.select(Track).where(Track.slug == slug)) is None:
            db.session.add(Track(slug=slug, name=name, country=country,
                                 length_m=length_m, reference_lap_ms=reference))
            added += 1
    db.session.commit()
    click.echo(f'{added} Strecken ergaenzt.')

    if db.session.scalar(sa.select(User).where(User.username == 'demo')):
        click.echo('Demokonto existiert bereits.')
        return
    user = User(username='demo', email='demo@example.ch')
    user.set_password('Trackday2026!')
    track = db.session.scalar(sa.select(Track).where(Track.slug == 'hockenheim-gp'))
    session = TrackSession(driver=user, track=track, session_date=date(2026, 5, 12),
                           car='BMW M2 (F87)', track_condition='dry',
                           notes='Demodaten: Out-Lap, fuenf gewertete Runden, eine ungueltige Runde, In-Lap')
    db.session.add_all([user, session])
    db.session.commit()
    for sectors, lap_type in DEMO_LAPS:
        record_lap(session, sectors, lap_type)
    click.echo("Demokonto 'demo' mit Passwort 'Trackday2026!' erstellt.")
