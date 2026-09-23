"""Konfiguration der Applikation.

Alle Werte kommen aus Umgebungsvariablen bzw. aus der Datei .env. Dadurch
laeuft derselbe Code lokal, in der Testsuite und auf dem Server, ohne dass
am Code etwas geaendert werden muss.
"""
import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'nur-fuer-die-entwicklung'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db')
    # Verbindungen vor Gebrauch pruefen; verhindert Fehler, wenn Postgres
    # zwischenzeitlich neu gestartet wurde oder die Verbindung gekappt hat.
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
