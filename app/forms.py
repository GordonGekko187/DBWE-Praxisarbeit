"""Formulare der Weboberflaeche (Flask-WTF).

Flask-WTF uebernimmt Feldvalidierung und CSRF-Schutz. Die fachliche
Plausibilisierung der Runden passiert danach in analysis.py.
"""
import sqlalchemy as sa
from flask_wtf import FlaskForm
from wtforms import (StringField, PasswordField, BooleanField, SubmitField,
                     SelectField, DateField, TextAreaField)
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional

from app import db
from app.models import User, Track, TrackSession, Lap
from app.timeformat import parse_time_to_ms, TimeFormatError


class LoginForm(FlaskForm):
    username = StringField('Benutzername', validators=[DataRequired()])
    password = PasswordField('Passwort', validators=[DataRequired()])
    remember_me = BooleanField('Angemeldet bleiben')
    submit = SubmitField('Anmelden')


class RegistrationForm(FlaskForm):
    username = StringField('Benutzername', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('E-Mail', validators=[DataRequired(), Email()])
    password = PasswordField('Passwort', validators=[DataRequired(), Length(min=8)])
    password2 = PasswordField('Passwort wiederholen',
                              validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Registrieren')

    def validate_username(self, username):
        if db.session.scalar(sa.select(User).where(User.username == username.data)):
            raise ValidationError('Dieser Benutzername ist bereits vergeben.')

    def validate_email(self, email):
        if db.session.scalar(sa.select(User).where(User.email == email.data)):
            raise ValidationError('Diese E-Mail-Adresse ist bereits registriert.')


class SessionForm(FlaskForm):
    track_id = SelectField('Strecke', coerce=int)
    session_date = DateField('Datum', validators=[DataRequired()])
    car = StringField('Fahrzeug', validators=[DataRequired(), Length(max=64)])
    track_condition = SelectField('Streckenzustand', choices=TrackSession.CONDITIONS)
    notes = TextAreaField('Notizen', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Session anlegen')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tracks = db.session.scalars(sa.select(Track).order_by(Track.name)).all()
        self.track_id.choices = [(t.id, t.name) for t in tracks]


class LapTimeField(StringField):
    """Zeitfeld in der Notation m:ss.mmm; der Wert wird in Millisekunden umgewandelt."""

    def process_formdata(self, valuelist):
        self.data = None
        if valuelist and valuelist[0].strip():
            try:
                self.data = parse_time_to_ms(valuelist[0].strip())
            except TimeFormatError as e:
                # WTForms zeigt einen ValueError als Feldfehler an.
                raise ValueError(str(e))


class LapForm(FlaskForm):
    sector1 = LapTimeField('Sektor 1', validators=[DataRequired()])
    sector2 = LapTimeField('Sektor 2', validators=[DataRequired()])
    sector3 = LapTimeField('Sektor 3', validators=[DataRequired()])
    lap_type = SelectField('Rundentyp', choices=Lap.TYPES, default='flying')
    submit = SubmitField('Runde erfassen')

    def sectors(self):
        return (self.sector1.data, self.sector2.data, self.sector3.data)
