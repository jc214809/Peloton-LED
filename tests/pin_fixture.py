"""Compact pin fixtures: each distinct value is stored once, in a table keyed by a short hash of its canonical
JSON, and each case lists ids. One case and one value per line, so a diff shows which ones changed.

Used by test_rotation_pages_pin.py and test_settings_form_pin.py. Cases map a name to a JSON structure in which
every table value was replaced by its id (see Table.intern) and is put back by Table.resolve.
"""
import hashlib
import json

ID_LENGTH = 8  # hex characters of a value id; Table(id_length=...) for a smaller fixture


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


class Table:
    """The values of a fixture, by id."""

    def __init__(self, values=None, id_length=ID_LENGTH):
        self.values = dict(values or {})
        self.id_length = len(next(iter(self.values))) if self.values else id_length

    def intern(self, value):
        """The id of a JSON-able value, storing it when it is new."""
        text = canonical(value)
        key = hashlib.sha256(text.encode()).hexdigest()[:self.id_length]
        known = self.values.setdefault(key, json.loads(text))
        assert canonical(known) == text, f'hash collision on {key}'
        return key

    def resolve(self, key):
        return self.values[key]


def write(path, table, cases):
    """Write the cases (name: JSON) and the table, one per line."""
    lines = ['{"cases":{']
    lines += [f'{json.dumps(name)}:{canonical(case)}{"," if i < len(cases) - 1 else ""}'
              for i, (name, case) in enumerate(sorted(cases.items()))]
    lines += ['},"values":{']
    items = sorted(table.values.items())
    lines += [f'"{key}":{canonical(value)}{"," if i < len(items) - 1 else ""}' for i, (key, value) in enumerate(items)]
    lines.append('}}')
    path.write_text('\n'.join(lines) + '\n')


def read(path):
    """(Table, cases) from a fixture file."""
    data = json.loads(path.read_text())
    return Table(data['values']), data['cases']


def show(value, limit=700):
    """A value as readable, shortened JSON for an assertion message."""
    text = json.dumps(value, sort_keys=True, default=repr)
    return text if len(text) <= limit else text[:limit] + f'... ({len(text)} chars)'
