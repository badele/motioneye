from motioneye.api.handlers import BaseHandler

# this will only trigger the login mechanism on the client side, if required
class LoginHandler(BaseHandler):
    @BaseHandler.auth()
    def get(self):
        self.finish_json()

    def post(self):
        self.set_header('Content-Type', 'text/html')
        self.finish()


DESCRIPTION = "Power module"
ROUTES = [
    (r'^/login/?$', LoginHandler),
]
