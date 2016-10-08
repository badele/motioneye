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

import motioneye.utils as utils
import motioneye.mod.config as config
import motioneye.remote as remote

import logging


class ConfigHandler(BaseHandler):
    @asynchronous
    def get(self, camera_id=None, op=None):
        config.invalidate_monitor_commands()

        if camera_id is not None:
            camera_id = int(camera_id)

        if op == 'get':
            self.get_config(camera_id)

        elif op == 'list':
            self.list()

        elif op == 'backup':
            self.backup()

        elif op == 'authorize':
            self.authorize(camera_id)

        else:
            raise HTTPError(400, 'unknown operation')

    @asynchronous
    def post(self, camera_id=None, op=None):
        if camera_id is not None:
            camera_id = int(camera_id)

        if op == 'set':
            self.set_config(camera_id)

        elif op == 'set_preview':
            self.set_preview(camera_id)

        elif op == 'add':
            self.add_camera()

        elif op == 'rem':
            self.rem_camera(camera_id)

        elif op == 'restore':
            self.restore()

        elif op == 'test':
            self.test(camera_id)

        else:
            raise HTTPError(400, 'unknown operation')

    @BaseHandler.auth(admin=True)
    def get_config(self, camera_id):
        if camera_id:
            logging.debug('getting config for camera %(id)s' % {'id': camera_id})

            if camera_id not in config.get_camera_ids():
                raise HTTPError(404, 'no such camera')

            local_config = config.get_camera(camera_id)
            if utils.local_motion_camera(local_config):
                ui_config = config.motion_camera_dict_to_ui(local_config)

                self.finish_json(ui_config)

            elif utils.remote_camera(local_config):
                def on_response(remote_ui_config=None, error=None):
                    if error:
                        return self.finish_json(
                            {'error': 'Failed to get remote camera configuration for %(url)s: %(msg)s.' % {
                                'url': remote.pretty_camera_url(local_config), 'msg': error}})

                    for key, value in local_config.items():
                        remote_ui_config[key.replace('@', '')] = value

                    # replace the real device url with the remote camera path
                    remote_ui_config['device_url'] = remote.pretty_camera_url(local_config)
                    self.finish_json(remote_ui_config)

                remote.get_config(local_config, on_response)

            else:  # assuming simple mjpeg camera
                ui_config = config.simple_mjpeg_camera_dict_to_ui(local_config)

                self.finish_json(ui_config)

        else:
            logging.debug('getting main config')

            ui_config = config.main_dict_to_ui(config.get_main())
            self.finish_json(ui_config)

    @BaseHandler.auth(admin=True)
    def set_config(self, camera_id):
        try:
            ui_config = json.loads(self.request.body)

        except Exception as e:
            logging.error('could not decode json: %(msg)s' % {'msg': unicode(e)})

            raise

        camera_ids = config.get_camera_ids()

        def set_camera_config(camera_id, ui_config, on_finish):
            logging.debug('setting config for camera %(id)s...' % {'id': camera_id})

            if camera_id not in camera_ids:
                raise HTTPError(404, 'no such camera')

            local_config = config.get_camera(camera_id)
            if utils.local_motion_camera(local_config):
                local_config = config.motion_camera_ui_to_dict(ui_config, local_config)

                config.set_camera(camera_id, local_config)

                on_finish(None, True)  # (no error, motion needs restart)

            elif utils.remote_camera(local_config):
                # update the camera locally
                local_config['@enabled'] = ui_config['enabled']
                config.set_camera(camera_id, local_config)

                if ui_config.has_key('name'):
                    def on_finish_wrapper(error=None):
                        return on_finish(error, False)

                    ui_config['enabled'] = True  # never disable the camera remotely
                    remote.set_config(local_config, ui_config, on_finish_wrapper)

                else:
                    # when the ui config supplied has only the enabled state
                    # and no useful fields (such as "name"),
                    # the camera was probably disabled due to errors
                    on_finish(None, False)

            else:  # assuming simple mjpeg camera
                local_config = config.simple_mjpeg_camera_ui_to_dict(ui_config, local_config)

                config.set_camera(camera_id, local_config)

                on_finish(None, False)  # (no error, motion doesn't need restart)

        def set_main_config(ui_config):
            logging.debug('setting main config...')

            old_main_config = config.get_main()
            old_admin_credentials = '%s:%s' % (
            old_main_config.get('@admin_username', ''), old_main_config.get('@admin_password', ''))
            old_normal_credentials = '%s:%s' % (
            old_main_config.get('@normal_username', ''), old_main_config.get('@normal_password', ''))

            main_config = config.main_ui_to_dict(ui_config)
            main_config.setdefault('thread', old_main_config.get('thread', []))
            admin_credentials = '%s:%s' % (
            main_config.get('@admin_username', ''), main_config.get('@admin_password', ''))
            normal_credentials = '%s:%s' % (
            main_config.get('@normal_username', ''), main_config.get('@normal_password', ''))

            additional_configs = config.get_additional_structure(camera=False)[1]
            reboot_config_names = [('@_' + c['name']) for c in additional_configs.values() if c.get('reboot')]
            reboot_config_names.append('@admin_password')
            reboot = bool([k for k in reboot_config_names if old_main_config.get(k) != main_config.get(k)])

            config.set_main(main_config)

            reload = False
            restart = False

            if admin_credentials != old_admin_credentials:
                logging.debug('admin credentials changed, reload needed')

                reload = True

            if normal_credentials != old_normal_credentials:
                logging.debug('surveillance credentials changed, all camera configs must be updated')

                # reconfigure all local cameras to update the stream authentication options
                for camera_id in config.get_camera_ids():
                    local_config = config.get_camera(camera_id)
                    if not utils.local_motion_camera(local_config):
                        continue

                    ui_config = config.motion_camera_dict_to_ui(local_config)
                    local_config = config.motion_camera_ui_to_dict(ui_config, local_config)

                    config.set_camera(camera_id, local_config)

                    restart = True

            if reboot and settings.ENABLE_REBOOT:
                logging.debug('system settings changed, reboot needed')

            else:
                reboot = False

            return {'reload': reload, 'reboot': reboot, 'restart': restart}

        reload = False  # indicates that browser should reload the page
        reboot = [False]  # indicates that the server will reboot immediately
        restart = [False]  # indicates that the local motion instance was modified and needs to be restarted
        error = [None]

        def finish():
            if reboot[0]:
                if settings.ENABLE_REBOOT:
                    def call_reboot():
                        powerctl.reboot()

                    io_loop = IOLoop.instance()
                    io_loop.add_timeout(datetime.timedelta(seconds=2), call_reboot)
                    return self.finish({'reload': False, 'reboot': True, 'error': None})

                else:
                    reboot[0] = False

            if restart[0]:
                logging.debug('motion needs to be restarted')

                motionctl.stop()

                if settings.SMB_SHARES:
                    logging.debug('updating SMB mounts')
                    stop, start = smbctl.update_mounts()  # @UnusedVariable

                    if start:
                        motionctl.start()

                else:
                    motionctl.start()

            self.finish({'reload': reload, 'reboot': reboot[0], 'error': error[0]})

        if camera_id is not None:
            if camera_id == 0:  # multiple camera configs
                if len(ui_config) > 1:
                    logging.debug('setting multiple configs')

                elif len(ui_config) == 0:
                    logging.warn('no configuration to set')

                    self.finish()

                so_far = [0]

                def check_finished(e, r):
                    restart[0] = restart[0] or r
                    error[0] = error[0] or e
                    so_far[0] += 1

                    if so_far[0] >= len(ui_config):  # finished
                        finish()

                # make sure main config is handled first
                items = ui_config.items()
                items.sort(key=lambda (key, cfg): key != 'main')

                for key, cfg in items:
                    if key == 'main':
                        result = set_main_config(cfg)
                        reload = result['reload'] or reload
                        reboot[0] = result['reboot'] or reboot[0]
                        restart[0] = result['restart'] or restart[0]
                        check_finished(None, reload)

                    else:
                        set_camera_config(int(key), cfg, check_finished)

            else:  # single camera config
                def on_finish(e, r):
                    error[0] = e
                    restart[0] = r
                    finish()

                set_camera_config(camera_id, ui_config, on_finish)

        else:  # main config
            result = set_main_config(ui_config)
            reload = result['reload']
            reboot[0] = result['reboot']
            restart[0] = result['restart']

    @BaseHandler.auth(admin=True)
    def set_preview(self, camera_id):
        try:
            controls = json.loads(self.request.body)

        except Exception as e:
            logging.error('could not decode json: %(msg)s' % {'msg': unicode(e)})

            raise

        camera_config = config.get_camera(camera_id)
        if utils.v4l2_camera(camera_config):
            device = camera_config['videodevice']

            if 'brightness' in controls:
                value = int(controls['brightness'])
                logging.debug('setting brightness to %(value)s...' % {'value': value})

                v4l2ctl.set_brightness(device, value)

            if 'contrast' in controls:
                value = int(controls['contrast'])
                logging.debug('setting contrast to %(value)s...' % {'value': value})

                v4l2ctl.set_contrast(device, value)

            if 'saturation' in controls:
                value = int(controls['saturation'])
                logging.debug('setting saturation to %(value)s...' % {'value': value})

                v4l2ctl.set_saturation(device, value)

            if 'hue' in controls:
                value = int(controls['hue'])
                logging.debug('setting hue to %(value)s...' % {'value': value})

                v4l2ctl.set_hue(device, value)

            self.finish_json({})

        elif utils.remote_camera(camera_config):
            def on_response(error=None):
                if error:
                    self.finish_json({'error': error})

                else:
                    self.finish_json()

            remote.set_preview(camera_config, controls, on_response)

        else:  # not supported
            self.finish_json({'error': True})

    @BaseHandler.auth()
    def list(self):
        logging.debug('listing cameras')

        proto = self.get_argument('proto')
        if proto == 'motioneye':  # remote listing
            def on_response(cameras=None, error=None):
                if error:
                    self.finish_json({'error': error})

                else:
                    self.finish_json({'cameras': cameras})

            remote.list(self.get_all_arguments(), on_response)

        elif proto == 'netcam':
            scheme = self.get_argument('scheme', 'http')

            def on_response(cameras=None, error=None):
                if error:
                    self.finish_json({'error': error})

                else:
                    self.finish_json({'cameras': cameras})

            if scheme in ['http', 'https']:
                utils.test_mjpeg_url(self.get_all_arguments(), auth_modes=['basic'], allow_jpeg=True,
                                     callback=on_response)

            elif motionctl.get_rtsp_support() and scheme == 'rtsp':
                utils.test_rtsp_url(self.get_all_arguments(), callback=on_response)

            else:
                on_response(error='protocol %s not supported' % scheme)

        elif proto == 'mjpeg':
            def on_response(cameras=None, error=None):
                if error:
                    self.finish_json({'error': error})

                else:
                    self.finish_json({'cameras': cameras})

            utils.test_mjpeg_url(self.get_all_arguments(), auth_modes=['basic', 'digest'], allow_jpeg=False,
                                 callback=on_response)

        elif proto == 'v4l2':
            configured_devices = set()
            for camera_id in config.get_camera_ids():
                data = config.get_camera(camera_id)
                if utils.v4l2_camera(data):
                    configured_devices.add(data['videodevice'])

            cameras = [{'id': d[1], 'name': d[2]} for d in v4l2ctl.list_devices()
                       if (d[0] not in configured_devices) and (d[1] not in configured_devices)]

            self.finish_json({'cameras': cameras})

        else:  # assuming local motionEye camera listing
            cameras = []
            camera_ids = config.get_camera_ids()
            if not config.get_main().get('@enabled'):
                camera_ids = []

            length = [len(camera_ids)]

            def check_finished():
                if len(cameras) == length[0]:
                    cameras.sort(key=lambda c: c['id'])
                    self.finish_json({'cameras': cameras})

            def on_response_builder(camera_id, local_config):
                def on_response(remote_ui_config=None, error=None):
                    if error:
                        cameras.append({
                            'id': camera_id,
                            'name': '&lt;' + remote.pretty_camera_url(local_config) + '&gt;',
                            'enabled': False,
                            'streaming_framerate': 1,
                            'framerate': 1
                        })

                    else:
                        remote_ui_config['id'] = camera_id

                        if not remote_ui_config['enabled'] and local_config['@enabled']:
                            # if a remote camera is disabled, make sure it's disabled locally as well
                            local_config['@enabled'] = False
                            config.set_camera(camera_id, local_config)

                        elif remote_ui_config['enabled'] and not local_config['@enabled']:
                            # if a remote camera is locally disabled, make sure the remote config says the same thing
                            remote_ui_config['enabled'] = False

                        for key, value in local_config.items():
                            remote_ui_config[key.replace('@', '')] = value

                        cameras.append(remote_ui_config)

                    check_finished()

                return on_response

            for camera_id in camera_ids:
                local_config = config.get_camera(camera_id)
                if local_config is None:
                    continue

                if utils.local_motion_camera(local_config):
                    ui_config = config.motion_camera_dict_to_ui(local_config)
                    cameras.append(ui_config)
                    check_finished()

                elif utils.remote_camera(local_config):
                    if local_config.get('@enabled') or self.get_argument('force', None) == 'true':
                        remote.get_config(local_config, on_response_builder(camera_id, local_config))

                    else:  # don't try to reach the remote of the camera is disabled
                        on_response_builder(camera_id, local_config)(error=True)

                else:  # assuming simple mjpeg camera
                    ui_config = config.simple_mjpeg_camera_dict_to_ui(local_config)
                    cameras.append(ui_config)
                    check_finished()

            if length[0] == 0:
                self.finish_json({'cameras': []})

    @BaseHandler.auth(admin=True)
    def add_camera(self):
        logging.debug('adding new camera')

        try:
            device_details = json.loads(self.request.body)

        except Exception as e:
            logging.error('could not decode json: %(msg)s' % {'msg': unicode(e)})

            raise

        camera_config = config.add_camera(device_details)

        if utils.local_motion_camera(camera_config):
            motionctl.stop()

            if settings.SMB_SHARES:
                stop, start = smbctl.update_mounts()  # @UnusedVariable

                if start:
                    motionctl.start()

            else:
                motionctl.start()

            ui_config = config.motion_camera_dict_to_ui(camera_config)

            self.finish_json(ui_config)

        elif utils.remote_camera(camera_config):
            def on_response(remote_ui_config=None, error=None):
                if error:
                    return self.finish_json({'error': error})

                for key, value in camera_config.items():
                    remote_ui_config[key.replace('@', '')] = value

                self.finish_json(remote_ui_config)

            remote.get_config(camera_config, on_response)

        else:  # assuming simple mjpeg camera
            ui_config = config.simple_mjpeg_camera_dict_to_ui(camera_config)

            self.finish_json(ui_config)

    @BaseHandler.auth(admin=True)
    def rem_camera(self, camera_id):
        logging.debug('removing camera %(id)s' % {'id': camera_id})

        local = utils.local_motion_camera(config.get_camera(camera_id))
        config.rem_camera(camera_id)

        if local:
            motionctl.stop()
            motionctl.start()

        self.finish_json()

    @BaseHandler.auth(admin=True)
    def backup(self):
        content = config.backup()

        if not content:
            raise Exception('failed to create backup file')

        filename = 'motioneye-config.tar.gz'
        self.set_header('Content-Type', 'application/x-compressed')
        self.set_header('Content-Disposition', 'attachment; filename=' + filename + ';')

        self.finish(content)

    @BaseHandler.auth(admin=True)
    def restore(self):
        try:
            content = self.request.files['files'][0]['body']

        except KeyError:
            raise HTTPError(400, 'file attachment required')

        result = config.restore(content)
        if result:
            self.finish_json({'ok': True, 'reboot': result['reboot']})

        else:
            self.finish_json({'ok': False})

    @classmethod
    def _on_test_result(cls, result):
        upload_service_test_info = getattr(cls, '_upload_service_test_info', None)
        cls._upload_service_test_info = None

        if not upload_service_test_info:
            return logging.warn('no pending upload service test request')

        (request_handler, service_name) = upload_service_test_info

        if result is True:
            logging.debug('accessing %s succeeded' % service_name)
            request_handler.finish_json()

        else:
            logging.warn('accessing %s failed: %s' % (service_name, result))
            request_handler.finish_json({'error': result})

    @BaseHandler.auth(admin=True)
    def test(self, camera_id):
        what = self.get_argument('what')
        data = self.get_all_arguments()
        camera_config = config.get_camera(camera_id)

        if utils.local_motion_camera(camera_config):
            if what == 'upload_service':
                service_name = data['service']
                ConfigHandler._upload_service_test_info = (self, service_name)

                tasks.add(0, uploadservices.test_access, tag='uploadservices.test(%s)' % service_name,
                          camera_id=camera_id, service_name=service_name, data=data, callback=self._on_test_result)

            elif what == 'email':
                import motioneye.sendmail as sendmail
                import motioneye.tzctl as tzctl
                import motioneye.smtplib as smtplib

                logging.debug('testing notification email')

                try:
                    subject = sendmail.subjects['motion_start']
                    message = sendmail.messages['motion_start']
                    format_dict = {
                        'camera': camera_config['@name'],
                        'hostname': socket.gethostname(),
                        'moment': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    }
                    if settings.LOCAL_TIME_FILE:
                        format_dict['timezone'] = tzctl.get_time_zone()

                    else:
                        format_dict['timezone'] = 'local time'

                    message = message % format_dict
                    subject = subject % format_dict

                    old_timeout = settings.SMTP_TIMEOUT
                    settings.SMTP_TIMEOUT = 10
                    sendmail.send_mail(data['smtp_server'], int(data['smtp_port']), data['smtp_account'],
                                       data['smtp_password'], data['smtp_tls'],
                                       data['from'], [data['addresses']], subject=subject, message=message, files=[])
                    settings.SMTP_TIMEOUT = old_timeout

                    self.finish_json()

                    logging.debug('notification email test succeeded')

                except Exception as e:
                    if isinstance(e, smtplib.SMTPResponseException):
                        msg = e.smtp_error

                    else:
                        msg = str(e)

                    msg_lower = msg.lower()
                    if msg_lower.count('tls'):
                        msg = 'TLS might be required'

                    elif msg_lower.count('authentication'):
                        msg = 'authentication error'

                    elif msg_lower.count('name or service not known'):
                        msg = 'check SMTP server name'

                    elif msg_lower.count('connection refused'):
                        msg = 'check SMTP port'

                    logging.error('notification email test failed: %s' % msg, exc_info=True)
                    self.finish_json({'error': str(msg)})

            elif what == 'network_share':
                logging.debug('testing access to network share //%s/%s' % (data['server'], data['share']))

                try:
                    smbctl.test_share(data['server'], data['share'], data['username'], data['password'],
                                      data['root_directory'])
                    logging.debug('access to network share //%s/%s succeeded' % (data['server'], data['share']))
                    self.finish_json()

                except Exception as e:
                    logging.error('access to network share //%s/%s failed: %s' % (data['server'], data['share'], e))
                    self.finish_json({'error': str(e)})

            else:
                raise HTTPError(400, 'unknown test %s' % what)

        elif utils.remote_camera(camera_config):
            def on_response(result=None, error=None):
                if result is True:
                    self.finish_json()

                else:
                    result = result or error
                    self.finish_json({'error': result})

            remote.test(camera_config, data, on_response)

        else:
            raise HTTPError(400, 'cannot test features on this type of camera')

    @BaseHandler.auth(admin=True)
    def authorize(self, camera_id):
        service_name = self.get_argument('service')
        if not service_name:
            raise HTTPError(400, 'service_name required')

        url = uploadservices.get_authorize_url(service_name)
        if not url:
            raise HTTPError(400, 'no authorization url for upload service %s' % service_name)

        logging.debug('redirected to authorization url %s' % url)
        self.redirect(url)


DESCRIPTION = "Manage motioneye configuration"
ROUTES = [
    (r'^/config/main/(?P<op>set|get)/?$', ConfigHandler),
    (r'^/config/(?P<camera_id>\d+)/(?P<op>get|set|rem|set_preview|test|authorize)/?$', ConfigHandler),
    (r'^/config/(?P<op>add|list|backup|restore)/?$', ConfigHandler),
]
