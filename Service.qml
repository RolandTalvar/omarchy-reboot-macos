import QtQuick
import Quickshell
import Quickshell.Io

Item {
  property var shell: null

  IpcHandler {
    target: "rolandtlvr.reboot-macos"
    function reboot(): void {
      var script = Qt.resolvedUrl("reboot_macos.py").toString()
      if (script.indexOf("file://") !== 0) return
      // Quickshell passes argv directly; presentation wrapper gets a quoted path.
      var path = decodeURIComponent(script.slice(7))
      var quoted = "'" + path.replace(/'/g, "'\\''") + "'"
      Quickshell.execDetached(["omarchy-launch-floating-terminal-with-presentation", "/usr/bin/python3 " + quoted])
    }
    function ping(): string { return "ready" }
  }
}
