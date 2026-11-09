#!/usr/bin/python3 -I
"""Root setup and event-driven cleanup. Never run code from a removed plugin."""
import json
import hashlib
import fcntl
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import tempfile

LIB = Path('/usr/local/lib/omarchy-reboot-macos')
HELPER = Path('/usr/local/libexec/omarchy-reboot-macos-helper')
RULE = Path('/etc/sudoers.d/90-omarchy-reboot-macos-plugin')
RECORD = Path('/etc/omarchy-reboot-macos.json')
UNIT = 'omarchy-reboot-macos-cleanup'
UNITS = Path('/etc/systemd/system')
TRANSACTION = Path('/var/lib/omarchy-reboot-macos/install-transaction')
LEGACY = Path('/etc/sudoers.d/90-omarchy-reboot-macos')
BLESS = Path('/usr/bin/asahi-bless')
LOCK = Path('/run/lock/omarchy-reboot-macos.lock')
ENV = {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'}

def run(*args, **kwargs): return subprocess.run(list(args),env=ENV,check=True,**kwargs)

class RecoveryError(RuntimeError):
    pass


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def sync_tree(path):
    if path.is_symlink(): return
    if path.is_dir():
        for child in path.iterdir(): sync_tree(child)
        sync_directory(path)
    else:
        with path.open('rb') as source: os.fsync(source.fileno())


def directory(path, mode=0o755, exist_ok=True):
    if not path.parent.exists(): directory(path.parent)
    path.mkdir(mode=mode, exist_ok=exist_ok)
    if path.is_symlink(): raise ValueError('Refusing a symlinked installation directory')
    path.chmod(mode)
    sync_directory(path)
    sync_directory(path.parent)


def write_root(path,text,mode=0o644):
    if not path.parent.exists(): directory(path.parent)
    fd,temp = tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'w') as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp,path)
        sync_directory(path.parent)
    finally: Path(temp).unlink(missing_ok=True)

def unlink_synced(path):
    if path.exists() or path.is_symlink():
        path.unlink()
        sync_directory(path.parent)


def stop_watcher():
    if (UNITS/(UNIT+'.path')).exists():
        run('/usr/bin/systemctl','disable','--now',UNIT+'.path')
    else:
        if watcher_state()['active']: run('/usr/bin/systemctl','stop',UNIT+'.path')
        unlink_synced(UNITS/'multi-user.target.wants'/(UNIT+'.path'))


def retire_legacy_rule(account):
    known = {
        f'{account} ALL=(root) NOPASSWD: /usr/bin/asahi-bless --next --set-boot macOS Sequoia --yes',
        f'{account} ALL=(root) NOPASSWD: /usr/bin/asahi-bless --next --set-boot-macos --yes',
    }
    if LEGACY.exists() and LEGACY.read_text().strip() in known:
        unlink_synced(LEGACY)


def remove(record):
    # Revoke access first, even if an invalid user menu needs later repair.
    unlink_synced(RULE)
    unlink_synced(HELPER)
    retire_legacy_rule(record['account'])
    menu_code = LIB/'menu_state.py'
    if menu_code.exists():
        run('/usr/bin/runuser','-u',record['account'],'--','/usr/bin/python3','-I',str(menu_code),'remove',record['config'])
    stop_watcher()
    for suffix in ['path','service']: unlink_synced(UNITS/(UNIT+'.'+suffix))
    run('/usr/bin/systemctl','daemon-reload')
    if LIB.exists():
        shutil.rmtree(LIB)
        sync_directory(LIB.parent)
    # Keep the record until every other component is gone, so a fresh copy of
    # the installer can resume even if the installed cleanup code was removed.
    unlink_synced(RECORD)


def watcher_state():
    state = {}
    for key, command in [('active', 'is-active'), ('enabled', 'is-enabled')]:
        result = subprocess.run(['/usr/bin/systemctl', command, UNIT+'.path'],
                                env=ENV, text=True, capture_output=True, check=False)
        state[key] = result.returncode == 0
    return state


def user_menu(stage, operation, record):
    run('/usr/bin/runuser', '-u', record['account'], '--', '/usr/bin/python3',
        '-I', str(stage/'menu_install.py'), operation, record['config'])


def artifacts():
    return [LIB, HELPER, RULE, RECORD, UNITS/(UNIT+'.path'),
            UNITS/(UNIT+'.service'), LEGACY]


def backup_digest(path):
    digest = hashlib.sha256()
    paths = [path] + sorted(path.rglob('*')) if path.is_dir() else [path]
    for item in paths:
        digest.update(str(item.relative_to(path) if item != path else '.').encode()+b'\0')
        if item.is_symlink(): digest.update(b'link:'+os.fsencode(os.readlink(item)))
        elif item.is_dir(): digest.update(b'dir')
        else:
            digest.update(b'file:')
            with item.open('rb') as data:
                for chunk in iter(lambda:data.read(65536), b''): digest.update(chunk)
    return digest.hexdigest()


def snapshot_artifacts():
    backup = TRANSACTION/'backup'
    directory(backup, 0o700, exist_ok=False)
    entries = []
    for index, path in enumerate(artifacts()):
        entry = {'path': str(path), 'exists': path.exists() or path.is_symlink()}
        if entry['exists']:
            saved = backup/str(index)
            if path.is_symlink():
                raise ValueError('Refusing to replace a symlinked installation artifact.')
            info = path.stat()
            entry.update(directory=path.is_dir(), mode=info.st_mode & 0o7777,
                         uid=info.st_uid, gid=info.st_gid)
            if path.is_dir(): shutil.copytree(path, saved, symlinks=True)
            else: shutil.copy2(path, saved)
            entry['digest'] = backup_digest(saved)
        entries.append(entry)
    sync_tree(backup)
    sync_directory(TRANSACTION)
    return entries


def restore_artifacts(entries):
    # Validate every backup before touching any live artifact. Incomplete old
    # cleanup must not turn a retry into destruction of a working installation.
    for index, entry in enumerate(entries):
        if entry['exists']:
            saved = TRANSACTION/'backup'/str(index)
            if not saved.exists() or 'digest' not in entry or backup_digest(saved) != entry['digest']:
                raise RecoveryError('A transaction backup is missing or incomplete; installed files were left untouched.')
    for index, entry in enumerate(entries):
        path = Path(entry['path'])
        if path.is_dir() and not path.is_symlink(): shutil.rmtree(path)
        else: path.unlink(missing_ok=True)
        if entry['exists']:
            path.parent.mkdir(parents=True, exist_ok=True)
            saved = TRANSACTION/'backup'/str(index)
            if entry['directory']: shutil.copytree(saved, path, symlinks=True)
            else: shutil.copy2(saved, path)
            os.chmod(path, entry['mode'])
            os.chown(path, entry['uid'], entry['gid'])
            sync_tree(path)
        if path.parent.exists(): sync_directory(path.parent)


def finish_transaction():
    # Retire all recovery authority durably before deleting its dependencies.
    # A crash during rmtree then leaves only disposable, unreferenced garbage.
    for name in ['journal.json','journal.mirror.json']:
        (TRANSACTION/name).unlink(missing_ok=True)
    sync_directory(TRANSACTION)
    shutil.rmtree(TRANSACTION)
    try: TRANSACTION.parent.rmdir()
    except OSError: pass


def write_journal(saved):
    text = json.dumps(saved)
    # Both copies are durable before any operation they authorize proceeds.
    write_root(TRANSACTION/'journal.json', text, 0o600)
    write_root(TRANSACTION/'journal.mirror.json', text, 0o600)


def read_journal():
    errors = []
    for name in ['journal.json','journal.mirror.json']:
        try:
            saved = json.loads((TRANSACTION/name).read_text())
            if saved['phase'] not in ['installing','restored','committed']:
                raise ValueError('Invalid transaction phase')
            if [entry['path'] for entry in saved['artifacts']] != [str(path) for path in artifacts()]:
                raise ValueError('Invalid transaction artifact paths')
            if not isinstance(saved['menu_started'], bool): raise ValueError('Invalid menu phase')
            if not re.fullmatch(r'[a-z_][a-z0-9_-]*',saved['record']['account']): raise ValueError('Invalid transaction user')
            return saved
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(str(error))
    raise RecoveryError('Both transaction journals are unreadable. Installed files and backups were left untouched. '
                        'An administrator must restore a valid journal from backup; see README recovery instructions. '
                        + '; '.join(errors))


def recover_installation():
    journal = TRANSACTION/'journal.json'
    if not journal.exists() and not (TRANSACTION/'journal.mirror.json').exists():
        if TRANSACTION.exists(): finish_transaction()
        return
    saved = read_journal()
    stage = TRANSACTION/'stage'
    if saved['phase'] == 'committed':
        user_menu(stage, 'commit', saved['record'])
        finish_transaction()
        return
    if saved['phase'] == 'installing':
        if (UNITS/(UNIT+'.path')).exists():
            run('/usr/bin/systemctl', 'disable', '--now', UNIT+'.path')
        restore_artifacts(saved['artifacts'])
        saved['phase'] = 'restored'
        write_journal(saved)
    if saved['menu_started']:
        user_menu(stage, 'rollback', saved['record'])
    run('/usr/bin/systemctl', 'daemon-reload')
    if saved['watcher']['enabled']:
        run('/usr/bin/systemctl', 'enable', UNIT+'.path')
    if saved['watcher']['active']:
        run('/usr/bin/systemctl', 'start', UNIT+'.path')
    if RULE.exists(): run('/usr/bin/visudo', '-cf', str(RULE))
    finish_transaction()


def stage_installation(account, config, source):
    directory(TRANSACTION.parent, 0o755)
    directory(TRANSACTION, 0o711, exist_ok=False)
    stage = TRANSACTION/'stage'
    directory(stage, 0o755, exist_ok=False)
    for name in ['apfs_metadata.py', 'menu_state.py', 'lifecycle.py',
                 'menu_install.py', 'translations.py', 'boot_helper.py']:
        text = (source/name).read_text()
        compile(text, name, 'exec')
        write_root(stage/name, text)
    directory(stage/'i18n', 0o755, exist_ok=False)
    for catalog in (source/'i18n').glob('*.json'):
        if catalog.is_symlink(): raise ValueError('Symlinked translation catalog')
        text = catalog.read_text()
        if not isinstance(json.loads(text), dict): raise ValueError('Invalid catalog')
        write_root(stage/'i18n'/catalog.name, text)
    rule = (f'{account} ALL=(root) NOPASSWD: {HELPER} --list, '
            f'{HELPER} ^--select-next [a-f0-9]{{64}}$, '
            f'{HELPER} ^--clear-next [a-f0-9]{{64}}$\n')
    write_root(stage/'sudoers', rule, 0o440)
    run('/usr/bin/visudo', '-cf', str(stage/'sudoers'))
    plugin = config/'omarchy/plugins/rolandtlvr.reboot-macos'
    watch = str(plugin.parent).replace('%','%%')
    write_root(stage/(UNIT+'.path'), f'[Unit]\nDescription=Watch for removal of the macOS reboot plugin\n\n[Path]\nPathChanged={watch}\nUnit={UNIT}.service\n\n[Install]\nWantedBy=multi-user.target\n')
    write_root(stage/(UNIT+'.service'), f'[Unit]\nDescription=Clean up removed macOS reboot plugin\nStartLimitIntervalSec=0\n\n[Service]\nType=oneshot\nRestart=on-failure\nRestartSec=15s\nExecStartPre=/usr/bin/sleep 2\nExecStart=/usr/bin/python3 -I {LIB}/lifecycle.py check\n')
    run('/usr/bin/systemd-analyze', 'verify', str(stage/(UNIT+'.path')),
        str(stage/(UNIT+'.service')))
    return stage


def install(account, config, source):
    user = pwd.getpwnam(account)
    if user.pw_uid == 0: raise ValueError('Install for a desktop user, not root')
    if RECORD.exists() and json.loads(RECORD.read_text())['account'] != account:
        raise ValueError('This helper is already installed for another user')
    config = Path(config).resolve()
    if any(ord(ch) < 32 for ch in str(config)): raise ValueError('Unsupported config path')
    plugin = config/'omarchy/plugins/rolandtlvr.reboot-macos'
    if not (plugin/'manifest.json').is_file(): raise ValueError('Install the Omarchy plugin first')
    if not BLESS.is_file(): raise ValueError('Install asahi-bless first')
    # Retry an interrupted installation from its durable journal before making
    # new changes. The journal and staged code are administrator-owned.
    recover_installation()
    record = {'version':1, 'account':account, 'config':str(config), 'plugin':str(plugin)}
    try:
        stage = stage_installation(account, config, Path(source))
        saved = {'phase':'installing', 'record':record,
                 'watcher':watcher_state(), 'artifacts':snapshot_artifacts(),
                 'menu_started':False}
        write_journal(saved)
        if (UNITS/(UNIT+'.path')).exists():
            run('/usr/bin/systemctl', 'disable', '--now', UNIT+'.path')
        trusted_modules = ['apfs_metadata.py', 'menu_state.py', 'lifecycle.py',
                           'menu_install.py', 'translations.py']
        directory(LIB, 0o755)
        for name in trusted_modules:
            write_root(LIB/name, (stage/name).read_text())
        # This directory is an installed snapshot, not an overlay. Obsolete
        # modules and bytecode must not survive a successful upgrade. The
        # transaction still restores the whole old tree if a later step fails.
        for entry in LIB.iterdir():
            if entry.name not in trusted_modules:
                if entry.is_dir() and not entry.is_symlink(): shutil.rmtree(entry)
                else: entry.unlink()
        write_root(HELPER, (stage/'boot_helper.py').read_text(), 0o755)
        write_root(RULE, (stage/'sudoers').read_text(), 0o440)
        write_root(RECORD, json.dumps(record)+'\n')
        for suffix in ['path','service']:
            name = UNIT+'.'+suffix
            write_root(UNITS/name, (stage/name).read_text())
        retire_legacy_rule(account)
        saved['menu_started'] = True
        write_journal(saved)
        user_menu(stage, 'install', record)
        run('/usr/bin/visudo', '-c')
        run('/usr/bin/systemctl', 'daemon-reload')
        if not (plugin/'manifest.json').is_file():
            raise ValueError('Plugin was removed during installation')
        run('/usr/bin/systemctl', 'enable', '--now', UNIT+'.path')
        if not (plugin/'manifest.json').is_file():
            raise ValueError('Plugin was removed while enabling its watcher')
        # Both sides are now installed. Persist the commit decision before
        # deleting snapshots so an interrupted cleanup never rolls back half.
        saved['phase'] = 'committed'
        write_journal(saved)
    except BaseException:
        recover_installation()
        raise
    user_menu(stage, 'commit', record)
    finish_transaction()

def main(args):
    if os.geteuid()!=0: raise ValueError('Administrator authentication required')
    os.umask(0o022)
    descriptor = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        if os.fstat(lock.fileno()).st_uid != os.getuid():
            raise ValueError('Setup lock belongs to another user')
        fcntl.flock(lock, fcntl.LOCK_EX)
        dispatch(args)


def revoke_access(account):
    unlink_synced(RULE)
    unlink_synced(HELPER)
    retire_legacy_rule(account)


def cleanup_requested(record):
    revoke_access(record['account'])
    try:
        if TRANSACTION.exists(): recover_installation()
        current=json.loads(RECORD.read_text()) if RECORD.exists() else record
        remove(current)
    except BaseException:
        # Recovery may have restored an earlier permission rule before a menu
        # failure. Every failed cleanup attempt must still leave it revoked.
        revoke_access(record['account'])
        raise


def dispatch(args):
    if args==['check']:
        record=json.loads(RECORD.read_text()) if RECORD.exists() else None
        if record and not Path(record['plugin']).exists():
            cleanup_requested(record)
            return
        if TRANSACTION.exists(): recover_installation()
        if RECORD.exists():
            record=json.loads(RECORD.read_text())
            if not Path(record['plugin']).exists(): cleanup_requested(record)
    elif len(args)==4 and args[0] in ['install','remove']:
        mode,account,config,source=args
        if not re.fullmatch(r'[a-z_][a-z0-9_-]*',account): raise ValueError('Invalid account')
        if mode=='install': install(account,config,source)
        else: remove_for_account(account,config)
    else: raise ValueError('Invalid setup operation')


def remove_for_account(account, config):
    record=json.loads(RECORD.read_text()) if RECORD.exists() else {'account':account,'config':str(Path(config).resolve())}
    if record['account']!=account: raise ValueError('Installation belongs to another user')
    cleanup_requested(record)

if __name__=='__main__': main(sys.argv[1:])
