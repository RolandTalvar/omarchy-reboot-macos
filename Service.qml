import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons as Commons

Item {
  id: root
  property var shell: null

  Commons.Translations {
    id: strings
    directory: Qt.resolvedUrl("i18n")
  }
  readonly property string menuStrings: JSON.stringify({
    "menu.label": strings.t("menu.label"),
    "menu.description": strings.t("menu.description"),
    "menu.shutdown": strings.t("menu.shutdown")
  })
  property bool syncPending: false
  function scheduleSync() {
    syncPending = true
    syncTimer.restart()
  }
  onMenuStringsChanged: scheduleSync()
  Component.onCompleted: scheduleSync()

  Timer {
    id: syncTimer
    interval: 150
    onTriggered: {
      if (syncProcess.running || !root.syncPending) return
      root.syncPending = false
      syncProcess.command = ["/usr/bin/python3", "-B", decodeURIComponent(Qt.resolvedUrl("sync_menu.py").toString().slice(7)), root.menuStrings]
      syncProcess.running = true
    }
  }
  Process {
    id: syncProcess
    onExited: (exitCode, exitStatus) => {
      if (exitCode !== 0) console.warn("Reboot into macOS: menu translation sync failed")
      if (root.syncPending) syncTimer.restart()
    }
  }

  IpcHandler {
    target: "rolandtlvr.reboot-macos"
    function reboot(): void {
      var script = Qt.resolvedUrl("reboot_macos.py").toString()
      if (script.indexOf("file://") !== 0) return
      // Quickshell passes argv directly; presentation wrapper gets a quoted path.
      var path = decodeURIComponent(script.slice(7))
      var quoted = "'" + path.replace(/'/g, "'\\''") + "'"
      Quickshell.execDetached(["omarchy-launch-floating-terminal-with-presentation", "/usr/bin/python3 -B " + quoted])
    }
    function ping(): string { return "ready" }
  }
}
