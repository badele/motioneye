import logging

from motioneye.api.handlers import BaseHandler
import motioneye.mod.config as config
import motioneye.motionctl as motionctl
import motioneye.utils as utils
import motioneye.utils as tasks
import motioneye.uploadservices as uploadservices

class RelayeventHandler(BaseHandler):
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

DESCRIPTION = "Relay event module"
ROUTES = [
    (r'^/_relay_event/?$', RelayeventHandler),
]
