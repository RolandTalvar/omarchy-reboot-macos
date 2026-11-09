#!/usr/bin/python3
"""Native UI regression: cancellation is disabled after accepting a reboot.
The copied dialog uses only a slow fake backend; no boot commands are run.
"""
from pathlib import Path
import json,os,subprocess,tempfile
repo=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
 root=Path(directory);(root/'language').write_text('en')
 runtime=root/'runtime';runtime.mkdir(mode=0o700)
 (root/'Confirmation.qml').write_text((repo/'Confirmation.qml').read_text())
 (root/'i18n').symlink_to(repo/'i18n',target_is_directory=True)
 (root/'qs').mkdir()
 for name in ['Commons','Ui']:(root/'qs'/name).symlink_to(Path('/usr/share/omarchy/shell')/name,target_is_directory=True)
 marker=root/'backend-completed'
 # Replace the entire backend with a harmless slow process in this test copy.
 (root/'reboot_macos.py').write_text('import time\nfrom pathlib import Path\ntime.sleep(0.5)\nPath('+repr(str(marker))+').write_text("completed")\n')
 (root/'shell.qml').write_text('''import QtQuick
import Quickshell
ShellRoot {
 id: root
 property var confirmation: null
 function findNo(item) {
  if (item.text === "No" && typeof item.clicked === "function") return item
  if (item.children) for (var i=0;i<item.children.length;i++) { var result=findNo(item.children[i]); if (result) return result }
  return null
 }
 Component.onCompleted: {
  var component=Qt.createComponent("Confirmation.qml")
  if (component.status===Component.Error) { console.error(component.errorString()); Qt.quit(); return }
  confirmation=component.createObject(root)
  confirmation.openPreview([{index:1,id:"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",name:"Fake system",os:"macos",selectable:true}])
  confirmation.previewMode=false
  confirmation.accept()
 }
 Timer { interval:100;running:true;onTriggered: {
  var button=root.findNo(root.confirmation.previewContent)
  console.log("No enabled while backend runs:",button.enabled)
  button.clicked()
  root.confirmation.cancel()
  console.log("Dialog visible after No:",root.confirmation.visible)
 }}
 Timer { interval:1500;running:true;onTriggered:Qt.quit() }
}''')
 env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','QT_QPA_PLATFORMTHEME':'basic','QT_QUICK_CONTROLS_STYLE':'Basic','XDG_CONFIG_HOME':str(root),'XDG_RUNTIME_DIR':str(runtime),'OMARCHY_LANGUAGE_FILE':str(root/'language'),'QML_IMPORT_PATH':str(root),'OMARCHY_PATH':'/usr/share/omarchy'}
 result=subprocess.run(['/usr/bin/quickshell','-p',str(root/'shell.qml')],env=env,text=True,capture_output=True,timeout=10)
 print(result.stdout,result.stderr)
 print('Accepted fake backend completed, with cancellation correctly disabled:',marker.exists())
 assert 'No enabled while backend runs: false' in result.stdout
 assert 'Dialog visible after No: true' in result.stdout
 assert marker.exists()
