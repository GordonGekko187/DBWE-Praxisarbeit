"""Eigene Fehlerseiten. Unter /api/ gibt's statt HTML JSON zurueck."""
from flask import render_template, request

from app import app, db
from app.api import error_response


def wants_json():
    return request.path.startswith('/api/')


@app.errorhandler(404)
def not_found_error(error):
    if wants_json():
        return error_response(404)
    return render_template('errors/404.html', title='Nicht gefunden'), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    if wants_json():
        return error_response(500)
    return render_template('errors/500.html', title='Fehler'), 500
