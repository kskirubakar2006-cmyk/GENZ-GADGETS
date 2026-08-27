import unittest

from werkzeug.security import generate_password_hash

from app import app, db
from models import Admin


class AuthFlowTests(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', SECRET_KEY='test-secret')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()

        admin = Admin(
            username='tester',
            email='tester@example.com',
            password_hash=generate_password_hash('secret123')
        )
        db.session.add(admin)
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_root_redirects_to_login_for_anonymous_user(self):
        response = self.client.get('/', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/login')

    def test_protected_routes_redirect_to_login(self):
        for route in ['/dashboard', '/inventory', '/customers', '/suppliers', '/sales']:
            response = self.client.get(route, follow_redirects=False)
            self.assertEqual(response.status_code, 302, msg=route)
            self.assertEqual(response.headers['Location'], '/login', msg=route)

    def test_login_redirects_to_dashboard_and_logout_restricts_access(self):
        login_response = self.client.post('/login', data={'username': 'tester', 'password': 'secret123'}, follow_redirects=False)
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(login_response.headers['Location'], '/dashboard')

        dashboard_response = self.client.get('/dashboard')
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn('GENZ GADGETS | Dashboard', dashboard_response.get_data(as_text=True))

        logout_response = self.client.get('/logout', follow_redirects=False)
        self.assertEqual(logout_response.status_code, 302)
        self.assertEqual(logout_response.headers['Location'], '/login')

        after_logout_response = self.client.get('/dashboard', follow_redirects=False)
        self.assertEqual(after_logout_response.status_code, 302)
        self.assertEqual(after_logout_response.headers['Location'], '/login')


if __name__ == '__main__':
    unittest.main()
