import os
import logging
import datetime
import subprocess

from tornado.ioloop import IOLoop
from tornado.web import RequestHandler, HTTPError, asynchronous

from motioneye.api.handlers import BaseHandler
import motioneye.mod.config as config
import motioneye.utils as utils
import motioneye.remote as remote


class ActionHandler(BaseHandler):
    @asynchronous
    def post(self, camera_id, action):
        camera_id = int(camera_id)
        if camera_id not in config.get_camera_ids():
            raise HTTPError(404, 'no such camera')

        local_config = config.get_camera(camera_id)
        if utils.remote_camera(local_config):
            def on_response(error=None):
                if error:
                    return self.finish_json(
                        {'error': 'Failed to execute action on remote camera at %(url)s: %(msg)s.' % {
                            'url': remote.pretty_camera_url(local_config), 'msg': error}})

                self.finish_json()

            return remote.exec_action(local_config, action, on_response)

        if action == 'snapshot':
            logging.debug('executing snapshot action for camera with id %s' % camera_id)
            return self.snapshot()

        elif action == 'record_start':
            logging.debug('executing record_start action for camera with id %s' % camera_id)
            return self.record_start()

        elif action == 'record_stop':
            logging.debug('executing record_stop action for camera with id %s' % camera_id)
            return self.record_stop()

        action_commands = config.get_action_commands(camera_id)
        command = action_commands.get(action)
        if not command:
            raise HTTPError(400, 'unknown action')

        logging.debug('executing %s action for camera with id %s: "%s"' % (action, camera_id, command))
        self.run_command_bg(command)

    def run_command_bg(self, command):
        self.p = subprocess.Popen(command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
        self.command = command

        self.io_loop = IOLoop.instance()
        self.io_loop.add_timeout(datetime.timedelta(milliseconds=100), self.check_command)

    def check_command(self):
        exit_status = self.p.poll()
        if exit_status is not None:
            output = self.p.stdout.read()
            lines = output.split('\n')
            if not lines[-1]:
                lines = lines[:-1]
            command = os.path.basename(self.command)
            if exit_status:
                logging.warn('%s: command has finished with non-zero exit status: %s' % (command, exit_status))
                for line in lines:
                    logging.warn('%s: %s' % (command, line))

            else:
                logging.debug('%s: command has finished' % command)
                for line in lines:
                    logging.debug('%s: %s' % (command, line))

            self.finish_json({'status': exit_status})

        else:
            self.io_loop.add_timeout(datetime.timedelta(milliseconds=100), self.check_command)

    def snapshot(self):
        self.finish_json({})

    def record_start(self):
        self.finish_json({})

    def record_stop(self):
        self.finish_json({})

DESCRIPTION = "Action module API"
ROUTES = [
    (r'^/action/(?P<camera_id>\d+)/(?P<action>\w+)/?$', ActionHandler),
]
