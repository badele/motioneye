import datetime

from tornado.ioloop import IOLoop
import motioneye.mod.power.powerctl as powerctl

from motioneye.api.handlers import BaseHandler


class PowerHandler(BaseHandler):
    @BaseHandler.auth(admin=True)
    def post(self, op):
        if op == 'shutdown':
            self.shut_down()

        elif op == 'reboot':
            self.reboot()

    def shut_down(self):
        io_loop = IOLoop.instance()
        io_loop.add_timeout(datetime.timedelta(seconds=2), powerctl.shut_down)

    def reboot(self):
        io_loop = IOLoop.instance()
        io_loop.add_timeout(datetime.timedelta(seconds=2), powerctl.reboot)

DESCRIPTION = "Power module"
ROUTES = [
    (r'^/power/(?P<op>shutdown|reboot)/?$', PowerHandler),
]
