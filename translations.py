"""Plugin catalogs using Omarchy's selected language and English fallback."""
import json
import os
from pathlib import Path
import re

CATALOGS = Path(__file__).resolve().parent / 'i18n'

def selected_language():
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    path = Path(os.environ.get('OMARCHY_LANGUAGE_FILE', config / 'omarchy/language'))
    try:
        code = path.read_text().strip()
    except OSError:
        return 'en'
    return code if re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z]{2})?', code) else 'en'

def catalog(code, directory=CATALOGS):
    if not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z]{2})?', code):
        return {}
    try:
        data = json.loads((directory / (code + '.json')).read_text())
        return {k: v for k, v in data.items() if isinstance(v, str) and v} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}

def translate(key, *args, language=None, directory=CATALOGS):
    code = language if language is not None else selected_language()
    strings = {}
    for layer in ['en', code.split('-')[0], code]:
        strings.update(catalog(layer, directory))
    text = strings.get(key, key)
    # One pass preserves volume names that themselves contain %1 or %2.
    return re.sub(r'%([1-9][0-9]*)', lambda m: str(args[int(m[1])-1]) if int(m[1]) <= len(args) else m[0], text)
