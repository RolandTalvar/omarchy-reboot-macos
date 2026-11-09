# Reboot into macOS for Omarchy

Adds **Reboot into macOS** between **Reboot** and **Shutdown** in the System menu (Super+Escape). No bar icon.

![System menu showing Reboot into macOS between Reboot and Shutdown](preview.png)

The action detects a single boot volume named `macOS …`, `Macintosh …`, or `Mac OS …`, shows its name in a confirmation, and selects it for the **next boot only**. Linux remains the default. If no label matches, or more than one matches, a picker lets you identify the macOS volume. Names are labels, not proof of which OS a volume contains: custom names require your choice.

## Requirements

- Apple Silicon Mac running Omarchy Quattro, with a macOS installation.
- `asahi-bless` (including the compatible `aurora-bless` provider).
- Python 3, sudo, polkit (`pkexec`), and gum.

## Install

Install this repository with `omarchy plugin add https://github.com/RolandTalvar/omarchy-reboot-macos.git --enable`, or copy the plugin folder into `~/.config/omarchy/plugins/rolandtlvr.reboot-macos/` and run:

```sh
omarchy plugin enable rolandtlvr.reboot-macos
python3 ~/.config/omarchy/plugins/rolandtlvr.reboot-macos/setup.py install
```

Run setup after either installation method. Setup requests administrator authentication **once**. Normal use requires only the reboot confirmation.

Omarchy has no plugin API for inserting System menu rows. Setup explicitly updates `~/.config/omarchy/extensions/omarchy-menu.jsonc`, backing it up first. It preserves unrelated entries, hides stock Shutdown, and appends a replacement Shutdown after the macOS action. This preserves the requested order. The macOS row is hidden while this plugin's service is disabled.

### Privileged helper

Setup installs a root-owned snapshot at `/usr/local/libexec/omarchy-reboot-macos-helper` and a user-specific rule in `/etc/sudoers.d/90-omarchy-reboot-macos-plugin`. The helper accepts only `--list` or `--select-next INDEX`. It validates indices against the live boot list, always uses `--next`, and never reboots or runs user-provided commands. Python runs in isolated mode. The UI confirms before selecting a boot target; Omarchy's normal reboot command then closes applications and reboots.

The rule permits selecting any listed boot volume for one boot; it grants no general root shell or permanent default-boot change. Only one user is supported by this installation. Updates to the helper require rerunning setup, so a plugin update alone cannot change privileged code.

If migrating from the earlier local `restart-macos` menu customization, setup replaces that action and retires its exact macOS Sequoia sudo rule. It does not execute a reboot during setup.

## Remove

Remove the menu entry and privilege rule **before** deleting the plugin:

```sh
python3 ~/.config/omarchy/plugins/rolandtlvr.reboot-macos/setup.py remove
omarchy plugin remove rolandtlvr.reboot-macos
```

Removal restores stock Shutdown. Menu backups remain available. If the plugin folder was deleted first, reinstall it and run the removal command to clean up the helper and menu rows.

## Development

```sh
omarchy plugin validate .
python3 -m unittest discover -s tests -v
bash -n setup-root
```

Tests mock boot-selection and reboot commands. To inspect actual candidates without selecting one:

```sh
sudo -n /usr/local/libexec/omarchy-reboot-macos-helper --list
```

## License

MIT; see LICENSE.
