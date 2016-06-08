$(function() {

    function PowerManagerViewModel(parameters) {
        var self = this;

        // Login state
        self.loginState = parameters[0];

        // Internal State Tracking
        self.printerPowerState = false;
        self.buttonDelay = 3000;
        self.powerButtonBusy = ko.observable(false);
        self.powerManagerButtonBusy = ko.observable(false);

        // UI State Management
        self.isPowerManagementEnabled = ko.observable();
        self.printerPowerStateText = ko.observable("...");
        self.printerPowerStateButtonClass = ko.observable("btn-primary");

        self.loginState.loggedIn.subscribe(function(isLoggedIn) {
            if (isLoggedIn) {
                console.log("Logged in");
                self.powerButtonBusy(true);
                self.powerManagerButtonBusy(true);
                self.getPrinterPowerState()
                self.getPowerManagementState();
                $('#sidebar_plugin_powermanager').collapse('show');

            } else {
                console.log("Not logged in");
                self.powerButtonBusy(false);
                self.powerManagerButtonBusy(false);
                self.updatePrinterPowerState(99);
                $('#sidebar_plugin_powermanager').collapse('hide');
            }
        });

        self.getPrinterPowerState = function() {
            $.ajax({
                url: API_BASEURL + "plugin/powermanager",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({
                    command: "get_printer_power_state"
                }),
                contentType: "application/json; charset=UTF-8"

            }).done(function (data) {
                if (data && data.state != null) {
                    self.updatePrinterPowerState(data.state);
                }
            });
        }

        self.getPowerManagementState = function() {
            $.ajax({
                url: API_BASEURL + "plugin/powermanager",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({
                    command: "get_power_management_state"
                }),
                contentType: "application/json; charset=UTF-8"

            }).done(function (data) {
                if (data && data.isEnabled != null) {
                    self.isPowerManagementEnabled(data.isEnabled);
                }
            });
        }

        self.updatePrinterPowerState = function(pstate) {
            var pstate_text;

            if (pstate == 0) {
                self.printerPowerState = false;
                self.printerPowerStateButtonClass("btn-danger");
                pstate_text = "Powered Off"

            } else if (pstate == 1) {
                self.printerPowerState = true;
                self.printerPowerStateButtonClass("btn-success");
                pstate_text = "Powered On"

            } else {
                self.printerPowerState = false;
                self.printerPowerStateButtonClass("btn-warning");
                pstate_text = "Unknown"
            }

            self.printerPowerStateText(pstate_text)
        }

        self.togglePrinterPowerState = function() {
            self.powerButtonBusy(false);

            if (!self.printerPowerState) {
                $.ajax({
                    url: API_BASEURL + "plugin/powermanager",
                    type: "POST",
                    dataType: "json",
                    data: JSON.stringify({
                        command: "power_on_printer"
                    }),
                    contentType: "application/json; charset=UTF-8"

                }).done(function(data) {
                    self.delay(function() {
                        self.powerButtonBusy(true);
                    });
                });

            } else {
                $.ajax({
                    url: API_BASEURL + "plugin/powermanager",
                    type: "POST",
                    dataType: "json",
                    data: JSON.stringify({
                        command: "power_off_printer"
                    }),
                    contentType: "application/json; charset=UTF-8"

                }).done(function(data) {
                    self.delay(function() {
                        self.powerButtonBusy(true);
                    });
                    self.disablePopup();
                });

            }
        }

        self.togglePowerManagementState = function() {
            self.powerManagerButtonBusy(false);

            if (!self.isPowerManagementEnabled()) {
                $.ajax({
                    url: API_BASEURL + "plugin/powermanager",
                    type: "POST",
                    dataType: "json",
                    data: JSON.stringify({
                        command: "enable_power_management"
                    }),
                    contentType: "application/json; charset=UTF-8"

                }).done(function(data) {
                    self.isPowerManagementEnabled(true);
                    self.delay(function() {
                        self.powerManagerButtonBusy(true);
                    });
                });

            } else {
                $.ajax({
                    url: API_BASEURL + "plugin/powermanager",
                    type: "POST",
                    dataType: "json",
                    data: JSON.stringify({
                        command: "disable_power_management"
                    }),
                    contentType: "application/json; charset=UTF-8"

                }).done(function(data) {
                    self.disablePopup();
                    self.isPowerManagementEnabled(false);
                    self.delay(function() {
                        self.powerManagerButtonBusy(true);
                    });
                });
            }
        }

        self.abortShutdown = function(abortShutdownValue) {
            self.timeoutPopup.remove();
            self.timeoutPopup = undefined;
            $.ajax({
                url: API_BASEURL + "plugin/powermanager",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({
                    command: "abort_power_off"
                }),
                contentType: "application/json; charset=UTF-8"
            })
        }

        // Hack to remove automatically added Cancel button
        // See https://github.com/sciactive/pnotify/issues/141
        PNotify.prototype.options.confirm.buttons = [];
        self.timeoutPopupText = gettext('...in ');
        self.timeoutPopupOptions = {
            title: gettext('Power Saver Mode'),
            type: 'notice',
            icon: false,
            hide: false,
            confirm: {
                confirm: true,
                buttons: [{
                    text: 'Abort',
                    addClass: 'btn-block btn-danger',
                    promptTrigger: true,
                    click: function(notice, value){
                        notice.remove();
                        notice.get().trigger("pnotify.cancel", [notice, value]);
                    }
                }]
            },
            buttons: {
                closer: false,
                sticker: false,
            },
            history: {
                history: false
            }
        }

        self.disablePopup = function() {
            if (self.timeoutPopup != null) {
                self.timeoutPopup.remove();
                self.timeoutPopup = undefined;
            }
        }


        self.onStartupComplete = function() {
            self.loginState.loggedIn.valueHasMutated();
        }

        self.onDataUpdaterReconnect = function() {
            self.loginState.loggedIn.valueHasMutated();
        }

        self.onDataUpdaterPluginMessage = function(plugin, data) {
            if (plugin != "powermanager") {
                return;
            }

            if (data.type == "pstate_update") {
                self.updatePrinterPowerState(data.pstate);
            }

            if (data.type == "cancel") {
                self.disablePopup();
            }

            if (data.type == "timeout") {
                if (data.timeout_value > 0) {
                    var time_left = data.timeout_value;
                    if (time_left > 60) {
                        time_left = Math.ceil(time_left / 60) + " minutes";

                    } else {
                        time_left = time_left + " seconds";
                    }

                    self.timeoutPopupOptions.text = self.timeoutPopupText + time_left;

                    if (self.timeoutPopup != null) {
                        self.timeoutPopup.update(self.timeoutPopupOptions);

                    } else {
                        self.timeoutPopup = new PNotify(self.timeoutPopupOptions);
                        self.timeoutPopup.get().on('pnotify.cancel', function() {self.abortShutdown(true);});
                    }

                } else {
                    self.disablePopup();
                }
            }
        }

        self.delay = function(cb) {
            setTimeout(cb, self.buttonDelay);
        }
    }

    OCTOPRINT_VIEWMODELS.push([
        PowerManagerViewModel,
        ["loginStateViewModel"],
        document.getElementById("sidebar_plugin_powermanager")
    ]);
});
