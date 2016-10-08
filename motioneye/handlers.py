
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

import json
import logging
import socket

from tornado.web import RequestHandler, HTTPError, asynchronous

import motioneye.mod.config as config
import motionctl
import motioneye.mod.prefs as prefs
import settings
import template
import motioneye.mod.update as update
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
