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

#TODO: See why cannot use import motioneye.api.utils as utils
import utils as utils

class APIHandler(BaseHandler):
    def get(self):
        modules = utils.get_modules_api()

        apilist = dict()
        for key, value in modules.items():
            apilist[key] = dict()
            apilist[key]['description'] = modules[key]['description']
            apilist[key]['routes'] = []
            for route in modules[key]['routes']:
                apilist[key]['routes'].append(route[0])

        self.finish_json(apilist)

    post = get


