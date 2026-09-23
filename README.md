# APEX Trackday Log

Webapplikation zur Erfassung und Auswertung von Rundenzeiten auf Rennstrecken.
Praxisarbeit DBWE.

Stack: Python 3.12, Flask 3 (Flask-SQLAlchemy, Flask-Migrate, Flask-Login,
Flask-WTF, Flask-HTTPAuth, Bootstrap-Flask), PostgreSQL 16, Gunicorn.

## Betrieb auf einem Linux-Server

Voraussetzung: Ubuntu-Server mit Python 3.12 und PostgreSQL 16.

```bash
# Systempakete
sudo apt update && sudo apt install -y python3-venv postgresql

# Datenbank und Benutzer anlegen (einmalig)
sudo -u postgres psql -c "CREATE DATABASE apex;"
sudo -u postgres psql -c "CREATE USER apex WITH PASSWORD 'bitte-ersetzen';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE apex TO apex;"
 # Ab PostgreSQL 15 zwingend: ohne dieses Recht schlaegt flask db upgrade fehl
sudo -u postgres psql -d apex -c "GRANT ALL ON SCHEMA public TO apex;"

# Applikation
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # SECRET_KEY und DATABASE_URL anpassen
flask db upgrade                # Schema anlegen
flask seed                      # Strecken und Demokonto anlegen
gunicorn -b 0.0.0.0:8000 --workers 3 apex:app
```

Für den Dauerbetrieb läuft Gunicorn nicht im Terminal, sondern als
systemd-Service mit `Restart=always`; optional steht ein Nginx als
Reverse Proxy davor (Konfiguration siehe Loesungsdokument, Kapitel 7.4).

Applikation: `http://<host>:8000/`, Demokonto `demo` / `Trackday2026!`.

## Lokale Entwicklung und Tests

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
flask db upgrade        # ohne DATABASE_URL: SQLite-Datei app.db
flask seed
flask run
python tests.py
```

## API (ohne Browser)

```bash
TOKEN=$(curl -s -u demo:'Trackday2026!' -X POST http://<host>:8000/api/tokens | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -H "Authorization: Bearer $TOKEN" http://<host>:8000/api/sessions/1
curl -H "Authorization: Bearer $TOKEN" http://<host>:8000/api/tracks/hockenheim-gp/leaderboard
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"sectors": ["40.100", "51.200", "37.800"], "lap_type": "flying"}' \
     http://<host>:8000/api/sessions/1/laps
```

Alle Endpunkte: siehe Kopf von `app/api.py` bzw. Kapitel API im Loesungsdokument.

## Aufbau

```
apex.py            Einstiegspunkt (FLASK_APP)
config.py          Konfiguration aus Umgebungsvariablen / .env
app/__init__.py    Flask-App und Erweiterungen
app/models.py      Datenmodell User, Track, TrackSession, Lap
app/analysis.py    Fachlogik: Regelwerk V1-V3, Auswertung, Rangliste
app/timeformat.py  Zeitnotation m:ss.mmm <-> Millisekunden
app/forms.py       Formulare (Flask-WTF)
app/routes.py      View-Funktionen der Weboberflaeche
app/api.py         RESTful Web-API mit Token-Authentisierung
app/errors.py      Fehlerseiten 404/500
app/cli.py         Kommando flask seed
migrations/        Datenbankmigrationen (Flask-Migrate/Alembic)
tests.py           Testsuite (unittest)
```
