#!/usr/bin/python3
"""Render harmless native dialog previews; never invoke a boot command."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,default=Path('/tmp/omarchy-macos-dialogs'))
parser.add_argument('--picker',action='store_true')
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)
source=Path(__file__).resolve().parents[1]
fixture=[{'index':1,'id':'a'*64,'name':"My <img src='https://example.invalid/image'> macOS 日本語",'os':'unknown' if args.picker else 'macos','selectable':True}]
if args.picker:fixture.append({'index':2,'id':'b'*64,'name':'Another system','os':'unknown','selectable':True})
for language in ['en','ar','he','et']:
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);(root/'language').write_text(language)
        runtime=root/'runtime';runtime.mkdir(mode=0o700)
        modules=root/'qs';modules.mkdir()
        for name in ['Commons','Ui']:(modules/name).symlink_to(Path('/usr/share/omarchy/shell')/name,target_is_directory=True)
        output=args.output/(language+('-picker' if args.picker else '-confirm')+'.png')
        qml='''import QtQuick
import Quickshell
ShellRoot {
 id: root
 property var preview: null
 Component.onCompleted: {
  var component = Qt.createComponent(SOURCE)
  if (component.status === Component.Error) { console.error(component.errorString()); Qt.quit(); return }
  preview = component.createObject(root)
  preview.openPreview(FIXTURE)
 }
 Timer { running: true; interval: 1200
  onTriggered: {
   if (!root.preview) { Qt.quit(); return }
   root.preview.previewContent.grabToImage(function(result) { result.saveToFile(OUTPUT); Qt.quit() })
  }
 }
}'''.replace('SOURCE',json.dumps((source/'Confirmation.qml').as_uri())).replace('FIXTURE',json.dumps(fixture)).replace('OUTPUT',json.dumps(str(output)))
        (root/'shell.qml').write_text(qml)
        env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','QT_QPA_PLATFORMTHEME':'basic','QT_QUICK_CONTROLS_STYLE':'Basic','XDG_CONFIG_HOME':str(root),'XDG_RUNTIME_DIR':str(runtime),'OMARCHY_LANGUAGE_FILE':str(root/'language'),'QML_IMPORT_PATH':str(root),'OMARCHY_PATH':'/usr/share/omarchy'}
        result=subprocess.run(['/usr/bin/quickshell','-p',str(root/'shell.qml')],env=env,capture_output=True,text=True,timeout=10)
        if result.returncode or not output.exists():raise RuntimeError(result.stdout+result.stderr)
        print(output)
