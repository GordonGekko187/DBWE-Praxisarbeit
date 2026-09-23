"""Datenmodell (Flask-SQLAlchemy mit der Mapped/mapped_column-Notation).

Alle Zeiten sind ganzzahlige Millisekunden. Damit sind Vergleiche, Summen
und Sortierungen exakt und es gibt keine Rundungsfehler durch Gleitkommazahlen.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional
import secrets

import sqlalchemy as sa
import sqlalchemy.orm as so
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db, login


class User(UserMixin, db.Model):
    """Benutzerkonto mit Passwort-Login und API-Token."""
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    username: so.Mapped[str] = so.mapped_column(sa.String(64), index=True, unique=True)
    email: so.Mapped[str] = so.mapped_column(sa.String(120), index=True, unique=True)
    password_hash: so.Mapped[Optional[str]] = so.mapped_column(sa.String(256))
    # API-Token mit Ablaufzeitpunkt
    token: so.Mapped[Optional[str]] = so.mapped_column(sa.String(32), index=True, unique=True)
    token_expiration: so.Mapped[Optional[datetime]]

    sessions: so.WriteOnlyMapped['TrackSession'] = so.relationship(back_populates='driver')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_token(self, expires_in=3600 * 24 * 30):
        """Liefert das gueltige Token oder erzeugt ein neues (30 Tage gueltig)."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if self.token and self.token_expiration.replace(tzinfo=None) > now + timedelta(seconds=60):
            return self.token
        self.token = secrets.token_hex(16)
        self.token_expiration = now + timedelta(seconds=expires_in)
        db.session.add(self)
        return self.token

    def revoke_token(self):
        self.token_expiration = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)

    @staticmethod
    def check_token(token):
        user = db.session.scalar(sa.select(User).where(User.token == token))
        if user is None or user.token_expiration.replace(tzinfo=None) < datetime.now(timezone.utc).replace(tzinfo=None):
            return None
        return user

    def to_dict(self):
        return {'id': self.id, 'username': self.username}

    def __repr__(self):
        return f'<User {self.username}>'


@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))


class Track(db.Model):
    """Rennstrecke als gemeinsame Referenz aller Benutzer.

    reference_lap_ms ist ein Richtwert und dient der Plausibilisierung
    erfasster Rundenzeiten (Regeln V2 und V3 in analysis.py).
    """
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    slug: so.Mapped[str] = so.mapped_column(sa.String(48), unique=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(96))
    country: so.Mapped[str] = so.mapped_column(sa.String(2))
    length_m: so.Mapped[int]
    reference_lap_ms: so.Mapped[int]

    sessions: so.WriteOnlyMapped['TrackSession'] = so.relationship(back_populates='track')

    def to_dict(self):
        return {'slug': self.slug, 'name': self.name, 'country': self.country,
                'length_m': self.length_m, 'reference_lap_ms': self.reference_lap_ms}

    def __repr__(self):
        return f'<Track {self.slug}>'


class TrackSession(db.Model):
    """Ein Turn eines Benutzers auf einer Strecke.

    Der Klassenname lautet nicht 'Session', um Verwechslungen mit der
    Flask-Session und der SQLAlchemy-Session zu vermeiden.
    """
    __tablename__ = 'track_session'
    CONDITIONS = [('dry', 'trocken'), ('damp', 'feucht'), ('wet', 'nass')]

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id), index=True)
    track_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Track.id), index=True)
    session_date: so.Mapped[date] = so.mapped_column(default=date.today)
    car: so.Mapped[str] = so.mapped_column(sa.String(64))
    track_condition: so.Mapped[str] = so.mapped_column(sa.String(8), default='dry')
    notes: so.Mapped[Optional[str]] = so.mapped_column(sa.String(500))

    driver: so.Mapped[User] = so.relationship(back_populates='sessions')
    track: so.Mapped[Track] = so.relationship(back_populates='sessions')
    laps: so.Mapped[list['Lap']] = so.relationship(
        back_populates='session', cascade='all, delete-orphan', order_by='Lap.lap_number')

    @property
    def condition_label(self):
        return dict(self.CONDITIONS).get(self.track_condition, self.track_condition)

    @property
    def next_lap_number(self):
        return max([lap.lap_number for lap in self.laps], default=0) + 1

    def to_dict(self):
        return {'id': self.id, 'date': self.session_date.isoformat(),
                'track': self.track.slug, 'car': self.car,
                'track_condition': self.track_condition, 'lap_count': len(self.laps),
                '_links': {'self': f'/api/sessions/{self.id}',
                           'laps': f'/api/sessions/{self.id}/laps'}}

    def __repr__(self):
        return f'<TrackSession {self.id} {self.session_date}>'


class Lap(db.Model):
    """Einzelne Runde mit drei Sektorzeiten.

    total_ms wird beim Erfassen aus den Sektorzeiten berechnet und gespeichert.
    Die Redundanz ist beabsichtigt: Bestzeiten und Ranglisten werden damit als
    Aggregat (MIN, GROUP BY) in der Datenbank ermittelt, nicht in Python.
    """
    TYPES = [('flying', 'fliegende Runde'), ('out', 'Out-Lap'), ('in', 'In-Lap')]

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    session_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(TrackSession.id), index=True)
    lap_number: so.Mapped[int]
    sector1_ms: so.Mapped[int]
    sector2_ms: so.Mapped[int]
    sector3_ms: so.Mapped[int]
    total_ms: so.Mapped[int] = so.mapped_column(index=True)
    lap_type: so.Mapped[str] = so.mapped_column(sa.String(8), default='flying')
    is_valid: so.Mapped[bool] = so.mapped_column(default=True)
    invalid_reason: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120))

    session: so.Mapped[TrackSession] = so.relationship(back_populates='laps')

    __table_args__ = (sa.UniqueConstraint('session_id', 'lap_number'),)

    @property
    def sectors(self):
        return (self.sector1_ms, self.sector2_ms, self.sector3_ms)

    @property
    def type_label(self):
        return dict(self.TYPES).get(self.lap_type, self.lap_type)

    @property
    def counts(self):
        """Nur gueltige fliegende Runden gehen in die Auswertung ein."""
        return self.is_valid and self.lap_type == 'flying'

    def to_dict(self):
        from app.timeformat import format_ms
        return {'lap_number': self.lap_number, 'lap_type': self.lap_type,
                'sectors_ms': list(self.sectors), 'total_ms': self.total_ms,
                'total': format_ms(self.total_ms), 'is_valid': self.is_valid,
                'invalid_reason': self.invalid_reason}

    def __repr__(self):
        return f'<Lap {self.lap_number} {self.total_ms} ms>'
