import os
import logging
import subprocess

from tornado.web import RequestHandler, HTTPError, asynchronous

from motioneye.api.handlers import BaseHandler
import motioneye.settings as settings

class LogHandler(BaseHandler):
    LOGS = {
        'motion': (os.path.join(settings.LOG_PATH, 'motion.log'), 'motion.log'),
    }

    @BaseHandler.auth(admin=True)
    def get(self, name):
        log = self.LOGS.get(name)
        if log is None:
            raise HTTPError(404, 'no such log')

        (path, filename) = log

        self.set_header('Content-Type', 'text/plain')
        self.set_header('Content-Disposition', 'attachment; filename=' + filename + ';')

        if path.startswith('/'):  # an actual path
            logging.debug('serving log file "%s" from "%s"' % (filename, path))

            with open(path) as f:
                self.finish(f.read())

        else:  # a command to execute
            logging.debug('serving log file "%s" from command "%s"' % (filename, path))

            try:
                output = subprocess.check_output(path.split())

            except Exception as e:
                output = 'failed to execute command: %s' % e

            self.finish(output)


DESCRIPTION = "Log module"
ROUTES = [
    (r'^/log/(?P<name>\w+)/?$', LogHandler),
]
