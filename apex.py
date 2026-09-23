"""Einstiegspunkt der Applikation.

    flask run                            Entwicklungsserver
    gunicorn -b 0.0.0.0:8000 apex:app    Betrieb
"""
from app import app, db
from app.models import User, Track, TrackSession, Lap


@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User, 'Track': Track,
            'TrackSession': TrackSession, 'Lap': Lap}
