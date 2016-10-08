# Copyright (c) 2016 Bruno Adele
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

from motioneye.api.handlers import BaseHandler
from tornado.web import RequestHandler, HTTPError, asynchronous

import motioneye.utils
import motioneye.config
import motioneye.remote

import logging

class ConfigHandler(BaseHandler):
    def get(self,camera_id):
        if camera_id:
            logging.debug('getting config for camera %(id)s' % {'id': camera_id})

            camera_id = int(camera_id)

            if camera_id not in motioneye.config.get_camera_ids():
                raise HTTPError(404, 'no such camera')

            local_config = motioneye.config.get_camera(camera_id)
            if motioneye.utils.local_motion_camera(local_config):
                ui_config = motioneye.config.motion_camera_dict_to_ui(local_config)

                self.finish_json(ui_config)

            elif motioneye.utils.remote_camera(local_config):
                def on_response(remote_ui_config=None, error=None):
                    if error:
                        return self.finish_json(
                            {'error': 'Failed to get remote camera configuration for %(url)s: %(msg)s.' % {
                                'url': motioneye.remote.pretty_camera_url(local_config), 'msg': error}})

                    for key, value in local_config.items():
                        remote_ui_config[key.replace('@', '')] = value

                    # replace the real device url with the remote camera path
                    remote_ui_config['device_url'] = motioneye.remote.pretty_camera_url(local_config)
                    self.finish_json(remote_ui_config)

                motioneye.remote.get_config(local_config, on_response)

            else:  # assuming simple mjpeg camera
                ui_config = motioneye.config.simple_mjpeg_camera_dict_to_ui(local_config)

                self.finish_json(ui_config)

        else:
            logging.debug('getting main config')

            ui_config = motioneye.config.main_dict_to_ui(motioneye.config.get_main())
            self.finish_json(ui_config)


DESCRIPTION = "Return the motioneye API version"
ROUTES = [
    (r'^/api/config/(?P<camera_id>\d+)/?$', ConfigHandler),
]
