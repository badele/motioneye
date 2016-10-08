
# Copyright (c) 2013 Calin Crisan
# This file is part of motionEye.
#
# motionEye is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>. 

import datetime
import json
import logging
import os
import socket
import subprocess

from tornado.ioloop import IOLoop
from tornado.web import RequestHandler, HTTPError, asynchronous

import motioneye.mod.config as config
import mediafiles
import motionctl
import powerctl
import motioneye.mod.prefs as prefs
import settings
import tasks
import template
import motioneye.mod.update as update
import uploadservices
import utils


class BaseHandler(RequestHandler):
    def get_all_arguments(self):
        keys = self.request.arguments.keys()
        arguments = dict([(key, self.get_argument(key)) for key in keys])

        for key in self.request.files:
            files = self.request.files[key]
            if len(files) > 1:
                arguments[key] = files

            elif len(files) > 0:
                arguments[key] = files[0]

            else:
                continue
        
        # consider the json passed in body as well
        data = self.get_json()
        if data and isinstance(data, dict):
            arguments.update(data)

        return arguments
    
    def get_json(self):
        if not hasattr(self, '_json'):
            self._json = None
            if self.request.headers.get('Content-Type', '').startswith('application/json'):
                self._json = json.loads(self.request.body)

        return self._json
    
    def get_argument(self, name, default=None):
        DEF = {}
        argument = RequestHandler.get_argument(self, name, default=DEF)
        if argument is DEF:
            # try to find it in json body
            data = self.get_json()
            if data:
                argument = data.get(name, DEF)
        
            if argument is DEF:
                argument = default
        
        return argument
    
    def finish(self, chunk=None):
        import motioneye

        self.set_header('Server', 'motionEye/%s' % motioneye.VERSION)
        RequestHandler.finish(self, chunk=chunk)

    def render(self, template_name, content_type='text/html', **context):
        self.set_header('Content-Type', content_type)
        
        content = template.render(template_name, **context)
        self.finish(content)
    
    def finish_json(self, data={}):
        self.set_header('Content-Type', 'application/json')
        self.finish(json.dumps(data))

    def get_current_user(self):
        main_config = config.get_main()
        
        username = self.get_argument('_username', None)
        signature = self.get_argument('_signature', None)
        login = self.get_argument('_login', None) == 'true'
        if (username == main_config.get('@admin_username') and
            signature == utils.compute_signature(self.request.method, self.request.uri, self.request.body, main_config.get('@admin_password'))):
            
            return 'admin'
        
        elif not username and not main_config.get('@normal_password'): # no authentication required for normal user
            return 'normal'
        
        elif (username == main_config.get('@normal_username') and
            signature == utils.compute_signature(self.request.method, self.request.uri, self.request.body, main_config.get('@normal_password'))):
            
            return 'normal'

        elif username and username != '_' and login:
            logging.error('authentication failed for user %(user)s' % {'user': username})

        return None
    
    def get_pref(self, key):
        return prefs.get(self.current_user or 'anonymous', key)
        
    def set_pref(self, key, value):
        return prefs.set(self.current_user or 'anonymous', key, value)
        
    def _handle_request_exception(self, exception):
        try:
            if isinstance(exception, HTTPError):
                logging.error(str(exception))
                self.set_status(exception.status_code)
                self.finish_json({'error': exception.log_message or getattr(exception, 'reason', None) or str(exception)})
            
            else:
                logging.error(str(exception), exc_info=True)
                self.set_status(500)
                self.finish_json({'error':  'internal server error'})
                
        except RuntimeError:
            pass # nevermind
        
    @staticmethod
    def auth(admin=False, prompt=True):
        def decorator(func):
            def wrapper(self, *args, **kwargs):
                _admin = self.get_argument('_admin', None) == 'true'
                
                user = self.current_user
                if (user is None) or (user != 'admin' and (admin or _admin)):
                    self.set_header('Content-Type', 'application/json')
                    self.set_status(403)

                    return self.finish_json({'error': 'unauthorized', 'prompt': prompt})

                return func(self, *args, **kwargs)
            
            return wrapper
        
        return decorator

    def get(self, *args, **kwargs):
        raise HTTPError(400, 'method not allowed')

    def post(self, *args, **kwargs):
        raise HTTPError(400, 'method not allowed')

    def head(self, *args, **kwargs):
        self.finish()


class NotFoundHandler(BaseHandler):
    def get(self, *args, **kwargs):
        raise HTTPError(404, 'not found')

    post = head = get


class MainHandler(BaseHandler):
    def get(self):
        import motioneye
        
        # additional config
        main_sections = config.get_additional_structure(camera=False, separators=True)[0]
        camera_sections = config.get_additional_structure(camera=True, separators=True)[0]

        self.render('main.html',
                frame=False,
                version=motioneye.VERSION,
                enable_update=settings.ENABLE_UPDATE,
                enable_reboot=settings.ENABLE_REBOOT,
                add_remove_cameras=settings.ADD_REMOVE_CAMERAS,
                main_sections=main_sections,
                camera_sections=camera_sections,
                hostname=socket.gethostname(),
                title=self.get_argument('title', None),
                admin_username=config.get_main().get('@admin_username'),
                has_streaming_auth=motionctl.has_streaming_auth(),
                has_new_movie_format_support=motionctl.has_new_movie_format_support(),
                has_motion=bool(motionctl.find_motion()),
                mask_width=utils.MASK_WIDTH,
                mask_default_resolution=utils.MASK_DEFAULT_RESOLUTION)


class RelayEventHandler(BaseHandler):
    @BaseHandler.auth(admin=True)
    def post(self):
        event = self.get_argument('event')
        thread_id = int(self.get_argument('thread_id'))

        camera_id = motionctl.thread_id_to_camera_id(thread_id)
        if camera_id is None:
            logging.debug('ignoring event for unknown thread id %s' % thread_id)
            return self.finish_json()

        else:
            logging.debug('recevied relayed event %(event)s for thread id %(id)s (camera id %(cid)s)' % {
                    'event': event, 'id': thread_id, 'cid': camera_id})
        
        camera_config = config.get_camera(camera_id)
        if not utils.local_motion_camera(camera_config):
            logging.warn('ignoring event for non-local camera with id %s' % camera_id)
            return self.finish_json()
        
        if event == 'start':
            if not camera_config['@motion_detection']:
                logging.debug('ignoring start event for camera with id %s and motion detection disabled' % camera_id)
                return self.finish_json()

            motionctl.set_motion_detected(camera_id, True)
            
        elif event == 'stop':
            motionctl.set_motion_detected(camera_id, False)
            
        elif event == 'movie_end':
            filename = self.get_argument('filename')
            
            # generate preview (thumbnail)
            tasks.add(5, mediafiles.make_movie_preview, tag='make_movie_preview(%s)' % filename,
                    camera_config=camera_config, full_path=filename)

            # upload to external service
            if camera_config['@upload_enabled'] and camera_config['@upload_movie']:
                self.upload_media_file(filename, camera_id, camera_config)

        elif event == 'picture_save':
            filename = self.get_argument('filename')
            
            # upload to external service
            if camera_config['@upload_enabled'] and camera_config['@upload_picture']:
                self.upload_media_file(filename, camera_id, camera_config)

        else:
            logging.warn('unknown event %s' % event)

        self.finish_json()
    
    def upload_media_file(self, filename, camera_id, camera_config):
        service_name = camera_config['@upload_service']
        
        tasks.add(5, uploadservices.upload_media_file, tag='upload_media_file(%s)' % filename,
                camera_id=camera_id, service_name=service_name,
                target_dir=camera_config['@upload_subfolders'] and camera_config['target_dir'],
                filename=filename)


class LogHandler(BaseHandler):
    LOGS = {
        'motion': (os.path.join(settings.LOG_PATH, 'motion.log'),  'motion.log'),
    }

    @BaseHandler.auth(admin=True)
    def get(self, name):
        log = self.LOGS.get(name)
        if log is None:
            raise HTTPError(404, 'no such log')

        (path, filename) = log

        self.set_header('Content-Type', 'text/plain')
        self.set_header('Content-Disposition', 'attachment; filename=' + filename + ';')

        if path.startswith('/'): # an actual path        
            logging.debug('serving log file "%s" from "%s"' % (filename, path))

            with open(path) as f:
                self.finish(f.read())
                
        else: # a command to execute 
            logging.debug('serving log file "%s" from command "%s"' % (filename, path))

            try:
                output = subprocess.check_output(path.split())

            except Exception as e:
                output = 'failed to execute command: %s' % e
                
            self.finish(output)
                


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


class VersionHandler(BaseHandler):
    def get(self):
        self.render('version.html',
                version=update.get_version(),
                hostname=socket.gethostname())

    post = get


# this will only trigger the login mechanism on the client side, if required 
class LoginHandler(BaseHandler):
    @BaseHandler.auth()
    def get(self):
        self.finish_json()

    def post(self):
        self.set_header('Content-Type', 'text/html')
        self.finish()
