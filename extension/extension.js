import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const BUS_NAME = 'local.SpeakText';
const OBJECT_PATH = '/local/SpeakText';
const INTERFACE_NAME = 'local.SpeakText.Control';
const DESKTOP_ID = 'local.SpeakText.desktop';

const CONTROL_XML = `
<node>
  <interface name="${INTERFACE_NAME}">
    <method name="GetStatus">
      <arg name="state" type="s" direction="out"/>
      <arg name="message" type="s" direction="out"/>
      <arg name="can_copy" type="b" direction="out"/>
    </method>
    <method name="ActivateWindow"/>
    <method name="CopyLastTranscript">
      <arg name="copied" type="b" direction="out"/>
    </method>
    <method name="CancelRecording"/>
    <method name="Quit"/>
    <signal name="StatusChanged">
      <arg name="state" type="s"/>
      <arg name="message" type="s"/>
      <arg name="can_copy" type="b"/>
    </signal>
  </interface>
</node>`;

const ControlProxy = Gio.DBusProxy.makeProxyWrapper(CONTROL_XML);

const ICONS = {
    Starting: 'content-loading-symbolic',
    Ready: 'audio-input-microphone-symbolic',
    Recording: 'audio-input-microphone-symbolic',
    Transcribing: 'content-loading-symbolic',
    Inserting: 'document-send-symbolic',
    Error: 'dialog-error-symbolic',
    Disconnected: 'microphone-disabled-symbolic',
};

const SpeakTextIndicator = GObject.registerClass(
class SpeakTextIndicator extends PanelMenu.Button {
    _init(logger) {
        super._init(0.0, 'SpeakText');
        this._logger = logger;

        this._icon = new St.Icon({
            icon_name: ICONS.Starting,
            style_class: 'system-status-icon',
        });
        this.add_child(this._icon);

        this._statusItem = new PopupMenu.PopupMenuItem('Starting SpeakText…', {
            reactive: false,
        });
        this.menu.addMenuItem(this._statusItem);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this._openItem = this.menu.addAction('Open SpeakText', () => {
            this._activateWindow();
        });
        this._cancelItem = this.menu.addAction('Cancel recording', () => {
            this._cancelRecording();
        });
        this._cancelItem.setSensitive(false);
        this._copyItem = this.menu.addAction('Copy last transcript', () => {
            this._copyLastTranscript();
        });
        this._copyItem.setSensitive(false);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._quitItem = this.menu.addAction('Quit SpeakText', () => {
            this._quitApplication();
        });

        this._proxy = new ControlProxy(
            Gio.DBus.session,
            BUS_NAME,
            OBJECT_PATH,
            (_proxy, error) => {
                if (error)
                    this._logger.warn(`D-Bus connection failed: ${error.message}`);
                if (this._proxy)
                    this._ownerChanged();
            }
        );
        this._ownerChangedId = this._proxy.connect(
            'notify::g-name-owner', () => this._ownerChanged());
        this._signalId = this._proxy.connect(
            'g-signal', (_proxy, _sender, signalName, parameters) => {
                if (signalName === 'StatusChanged') {
                    const [state, message, canCopy] = parameters.deepUnpack();
                    this._setStatus(state, message, canCopy);
                }
            });
    }

    _ownerChanged() {
        if (!this._proxy)
            return;
        const running = Boolean(this._proxy.get_name_owner());
        this._quitItem.setSensitive(running);
        if (!running)
            this._cancelItem.setSensitive(false);
        if (running) {
            this._openItem.label.text = 'Open SpeakText';
            this._refreshStatus();
        } else {
            this._openItem.label.text = 'Start SpeakText';
            this._setStatus('Disconnected', 'SpeakText is not running', false);
        }
    }

    _refreshStatus() {
        this._proxy.GetStatusRemote((result, error) => {
            if (!this._proxy)
                return;
            if (error) {
                this._logger.warn(`Could not read status: ${error.message}`);
                return;
            }
            const [state, message, canCopy] = result;
            this._setStatus(state, message, canCopy);
        });
    }

    _setStatus(state, message, canCopy) {
        this._icon.icon_name = ICONS[state] ?? ICONS.Error;
        if (state === 'Recording')
            this._icon.add_style_class_name('speaktext-recording');
        else
            this._icon.remove_style_class_name('speaktext-recording');
        this._statusItem.label.text = message || state;
        this._cancelItem.setSensitive(state === 'Recording');
        this._copyItem.setSensitive(canCopy);
        this.accessible_name = `SpeakText: ${state}`;
    }

    _activateWindow() {
        if (!this._proxy)
            return;
        if (this._proxy.get_name_owner()) {
            this._proxy.ActivateWindowRemote((_result, error) => {
                if (error)
                    this._logger.warn(`Could not open SpeakText: ${error.message}`);
            });
            return;
        }

        const appInfo = Gio.DesktopAppInfo.new(DESKTOP_ID);
        if (!appInfo) {
            this._logger.warn('SpeakText desktop entry was not found');
            return;
        }
        try {
            appInfo.launch([], null);
        } catch (error) {
            this._logger.warn(`Could not start SpeakText: ${error.message}`);
        }
    }

    _copyLastTranscript() {
        if (!this._proxy?.get_name_owner())
            return;
        this._proxy.CopyLastTranscriptRemote((_result, error) => {
            if (error)
                this._logger.warn(`Could not copy transcript: ${error.message}`);
        });
    }

    _cancelRecording() {
        if (!this._proxy?.get_name_owner())
            return;
        this._proxy.CancelRecordingRemote((_result, error) => {
            if (error)
                this._logger.warn(`Could not cancel recording: ${error.message}`);
        });
    }

    _quitApplication() {
        if (!this._proxy?.get_name_owner())
            return;
        this._proxy.QuitRemote((_result, error) => {
            if (error)
                this._logger.warn(`Could not quit SpeakText: ${error.message}`);
        });
    }

    destroy() {
        if (this._proxy && this._ownerChangedId)
            this._proxy.disconnect(this._ownerChangedId);
        if (this._proxy && this._signalId)
            this._proxy.disconnect(this._signalId);
        this._proxy = null;
        super.destroy();
    }
});

export default class SpeakTextExtension extends Extension {
    enable() {
        this._indicator = new SpeakTextIndicator(this.getLogger());
        Main.panel.addToStatusArea(this.uuid, this._indicator, 0, 'right');
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
