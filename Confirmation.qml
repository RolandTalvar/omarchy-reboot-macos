import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons as Commons
import qs.Ui as Ui

FloatingWindow {
  id: root
  visible: false
  title: strings.t("menu.label")
  implicitWidth: 560
  implicitHeight: Math.min(560, content.implicitHeight + 48)
  minimumSize: Qt.size(400, 220)
  color: Commons.Color.background
  property alias previewContent: content
  property var volumes: []
  property var choices: []
  property var selected: null
  property bool loading: false
  property bool failed: false
  property bool previewMode: false
  readonly property string script: decodeURIComponent(Qt.resolvedUrl("reboot_macos.py").toString().slice(7))

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  function populate(candidates) {
    volumes = candidates
    choices = candidates.filter(function(v) { return v.selectable && typeof v.name === "string" && /^[a-f0-9]{64}$/.test(v.id) })
    var macos = choices.filter(function(v) { return v.os === "macos" })
    selected = macos.length === 1 ? macos[0] : null
    failed = choices.length === 0
    loading = false
    cancelButton.forceActiveFocus()
  }
  function open() {
    if (listProcess.running || bootProcess.running) return
    previewMode = false
    selected = null; choices = []; volumes = []; failed = false; loading = true
    visible = true
    listProcess.running = true
    cancelButton.forceActiveFocus()
  }
  function openPreview(candidates) {
    previewMode = true
    populate(candidates)
    visible = true
  }
  function accept() {
    if (!selected || loading || failed) return
    if (previewMode) { visible = false; return }
    loading = true
    bootProcess.command = ["/usr/bin/python3", "-B", script, "--confirmed", selected.id, JSON.stringify(volumes)]
    bootProcess.running = true
  }

  Process {
    id: listProcess
    command: ["/usr/bin/python3", "-B", root.script, "--list"]
    stdout: StdioCollector { id: listOutput }
    onExited: (code, status) => {
      if (code === 0) {
        try { root.populate(JSON.parse(listOutput.text)) }
        catch (e) { root.failed = true; root.loading = false }
      } else { root.failed = true; root.loading = false }
    }
  }
  Process {
    id: bootProcess
    onExited: (code, status) => {
      root.loading = false
      if (code === 0) root.visible = false
      else root.failed = true
    }
  }

  ColumnLayout {
    id: content
    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 24 }
    spacing: 20
    LayoutMirroring.enabled: Commons.I18n.rightToLeft
    LayoutMirroring.childrenInherit: true
    Keys.onEscapePressed: root.visible = false

    Text {
      Layout.fillWidth: true
      text: strings.t("menu.label")
      textFormat: Text.PlainText
      color: Commons.Color.foreground
      font.family: Commons.Style.font.family
      font.pixelSize: Commons.Style.font.body + 4
      font.bold: true
      wrapMode: Text.Wrap
      horizontalAlignment: Commons.I18n.rightToLeft ? Text.AlignRight : Text.AlignLeft
    }
    Text {
      Layout.fillWidth: true
      text: root.failed ? strings.t("failed") : root.loading ? "…" : root.selected
        ? strings.t("confirm").arg("\u2068" + root.selected.name + "\u2069") : strings.t("picker")
      textFormat: Text.PlainText
      color: root.failed ? Commons.Color.urgent : Commons.Color.foreground
      font.family: Commons.Style.font.family
      font.pixelSize: Commons.Style.font.body
      wrapMode: Text.Wrap
      horizontalAlignment: Commons.I18n.rightToLeft ? Text.AlignRight : Text.AlignLeft
    }
    ListView {
      visible: !root.selected && !root.loading && !root.failed
      Layout.fillWidth: true
      Layout.preferredHeight: visible ? Math.min(contentHeight, 240) : 0
      clip: true
      spacing: 6
      model: root.choices
      delegate: Ui.Button {
        required property var modelData
        width: ListView.view.width
        text: modelData.name
        focusable: true
        bordered: true
        onClicked: root.selected = modelData
      }
    }
    RowLayout {
      Layout.alignment: Qt.AlignRight
      spacing: 12
      Ui.Button {
        id: cancelButton
        text: strings.t("no")
        focusable: true
        bordered: true
        onClicked: root.visible = false
      }
      Ui.Button {
        text: strings.t("yes")
        enabled: !!root.selected && !root.loading && !root.failed
        focusable: true
        bordered: true
        onClicked: root.accept()
      }
    }
  }
}
