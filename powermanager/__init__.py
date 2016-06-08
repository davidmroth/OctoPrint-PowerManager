# coding=utf-8
from __future__ import absolute_import

__author__ = "David Roth <david.m.roth-at-gmail-dot-com>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'
__copyright__ = "Copyright (C) 2016 David Roth - Released under terms of the AGPLv3 License"

import re
import logging

import octoprint.plugin
from octoprint.util import RepeatedTimer
from octoprint.events import eventManager

from subprocess import Popen, PIPE

class Timer():

    def __init__(self, timeout_minutes):
        self._logEnabled = False
        self._timerEnabled = False
        self._logger = None
        self._timer = None
        self._plugin_manager = None
        self._identifier = None
        self._timeout_seconds = None
        self._cb = None
        self._default_timeout_seconds = self._min2sec(timeout_minutes)

    def initialize(self, plugin_manager, identifier, cb):
        if self._logEnabled is False:
            self._logEnabled = True
            self._logger = logging.getLogger("octoprint.plugins.{}".format(__name__))
            self._plugin_manager = plugin_manager
            self._identifier = identifier
            self._cb = cb

    def initializeTimer(self):
        self._timer = RepeatedTimer(1, self._timer_task)

    def start(self):
        if self._timerEnabled is False:
            if self._timer is None:
                self.initializeTimer()
            self._timeout_seconds = self._default_timeout_seconds
            self._timerEnabled = True
            self._timer.start()
            self._logger.info("Powersave timer started with: {} mintues".format(self._sec2min(self._default_timeout_seconds)))

    def cancel(self):
        if self._timerEnabled is True:
            self._timerEnabled = False
            if self._timer is not None:
                self._plugin_manager.send_plugin_message(self._identifier, dict(type="cancel"))
                self._timer.cancel()
                self._timer = None
            self._logger.info("Powersave timer canceled")

    def setNewTimeoutMinutes(self, minutes):
        if not self._min2sec(minutes) == self._default_timeout_seconds:
            self._default_timeout_seconds = self._min2sec(minutes)
            self.cancel()
            self.start()
            self._logger.info("Powersave timeout value updated to: {}".format(minutes))

    def reset(self):
        self._timeout_value = self.default_timeout_seconds
        self._logger.info("Powersave timer reset")

    def _timer_task(self):
        self._timeout_seconds -= 1

        if self._timeout_seconds < 60 * 5:
            self._plugin_manager.send_plugin_message(self._identifier, dict(type="timeout", timeout_value=self._timeout_seconds))

        if self._timeout_seconds <= 0:
            self._timer.cancel()
            self._timer = None
            self._cb()

    def _sec2min(self, seconds):
        return seconds / 60

    def _min2sec(self, minutes):
        return 60 * minutes


class PowerManagerPlugin(octoprint.plugin.StartupPlugin,
    octoprint.plugin.ShutdownPlugin,
    octoprint.plugin.EventHandlerPlugin,
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.SimpleApiPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin):

    PSTATE_OFF = 0
    PSTATE_ON = 1
    PSTATE_UNKNOWN = 99

    def __init__(self):
        self._timer = None
        self._isPowerManagerEnabled = True
        self._pstate = 99
        self._changeState(self._getGPIO_status())

    def on_after_startup(self):
        self._missing_msg()
        self._timer = Timer(self._settings.get_int(["timeoutMinutes"]))
        self._timer.initialize(self._plugin_manager, self._identifier, self._powerdown_system)
        if self._pstate == self.PSTATE_ON:
            self._timer.start()
        else:
            self._printer._comm._changeState(self._printer._comm.STATE_NONE)

    def on_shutdown(self):
        self._printer._comm._changeState(self._printer._comm.STATE_NONE)
        self._changeState(self.PSTATE_OFF)
        self._updatePstate()
        self._powerdown_system()

    def on_event(self, event, payload):
        self._logger.info("Event recieved: {}".format(event))

        if event == "Startup":
            pass

        if event == "PrintStarted":
            if self._isPowerManagerEnabled is True:
                self._timer.cancel()
            return

        if event == "PrintDone":
            if self._isPowerManagerEnabled is True:
                self._timer.start()
            return

        if event == "PoweredOff":
            self._printer._comm._changeState(self._printer._comm.STATE_NONE)
            self._changeState(self.PSTATE_OFF)
            self._updatePstate()
            if self._isPowerManagerEnabled is True:
                self._timer.cancel()
            return

        if event == "PoweredOn":
            self._printer._comm._changeState(self._printer._comm.STATE_OPERATIONAL)
            self._changeState(self.PSTATE_ON)
            self._updatePstate()
            if self._isPowerManagerEnabled is True:
                self._timer.start()
            return

        if event == "SettingsUpdated":
            s = self._settings
            self._timer.setNewTimeoutMinutes(s.get_int(["timeoutMinutes"]))
            current_systemPowerdownCommand = s.global_get(["server", "commands", "systemShutdownCommand"])
            new_systemPowerdownCommand = self._settings.get(["systemPowerdownCommand"])

            #Change global setting
            if not new_systemPowerdownCommand == current_systemPowerdownCommand:
                s.global_set(["server", "commands", "systemShutdownCommand"], new_systemPowerdownCommand)
                s.save()
            return

    def get_api_commands(self):
        return dict(enable_power_management=[], disable_power_management=[], power_on_printer=[], power_off_printer=[], abort_power_off=[], get_printer_power_state=[], get_power_management_state=[])

    def on_api_command(self, command, data):
        from flask import jsonify
        self._logger.info("Command recieved: {}".format(command))

        if command == "abort_power_off":
            self._timer.cancel()
            self._logger.info("Shutdown aborted.")

        elif command == "power_on_printer":
            if self._pstate == self.PSTATE_OFF:
                self._powerup_system()

        elif command == "power_off_printer":
            if self._pstate == self.PSTATE_ON:
                self._powerdown_system()

        elif command == "enable_power_management":
            self._isPowerManagerEnabled = True
            if self._pstate == self.PSTATE_ON:
                self._timer.start()

        elif command == "disable_power_management":
            self._isPowerManagerEnabled = False
            if self._pstate == self.PSTATE_ON:
                self._timer.cancel()

        elif command == "get_printer_power_state":
            return jsonify(state=self._pstate)

        elif command == "get_power_management_state":
            return jsonify(isEnabled=self._isPowerManagerEnabled)

    def catch_m80_m81(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):

        if gcode and (gcode == "M80" or gcode == "M81"):
            if (gcode == "M80"):
                self._powerup_system()
                cmd = "G4 S5"
                action = "up"

            if (gcode == "M81"):
                self._powerdown_system()
                cmd = "G4 S0"
                action = "down"

            self._logger.info("Intercepting G-code: {gcode}. Powering {action} printer".format(**locals()))

        return cmd

    def _changeState(self, newState):
        print "self._pstate = {} | newState = {}".format(self._pstate, newState)
        if self._pstate == newState:
            return

        self._pstate = newState

    def _updatePstate(self):
        self._plugin_manager.send_plugin_message(self._identifier, dict(type="pstate_update", pstate=self._pstate))

    def _powerdown_system(self):
        powerdown_command = self._settings.global_get(["server", "commands", "systemShutdownCommand"])
        self._logger.info("Powering down system with command: {}".format(powerdown_command))

        if powerdown_command:
            try:
                import sarge
                p = sarge.run(powerdown_command, async=True)
                eventManager().fire("PoweredOff")

            except Exception as e:
                self._logger.exception("Error when shutting down: {error}".format(error=e))
                return

    def _powerup_system(self):
        powerup_command = self._systemPowerupCommand = self._settings.get(["systemPowerupCommand"])
        self._logger.info("Powering up system with command: {}".format(powerup_command))

        if powerup_command:
            try:
                import sarge
                p = sarge.run(powerup_command, async=True)
                eventManager().fire("PoweredOn")

            except Exception as e:
                self._logger.exception("Error when powering up: {error}".format(error=e))
                return

    def _getGPIO_status(self):
        process = Popen(["gpio", "read", "7"], stdout=PIPE)
        (output, err) = process.communicate()
        exit_code = process.wait()
        state = re.compile('(^\d)').match(output)

        if state:
            pstate = state.groups()[0]
            if int(pstate) == 0:
                return 0

            elif int(pstate) == 1:
                return 1
        else:
            return 99


    def _missing_msg(self):
        if not self._settings.global_get(["server", "commands", "systemShutdownCommand"]):
            self._logger.error("Missing global setting: 'systemShutdownCommand'")

        if not self._settings.get(["server", "commands", "systemPowerupCommand"]):
            self._logger.error("Missing setting: 'systemPowerupCommand'")

    def get_assets(self):
        return dict(js=["js/{}.js".format(__name__)])

    def get_template_configs(self):
        return [
            dict(type="sidebar", name="Power Manager", template="{}_sidebar.jinja2".format(__name__), custom_bindings=False, icon="power-off"),
            dict(type="settings", name="Power Manager", template="{}_settings.jinja2".format(__name__), custom_bindings=False)
        ]

    def get_settings_defaults(self):
        return dict(
          powerManagementEnabled = True,
          timeoutMinutes = "15",
          systemPowerdownCommand = "gpio write 7 0",
          systemPowerupCommand = "gpio write 7 1"
        )

    def on_settings_save(self, data):
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        eventManager().fire("SettingsUpdated")

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://github.com/foosel/OctoPrint/wiki/Plugin:-Software-Update
        # for details.
        return dict(
            autopowersaver=dict(
                displayName="OctoPrint-PowerManager",
                displayVersion=self._plugin_version,

                # version check: github repository
                type="github_release",
                user="davidmroth",
                repo="OctoPrint-PowerManager",
                current=self._plugin_version,

                # update method: pip
                pip="https://github.com/davidmroth/OctoPrint-PowerManager/archive/{target_version}.zip"
            )
        )


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = PowerManagerPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
        "octoprint.comm.protocol.gcode.queuing": __plugin_implementation__.catch_m80_m81
    }

