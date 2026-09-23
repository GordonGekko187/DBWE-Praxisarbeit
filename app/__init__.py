"""APEX Trackday Log - Flask-Applikation.

Ein globales app-Objekt, die Erweiterungen werden hier initialisiert. Routen
und Modelle werden erst am Ende importiert, weil sie selbst wieder auf app
und db zugreifen - sonst gibt's einen Importzirkel.
"""
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_bootstrap import Bootstrap5
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login = LoginManager(app)
login.login_view = 'login'
login.login_message = 'Bitte zuerst anmelden.'
bootstrap = Bootstrap5(app)

from app import routes, api, errors, models, cli  # noqa: E402,F401
