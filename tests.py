"""Testsuite (unittest).

Ausfuehren:  python tests.py
Die Tests laufen gegen eine SQLite-Datenbank im Arbeitsspeicher. Die
Kennungen T-01 bis T-12 verweisen auf das Testprotokoll im Loesungsdokument.
"""
import os
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'test'

import unittest  # noqa: E402
from datetime import date  # noqa: E402

from app import app, db  # noqa: E402
from app.models import User, Track, TrackSession, Lap  # noqa: E402
from app.analysis import validate_lap, analyse_session, record_lap, leaderboard  # noqa: E402
from app.timeformat import parse_time_to_ms, format_ms, TimeFormatError  # noqa: E402

PASSWORD = 'Trackday2026!'


def lap(sectors, number, lap_type='flying', is_valid=True):
    """Nicht persistiertes Lap-Objekt fuer Tests der Fachlogik."""
    return Lap(lap_number=number, sector1_ms=sectors[0], sector2_ms=sectors[1],
               sector3_ms=sectors[2], total_ms=sum(sectors), lap_type=lap_type,
               is_valid=is_valid)


class AnalysisCase(unittest.TestCase):
    """Fachlogik ohne Datenbank und ohne Webserver."""

    def test_validate_lap_rules(self):
        """T-01: Regelwerk V1 bis V3."""
        ref = 125000
        self.assertEqual(validate_lap((40000, 51000, 38000), ref), (129000, True, None))
        total, valid, reason = validate_lap((1500, 51000, 38000), ref)
        self.assertFalse(valid)
        self.assertIn('V1', reason)
        self.assertIn('V2', validate_lap((20000, 20000, 20000), ref)[2])
        self.assertIn('V3', validate_lap((120000, 120000, 120000), ref)[2])

    def test_out_and_in_laps(self):
        """T-02: Out-/In-Laps werden nur gegen V1 geprueft und nicht gewertet."""
        total, valid, reason = validate_lap((120000, 120000, 120000), 125000, 'out')
        self.assertTrue(valid)
        result = analyse_session([lap((55000, 62000, 48000), 1, 'out'),
                                  lap((40000, 51000, 38000), 2)])
        self.assertEqual(result['counted_laps'], 1)
        self.assertEqual(result['best_lap_ms'], 129000)

    def test_ideal_lap(self):
        """T-03: Theoretische Bestzeit aus Sektorbestzeiten und Potenzial."""
        result = analyse_session([lap((40100, 51200, 37800), 1),
                                  lap((39800, 51500, 37900), 2),
                                  lap((40300, 51000, 38400), 3)])
        self.assertEqual(result['best_lap_ms'], 129100)
        self.assertEqual(result['sector_bests'], {1: 39800, 2: 51000, 3: 37800})
        self.assertEqual(result['ideal_lap_ms'], 128600)
        self.assertEqual(result['potential_ms'], 500)
        self.assertEqual(result['ideal_sources'], [2, 3, 1])

    def test_consistency(self):
        """T-04: Konsistenzindex, Standardabweichung und Spannweite."""
        result = analyse_session([lap((40000, 50000, 30000), 1),
                                  lap((40000, 50000, 31000), 2),
                                  lap((40000, 50000, 32000), 3)])
        self.assertEqual(result['mean_ms'], 121000)
        self.assertEqual(result['stdev_ms'], 1000)
        self.assertEqual(result['spread_ms'], 2000)
        self.assertEqual(result['consistency_index'], 99.2)
        self.assertIsNone(analyse_session([lap((40000, 50000, 30000), 1)])['stdev_ms'])

    def test_time_format(self):
        """T-05: Umwandlung der Zeitnotation."""
        self.assertEqual(parse_time_to_ms('1:23.456'), 83456)
        self.assertEqual(parse_time_to_ms('38.4'), 38400)
        self.assertEqual(parse_time_to_ms('38,412'), 38412)
        self.assertEqual(format_ms(129100), '2:09.100')
        with self.assertRaises(TimeFormatError):
            parse_time_to_ms('1:60.000')
        with self.assertRaises(TimeFormatError):
            parse_time_to_ms('abc')


class WebCase(unittest.TestCase):
    """Weboberflaeche und API mit dem Flask-Testclient."""

    def setUp(self):
        app.config['WTF_CSRF_ENABLED'] = False
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = app.test_client()
        self.track = Track(slug='hockenheim-gp', name='Hockenheimring GP', country='DE',
                           length_m=4574, reference_lap_ms=125000)
        self.user = User(username='marc', email='marc@example.ch')
        self.user.set_password(PASSWORD)
        db.session.add_all([self.track, self.user])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login(self, username='marc', password=PASSWORD):
        return self.client.post('/login', data={'username': username, 'password': password},
                                follow_redirects=True)

    def new_session(self, user=None):
        session = TrackSession(driver=user or self.user, track=self.track,
                               session_date=date(2026, 5, 12), car='BMW M2')
        db.session.add(session)
        db.session.commit()
        return session

    def bearer(self):
        response = self.client.post('/api/tokens', auth=('marc', PASSWORD))
        self.assertEqual(response.status_code, 200)
        return {'Authorization': 'Bearer ' + response.get_json()['token']}

    def test_register_duplicate(self):
        """T-06: Registrierung mit vergebenem Benutzernamen bzw. E-Mail."""
        response = self.client.post('/register', data={
            'username': 'marc', 'email': 'neu@example.ch',
            'password': PASSWORD, 'password2': PASSWORD})
        self.assertIn('bereits vergeben', response.get_data(as_text=True))
        response = self.client.post('/register', data={
            'username': 'neu', 'email': 'marc@example.ch',
            'password': PASSWORD, 'password2': PASSWORD})
        self.assertIn('bereits registriert', response.get_data(as_text=True))
        self.assertEqual(db.session.query(User).count(), 1)

    def test_register_and_password_hash(self):
        """T-07: Neues Konto, Passwort nur als Hash gespeichert."""
        self.client.post('/register', data={'username': 'anna', 'email': 'anna@example.ch',
                                            'password': PASSWORD, 'password2': PASSWORD})
        user = db.session.scalar(db.select(User).where(User.username == 'anna'))
        self.assertIsNotNone(user)
        self.assertNotEqual(user.password_hash, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(user.check_password('falsch'))

    def test_login_and_protection(self):
        """T-08: Falsches Passwort, geschuetzte Seite ohne Anmeldung."""
        response = self.login(password='falsch')
        self.assertIn('Benutzername oder Passwort ist falsch', response.get_data(as_text=True))
        response = self.client.get('/sessions/new')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

    def test_record_lap_in_browser(self):
        """T-09: Runde im Browser erfassen, plausibel und unplausibel."""
        self.login()
        session = self.new_session()
        response = self.client.post(f'/sessions/{session.id}', follow_redirects=True, data={
            'sector1': '40.100', 'sector2': '51.200', 'sector3': '37.800', 'lap_type': 'flying'})
        html = response.get_data(as_text=True)
        self.assertIn('Neue persoenliche Bestzeit: 2:09.100', html)
        response = self.client.post(f'/sessions/{session.id}', follow_redirects=True, data={
            'sector1': '1.500', 'sector2': '51.000', 'sector3': '38.000', 'lap_type': 'flying'})
        self.assertIn('ungueltig', response.get_data(as_text=True))
        laps = db.session.scalars(db.select(Lap).order_by(Lap.lap_number)).all()
        self.assertEqual(len(laps), 2)
        self.assertFalse(laps[1].is_valid)
        self.assertIn('V1', laps[1].invalid_reason)
        # fehlerhafte Notation: Feldfehler, kein Datensatz
        self.client.post(f'/sessions/{session.id}', data={
            'sector1': 'abc', 'sector2': '51.000', 'sector3': '38.000', 'lap_type': 'flying'})
        self.assertEqual(db.session.query(Lap).count(), 2)

    def test_other_users_session(self):
        """T-10: Fremde Session ist ueber Web und API nicht erreichbar."""
        other = User(username='anna', email='anna@example.ch')
        other.set_password(PASSWORD)
        db.session.add(other)
        db.session.commit()
        session = self.new_session(user=other)
        self.login()
        self.assertEqual(self.client.get(f'/sessions/{session.id}').status_code, 404)
        headers = self.bearer()
        self.assertEqual(self.client.get(f'/api/sessions/{session.id}', headers=headers).status_code, 404)
        response = self.client.post(f'/api/sessions/{session.id}/laps', headers=headers,
                                    json={'sectors': ['40.100', '51.200', '37.800']})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get('/api/sessions', headers=headers).get_json()['items'], [])

    def test_token(self):
        """T-11: Token beziehen, falsche Zugangsdaten, Widerruf."""
        self.assertEqual(self.client.post('/api/tokens', auth=('marc', 'falsch')).status_code, 401)
        self.assertEqual(self.client.post('/api/tokens').status_code, 401)
        headers = self.bearer()
        self.assertEqual(self.client.get('/api/tracks', headers=headers).status_code, 200)
        self.assertEqual(self.client.delete('/api/tokens', headers=headers).status_code, 204)
        self.assertEqual(self.client.get('/api/tracks', headers=headers).status_code, 401)

    def test_api_read_and_write(self):
        """T-12: Lesender Zugriff, Runde erfassen, fehlerhafte Anfragen, Rangliste."""
        self.assertEqual(self.client.get('/api/tracks').status_code, 401)
        session = self.new_session()
        headers = self.bearer()
        self.assertEqual(self.client.get('/api/tracks', headers=headers).get_json()['items'][0]['slug'],
                         'hockenheim-gp')
        response = self.client.post(f'/api/sessions/{session.id}/laps', headers=headers,
                                    json={'sectors': ['40.100', '51.200', '37.800']})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()['total'], '2:09.100')
        self.assertTrue(response.get_json()['is_new_personal_best'])
        detail = self.client.get(f'/api/sessions/{session.id}', headers=headers).get_json()
        self.assertEqual(detail['analysis']['best_lap_ms'], 129100)
        self.assertEqual(self.client.get(f'/api/sessions/{session.id}/laps', headers=headers)
                         .get_json()['items'][0]['lap_number'], 1)
        # fehlerhafte Anfragen
        self.assertEqual(self.client.post(f'/api/sessions/{session.id}/laps', headers=headers,
                                          json={'sectors': ['a', 'b', 'c']}).status_code, 400)
        self.assertEqual(self.client.post(f'/api/sessions/{session.id}/laps', headers=headers,
                                          json={}).status_code, 400)
        self.assertEqual(db.session.query(Lap).count(), 1)
        # Rangliste
        board = self.client.get('/api/tracks/hockenheim-gp/leaderboard', headers=headers).get_json()
        self.assertEqual(board['entries'][0]['username'], 'marc')
        self.assertEqual(board['entries'][0]['total'], '2:09.100')
        self.assertEqual(self.client.get('/api/tracks/gibtsnicht/leaderboard', headers=headers)
                         .status_code, 404)


if __name__ == '__main__':
    unittest.main(verbosity=2)
