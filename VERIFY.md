# Verification and remaining hardware checks

## Automated and read-only checks

- Regression tests cover metadata checksums and unsupported APFS layouts, identity-based selection, cancellation, failures, cleanup, customized menu restoration, and translations.
- Read-only hardware inspection on an Apple MacBook Pro (14-inch, M1 Pro, 2021) found macOS Sequoia on nvme0n1p2 with a sealed System volume and Omarchy's unsealed stub on nvme0n1p3. No label heuristic is needed for that installation.
- The next-boot write and reboot actions are mocked in automated tests. Listing candidates does not select a target.
- Removal watcher checks are event-driven; a short delay tolerates a plugin's atomic replacement during updates. A merely missing manifest in an existing directory does not trigger cleanup.

## Completed live checks

- The installed password-free helper identified macOS Sequoia as a sealed macOS candidate and Omarchy as an unsealed/unknown stub, using APFS metadata rather than label patterns.
- Normal `omarchy plugin remove` triggered the root watcher and restored the System menu. The helper, trusted library directory, root installation record, sudo entry, watcher unit files, and enabled path link were removed. The removed helper was no longer callable through sudo.
- Native confirmation and volume-picker previews rendered in English, Estonian, Arabic, and Hebrew. Layout mirrored for Arabic/Hebrew, long text wrapped, and markup-shaped volume names remained literal text. This is rendering verification, not native-speaker linguistic review.
- Live menu labels switched from Estonian to French in an isolated QML instance without a restart; the desktop user's language was unchanged.

## Upgrade regression coverage

Disposable installation tests cover repeated setup, replacement of privileged code only during explicit setup, preservation of original removal state and user edits, migration of legacy menu backups, removal of obsolete trusted modules, and retry after an injected upgrade failure. These checks run in CI without changing the host installation or boot target.

## Independent recovery review

Claude performed read-only static reviews of the privileged lifecycle and APFS/parser changes. Confirmed findings were addressed in separate commits with focused regression tests. The suite now contains 114 tests, including interrupted rollback, atomic restoration, damaged-record recovery, watcher activation before privilege grants, and stale-state reconciliation. Static review does not replace the pending hardware and linguistic checks below.

## Systemd retry verification

On the development machine, disposable user-manager targets reached `active` while their wanted services repeatedly failed with `Restart=on-failure`, both for `Type=oneshot` and `Type=exec`. After four seconds each service had restarted three times, with no pending jobs. The temporary units and runtime links were then removed. This checks the suspected restart-ordering behavior on the installed systemd version; it is not a full machine boot test.

The cleanup unit now requires the recorded plugin filesystem (including nested mounts below the config directory) through `RequiresMountsFor`. Config directories must still be available to the system manager; session-only encrypted or externally managed mounts need separate integration testing. The installed Omarchy `--execute` reboot path was inspected and propagates synchronous systemctl failure.

## Full boot cycle — pending user execution

This check interrupts the session. Save work first and perform it when ready:

1. Record the default boot system and candidates using the read-only check below. Verify exactly the intended macOS volume is identified.
2. Open System > Reboot into macOS. First choose No and verify the system stays in Linux.
3. Reopen the action and choose Yes. Verify the machine boots the intended macOS installation.
4. Restart normally from macOS. Verify the machine returns to the original default system (Linux on the development machine).
5. Report the macOS version, machine, and result here. Do not mark this check passed without observing both boots.

```sh
sudo -n /usr/local/libexec/omarchy-reboot-macos-helper --list
```

## Complete removal

With the plugin installed and setup complete, run normal Omarchy plugin removal. Within a few seconds verify:

- The System menu returns to its prior customization, including the prior Shutdown command.
- `/usr/local/libexec/omarchy-reboot-macos-helper`, `/usr/local/lib/omarchy-reboot-macos`, `/etc/omarchy-reboot-macos.json`, and `/etc/sudoers.d/90-omarchy-reboot-macos-plugin` are gone.
- The cleanup path and service unit files are gone, with no enabled path unit left.
- Unrelated menu settings and edits made while installed survive removal.

Menu backups made by older versions may remain intentionally. User-created replacement commands are not deleted.
