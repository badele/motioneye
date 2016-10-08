import logging

from motioneye.api.handlers import BaseHandler
import motioneye.mod.update as update

class UpdateHandler(BaseHandler):
    @BaseHandler.auth(admin=True)
    def get(self):
        logging.debug('listing versions')

        versions = update.get_all_versions()
        current_version = update.get_version()
        update_version = None
        if versions and update.compare_versions(versions[-1], current_version) > 0:
            update_version = versions[-1]

        self.finish_json({
            'update_version': update_version,
            'current_version': current_version
        })

    @BaseHandler.auth(admin=True)
    def post(self):
        version = self.get_argument('version')

        logging.debug('performing update to version %(version)s' % {'version': version})

        result = update.perform_update(version)

        self.finish_json(result)



DESCRIPTION = "Manage motioneye program"
ROUTES = [
    (r'^/update/?$', UpdateHandler),
]
