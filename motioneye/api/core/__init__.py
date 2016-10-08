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
import motioneye.mod.update as update
import socket

class CoreHandler(BaseHandler):
    def get(self):
        values = {
            'version': update.get_version(),
            'hostname': socket.gethostname(),
        }
        self.finish_json(values)

    post = get

DESCRIPTION = "Show motioneye sample informations"
ROUTES = [
    (r'^/api/motioneye$', CoreHandler),
]
