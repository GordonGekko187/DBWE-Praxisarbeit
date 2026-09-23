"""View-Funktionen der Weboberflaeche.

Alle Ansichten mit Benutzerdaten sind mit @login_required geschuetzt. Bei
Sessions wird zusaetzlich geprueft, ob sie dem angemeldeten Benutzer gehoeren;
fremde Sessions liefern 404, damit man ihre Existenz nicht erraten kann.
"""
from datetime import date
from urllib.parse import urlsplit

import sqlalchemy as sa
from flask import render_template, flash, redirect, url_for, request, abort
from flask_login import current_user, login_user, logout_user, login_required

from app import app, db
from app.forms import LoginForm, RegistrationForm, SessionForm, LapForm
from app.models import User, Track, TrackSession
from app import analysis
from app.timeformat import format_ms, format_sector, format_gap

# Jinja-Filter fuer die Anzeige von Millisekunden
app.jinja_env.filters['laptime'] = format_ms
app.jinja_env.filters['sectortime'] = format_sector
app.jinja_env.filters['gap'] = format_gap


def own_session(session_id):
    session = db.session.get(TrackSession, session_id)
    if session is None or session.user_id != current_user.id:
        abort(404)
    return session


@app.route('/')
@app.route('/index')
def index():
    """Startseite: fuer angemeldete Benutzer die Liste der eigenen Sessions."""
    if not current_user.is_authenticated:
        return render_template('index.html', title='Start')
    sessions = db.session.scalars(
        sa.select(TrackSession).where(TrackSession.user_id == current_user.id)
        .order_by(TrackSession.session_date.desc(), TrackSession.id.desc())).all()
    return render_template('sessions.html', title='Meine Sessions', sessions=sessions)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(sa.select(User).where(User.username == form.username.data))
        # Einheitliche Meldung: es wird nicht offengelegt, ob nur das Passwort falsch war.
        if user is None or not user.check_password(form.password.data):
            flash('Benutzername oder Passwort ist falsch.', 'danger')
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    return render_template('login.html', title='Anmelden', form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Konto erstellt. Bitte anmelden.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Registrieren', form=form)


@app.route('/sessions/new', methods=['GET', 'POST'])
@login_required
def session_new():
    form = SessionForm()
    if request.method == 'GET':
        form.session_date.data = date.today()
    if form.validate_on_submit():
        session = TrackSession(driver=current_user, track_id=form.track_id.data,
                               session_date=form.session_date.data, car=form.car.data,
                               track_condition=form.track_condition.data,
                               notes=form.notes.data or None)
        db.session.add(session)
        db.session.commit()
        flash('Session angelegt. Runden koennen jetzt erfasst werden.', 'success')
        return redirect(url_for('session_detail', session_id=session.id))
    return render_template('session_form.html', title='Neue Session', form=form)


@app.route('/sessions/<int:session_id>', methods=['GET', 'POST'])
@login_required
def session_detail(session_id):
    """Rundentabelle, Auswertung und Erfassungsformular einer Session."""
    session = own_session(session_id)
    form = LapForm()
    if form.validate_on_submit():
        lap, is_new_best, previous_best = analysis.record_lap(
            session, form.sectors(), lap_type=form.lap_type.data)
        if not lap.is_valid:
            flash(f'Runde {lap.lap_number} erfasst, aber ungueltig: {lap.invalid_reason}', 'warning')
        elif is_new_best:
            bisher = f' (bisher {format_ms(previous_best)})' if previous_best else ''
            flash(f'Neue persoenliche Bestzeit: {format_ms(lap.total_ms)}{bisher}', 'success')
        else:
            flash(f'Runde {lap.lap_number} erfasst: {format_ms(lap.total_ms)}', 'success')
        return redirect(url_for('session_detail', session_id=session.id))
    return render_template('session_detail.html', title=session.track.name, session=session,
                           result=analysis.analyse_session(session.laps), form=form)


@app.route('/tracks')
def tracks():
    tracks = db.session.scalars(sa.select(Track).order_by(Track.name)).all()
    return render_template('tracks.html', title='Strecken', tracks=tracks)


@app.route('/tracks/<slug>')
def track_detail(slug):
    """Rangliste einer Strecke ueber alle Benutzer."""
    track = db.session.scalar(sa.select(Track).where(Track.slug == slug))
    if track is None:
        abort(404)
    return render_template('track_detail.html', title=track.name, track=track,
                           entries=analysis.leaderboard(track.id))
