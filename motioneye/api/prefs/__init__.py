import json
import logging

from motioneye.api.handlers import BaseHandler

class PrefsHandler(BaseHandler):
    def get(self, key=None):
        self.finish_json(self.get_pref(key))

    def post(self, key=None):
        try:
            value = json.loads(self.request.body)

        except Exception as e:
            logging.error('could not decode json: %s' % e)

            raise

        self.set_pref(key, value)

DESCRIPTION = "Prefs module API"
ROUTES = [
    (r'^/prefs/(?P<key>\w+)?/?$', PrefsHandler),
]

