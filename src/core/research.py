"""Project-local research rules, identities and reversible coding edits.

Human confirmation is never inferred from legacy role selections. Names remain
in the CIGA CSV contract; immutable IDs and review metadata live in the project.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

ROLES = ('speakers', 'listeners', 'targets')
ROLE_LABELS = dict(zip(ROLES, ('Speaker', 'Listener', 'Target')))
STATES = {'pending': 'Pending', 'in_progress': 'In progress',
          'confirmed': 'Confirmed', 'needs_review': 'Needs review', 'excluded': 'Excluded'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def study_settings(value=None):
    value = value or {}
    return {
        'coder_id': str(value.get('coder_id', '')),
        'codebook_version': str(value.get('codebook_version', '')),
        'required_roles': [role for role in ROLES if role in value.get('required_roles', ROLES)],
        'definitions': {role: str(value.get('definitions', {}).get(role, '')) for role in ROLES},
    }


def material_identity(subtitles):
    """Content hash of parsed cues, independent of path/encoding/line endings."""
    cues = [[cue['start_time'], cue['end_time'], cue['text']] for cue in subtitles]
    digest = hashlib.sha256(json.dumps(cues, ensure_ascii=False).encode('utf-8')).hexdigest()
    units = [hashlib.sha256(f'{digest}:{index}'.encode()).hexdigest() for index in range(len(cues))]
    return {'subtitle_sha256': digest, 'unit_ids': units}


def ensure_character_ids(characters):
    names = set()
    identities = set()
    for character in characters:
        name = character.get('name', '')
        if not isinstance(name, str) or not name.strip() or ',' in name or name.casefold() in names:
            raise ValueError('Character names must be nonempty, unique and contain no commas.')
        names.add(name.casefold())
        if not character.get('id'):
            character['id'] = str(uuid4())
        if character['id'] in identities:
            raise ValueError('Two characters share the same identity. Restore an intact project copy.')
        identities.add(character['id'])
        character.setdefault('aliases', [])
        if character.get('key'):
            character['key'] = str(character['key']).upper()


def missing_roles(annotation, study):
    na = annotation.get('not_applicable', [])
    return [role for role in study['required_roles']
            if not annotation.get(role) and role not in na]


def review_state(annotation):
    state = annotation.get('review_state')
    if state in STATES:
        return state
    if any(annotation.get(role) for role in ROLES) or annotation.get('note') or annotation.get('Note'):
        return 'in_progress'
    return 'pending'


def normalize_annotation(annotation, characters):
    result = deepcopy(annotation)
    result['review_state'] = review_state(result)
    result['not_applicable'] = [role for role in result.get('not_applicable', []) if role in ROLES]
    identities = {character['name']: character['id'] for character in characters}
    for role in ROLES:
        result[role] = list(result.get(role, []))
        result[f'{role}_ids'] = [identities[name] for name in result[role] if name in identities]
    result['note'] = result.get('note', result.get('Note', ''))
    result.setdefault('Note', result['note'])
    return result


class CodingHistory:
    """Bounded patches, with consecutive note typing coalesced per unit."""
    def __init__(self, limit=200):
        self.undo_entries = []
        self.redo_entries = []
        self.limit = limit
        self.coalesce_allowed = False

    def break_group(self):
        self.coalesce_allowed = False

    def push(self, index, before, after, action, coalesce=False):
        entry = (index, deepcopy(before), deepcopy(after), action)
        if coalesce and self.coalesce_allowed and self.undo_entries and not self.redo_entries:
            last = self.undo_entries[-1]
            if last[0] == index and last[3] == action:
                self.undo_entries[-1] = (index, last[1], entry[2], action)
                return
        self.undo_entries.append(entry)
        self.undo_entries = self.undo_entries[-self.limit:]
        self.redo_entries.clear()
        self.coalesce_allowed = coalesce

    def undo(self):
        self.break_group()
        if not self.undo_entries:
            return None
        entry = self.undo_entries.pop()
        self.redo_entries.append(entry)
        return entry[0], deepcopy(entry[1]), entry[3]

    def redo(self):
        self.break_group()
        if not self.redo_entries:
            return None
        entry = self.redo_entries.pop()
        self.undo_entries.append(entry)
        return entry[0], deepcopy(entry[2]), entry[3]


def compare_projects(current, other):
    """Compare independent coding only when material and rules match exactly.

    Character IDs survive project copies. Independently created projects may
    have different IDs, so matching uses unique names, without fuzzy guesses.
    """
    if current.get('material', {}).get('subtitle_sha256') != other.get('material', {}).get('subtitle_sha256'):
        raise ValueError('Subtitle material differs. Compare projects created from the same subtitles.')
    if not current.get('material', {}).get('subtitle_sha256'):
        raise ValueError('Save both projects with this version before comparing them.')
    if current['material'].get('unit_ids') != other['material'].get('unit_ids'):
        raise ValueError('Coding units differ.')
    left_video = current['material'].get('video_sha256')
    right_video = other['material'].get('video_sha256')
    if left_video and right_video and left_video != right_video:
        raise ValueError('Video content differs. Compare coding from the same video material.')
    for key in ('codebook_version', 'required_roles', 'definitions'):
        if study_settings(current.get('study'))[key] != study_settings(other.get('study'))[key]:
            raise ValueError('Codebook or completion rules differ. Align project settings first.')
    columns = sorted(set(current.get('custom_columns', ['Note'])))
    if columns != sorted(set(other.get('custom_columns', ['Note']))):
        raise ValueError('Custom coding fields differ. Align the project columns first.')
    current_chars = current.get('characters', [])
    other_chars = other.get('characters', [])
    by_id = {character['id']: character['name'] for character in current_chars}
    names = {character['name'] for character in current_chars}
    mapping = {}
    for character in other_chars:
        name = by_id.get(character.get('id'), character['name'])
        if name not in names:
            raise ValueError(f"Character '{character['name']}' has no matching identity. Align character names first.")
        mapping[character['name']] = name
    differences = []
    for index in range(len(current['material']['unit_ids'])):
        left = deepcopy(current.get('annotations', {}).get(str(index), current.get('annotations', {}).get(index, {})))
        right = deepcopy(other.get('annotations', {}).get(str(index), other.get('annotations', {}).get(index, {})))
        for role in ROLES:
            right[role] = [mapping.get(name, name) for name in right.get(role, [])]
        def signature(annotation):
            return ([sorted(annotation.get(role, [])) for role in ROLES],
                    sorted(annotation.get('not_applicable', [])), review_state(annotation),
                    annotation.get('note', annotation.get('Note', '')), annotation.get('exclusion_reason', ''),
                    [annotation.get(field, '') for field in columns if field != 'Note'])
        if signature(left) != signature(right):
            differences.append((index, left, right))
    return differences
