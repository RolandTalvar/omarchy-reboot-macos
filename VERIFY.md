# Verification and remaining hardware checks

## Automated and read-only checks

- Regression tests cover metadata checksums and unsupported APFS layouts, identity-based selection, cancellation, failures, cleanup, customized menu restoration, and translations.
- Read-only hardware inspection on an Apple MacBook Pro (14-inch, M1 Pro, 2021) found macOS Sequoia on nvme0n1p2 with a sealed System volume and Omarchy's unsealed stub on nvme0n1p3. No label heuristic is needed for that installation.
- The next-boot write and reboot actions are mocked in automated tests. Listing candidates does not select a target.
- Removal watcher checks are event-driven; a short delay tolerates a plugin's atomic replacement during updates. A merely missing manifest in an existing directory does not trigger cleanup.

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
