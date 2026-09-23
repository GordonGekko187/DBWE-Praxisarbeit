"""RESTful Web-API (Flask-HTTPAuth).

Das API ist zustandslos und verwendet keine Cookies. Ein Client bezieht mit
Benutzername und Passwort (HTTP Basic) ein Token und sendet es danach als
Bearer-Token im Authorization-Header mit. Alle Antworten sind JSON.

    POST   /api/tokens                       Token beziehen (HTTP Basic)
    DELETE /api/tokens                       Token widerrufen
    GET    /api/tracks                       alle Strecken
    GET    /api/tracks/<slug>/leaderboard    Rangliste einer Strecke
    GET    /api/sessions                     eigene Sessions
    GET    /api/sessions/<id>                Session mit Auswertung
    GET    /api/sessions/<id>/laps           Runden einer Session
    POST   /api/sessions/<id>/laps           Runde erfassen (JSON-Body)
"""
import sqlalchemy as sa
from flask import jsonify, request
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth
from werkzeug.http import HTTP_STATUS_CODES

from app import app, db
from app import analysis
from app.models import User, Track, TrackSession, Lap
from app.timeformat import parse_time_to_ms, format_ms, format_sector, TimeFormatError

basic_auth = HTTPBasicAuth()
token_auth = HTTPTokenAuth()


# --- Fehlerantworten und Authentisierung ---------------------------------
def error_response(status_code, message=None):
    payload = {'error': HTTP_STATUS_CODES.get(status_code, 'Unknown error')}
    if message:
        payload['message'] = message
    return jsonify(payload), status_code


def bad_request(message):
    return error_response(400, message)


@basic_auth.verify_password
def verify_password(username, password):
    user = db.session.scalar(sa.select(User).where(User.username == username))
    if user and user.check_password(password):
        return user


@basic_auth.error_handler
def basic_auth_error(status):
    return error_response(status)


@token_auth.verify_token
def verify_token(token):
    return User.check_token(token) if token else None


@token_auth.error_handler
def token_auth_error(status):
    return error_response(status)


# --- Token ---------------------------------------------------------------
@app.route('/api/tokens', methods=['POST'])
@basic_auth.login_required
def get_token():
    token = basic_auth.current_user().get_token()
    db.session.commit()
    return jsonify({'token': token})


@app.route('/api/tokens', methods=['DELETE'])
@token_auth.login_required
def revoke_token():
    token_auth.current_user().revoke_token()
    db.session.commit()
    return '', 204


# --- Strecken ------------------------------------------------------------
@app.route('/api/tracks', methods=['GET'])
@token_auth.login_required
def get_tracks():
    tracks = db.session.scalars(sa.select(Track).order_by(Track.name)).all()
    return jsonify({'items': [t.to_dict() for t in tracks]})


@app.route('/api/tracks/<slug>/leaderboard', methods=['GET'])
@token_auth.login_required
def get_leaderboard(slug):
    track = db.session.scalar(sa.select(Track).where(Track.slug == slug))
    if track is None:
        return error_response(404)
    entries = []
    for e in analysis.leaderboard(track.id):
        entries.append({**e, 'date': e['date'].isoformat(), 'total': format_ms(e['total_ms'])})
    return jsonify({'track': track.to_dict(), 'entries': entries})


# --- Sessions und Runden -------------------------------------------------
def own_session_or_404(session_id):
    session = db.session.get(TrackSession, session_id)
    if session is None or session.user_id != token_auth.current_user().id:
        return None
    return session


def analysis_to_dict(result):
    """Kennzahlen als JSON, Zeiten zusaetzlich formatiert fuer die Lesbarkeit."""
    return {**result, 'best_lap': format_ms(result['best_lap_ms']),
            'ideal_lap': format_ms(result['ideal_lap_ms']),
            'potential': format_sector(result['potential_ms'])}


@app.route('/api/sessions', methods=['GET'])
@token_auth.login_required
def get_sessions():
    sessions = db.session.scalars(
        sa.select(TrackSession).where(TrackSession.user_id == token_auth.current_user().id)
        .order_by(TrackSession.session_date.desc())).all()
    return jsonify({'items': [s.to_dict() for s in sessions]})


@app.route('/api/sessions/<int:session_id>', methods=['GET'])
@token_auth.login_required
def get_session(session_id):
    session = own_session_or_404(session_id)
    if session is None:
        return error_response(404)
    data = session.to_dict()
    data['analysis'] = analysis_to_dict(analysis.analyse_session(session.laps))
    return jsonify(data)


@app.route('/api/sessions/<int:session_id>/laps', methods=['GET'])
@token_auth.login_required
def get_laps(session_id):
    session = own_session_or_404(session_id)
    if session is None:
        return error_response(404)
    return jsonify({'session_id': session.id, 'items': [lap.to_dict() for lap in session.laps]})


@app.route('/api/sessions/<int:session_id>/laps', methods=['POST'])
@token_auth.login_required
def create_lap(session_id):
    """Runde erfassen. Body: {"sectors": ["40.100", "51.200", "37.800"], "lap_type": "flying"}"""
    session = own_session_or_404(session_id)
    if session is None:
        return error_response(404)
    data = request.get_json(silent=True) or {}
    sectors = data.get('sectors')
    if not isinstance(sectors, list) or len(sectors) != 3:
        return bad_request("Feld 'sectors' muss eine Liste mit genau drei Zeitangaben sein.")
    try:
        sectors = [parse_time_to_ms(s) for s in sectors]
    except TimeFormatError as e:
        return bad_request(str(e))
    lap_type = data.get('lap_type', 'flying')
    if lap_type not in dict(Lap.TYPES):
        return bad_request("Feld 'lap_type' muss 'flying', 'out' oder 'in' sein.")
    lap, is_new_best, previous_best = analysis.record_lap(session, sectors, lap_type)
    payload = lap.to_dict()
    payload['is_new_personal_best'] = is_new_best
    return jsonify(payload), 201
