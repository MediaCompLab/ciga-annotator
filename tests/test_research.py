from copy import deepcopy
import pytest
from src.core.research import (CodingHistory, compare_projects, material_identity,
                               missing_roles, review_state, study_settings, is_uncoded, review_feedback)


def test_legacy_filled_roles_are_not_human_confirmation():
    assert review_state({role: ['Alice'] for role in ('speakers', 'listeners', 'targets')}) == 'in_progress'
    assert review_state({}) == 'pending'


def test_configurable_required_roles_allow_explicit_na():
    study = study_settings({'required_roles': ['speakers', 'listeners']})
    assert missing_roles({'speakers': ['A'], 'not_applicable': ['listeners']}, study) == []
    assert missing_roles({'speakers': ['A']}, study) == ['listeners']


def test_history_coalesces_notes_without_losing_first_state():
    history = CodingHistory()
    history.push(0, {}, {'note': 'a'}, 'Edit note', True)
    history.push(0, {'note': 'a'}, {'note': 'ab'}, 'Edit note', True)
    assert history.undo() == (0, {}, 'Edit note')
    assert history.redo() == (0, {'note': 'ab'}, 'Edit note')
    history.undo()
    history.push(1, {}, {'note': 'new'}, 'Edit note', True)
    assert history.redo() is None


def project():
    return {'study': study_settings({'codebook_version': 'v1'}),
            'material': material_identity([{'start_time': 0, 'end_time': 1000, 'text': 'Hello'}]),
            'characters': [{'id': 'alice', 'name': 'Alice'}],
            'annotations': {'0': {'speakers': ['Alice']}}}


def test_compare_uses_stable_identity_after_rename():
    left, right = project(), project()
    right['characters'][0]['name'] = 'Alicia'
    right['annotations']['0']['speakers'] = ['Alicia']
    assert compare_projects(left, right) == []
    right['annotations']['0']['not_applicable'] = ['listeners']
    assert compare_projects(left, right)[0][0] == 0


@pytest.mark.parametrize('surface', ['material', 'codebook', 'definition', 'required'])
def test_compare_rejects_incompatible_projects(surface):
    left, right = project(), project()
    if surface == 'material':
        right['material']['subtitle_sha256'] = 'different'
    elif surface == 'codebook':
        right['study']['codebook_version'] = 'v2'
    elif surface == 'definition':
        right['study']['definitions']['listeners'] = 'different definition'
    else:
        right['study']['required_roles'] = ['speakers']
    with pytest.raises(ValueError):
        compare_projects(left, right)


def test_compare_includes_custom_coding_dimensions():
    left, right = project(), project()
    left['custom_columns'] = right['custom_columns'] = ['Note', 'Emotion']
    left['annotations']['0']['Emotion'] = 'Positive'
    right['annotations']['0']['Emotion'] = 'Negative'
    assert len(compare_projects(left, right)) == 1


@pytest.mark.parametrize('annotation', [
    {'speakers': ['A']}, {'not_applicable': ['listeners']}, {'note': 'check gaze'},
    {'Emotion': 'positive'}, {'review_state': 'confirmed'}, {'review_state': 'excluded'},
    {'review_state': 'needs_review', 'speakers': ['A']},
])
def test_coding_navigation_does_not_require_manual_approval(annotation):
    assert not is_uncoded(annotation, ['Note', 'Emotion'])


def test_cleared_coding_is_uncoded_even_if_previously_started():
    assert is_uncoded({'review_state': 'in_progress', 'speakers': [], 'Note': ''})


def test_missing_roles_are_passive_feedback_and_do_not_change_review_state():
    annotation = {'speakers': ['A'], 'review_state': 'in_progress'}
    label, details, feedback = review_feedback(annotation, study_settings())
    assert label == 'Needs check'
    assert 'Listener' in details and 'Target' in details
    assert feedback == 'needs_review'
    assert annotation['review_state'] == 'in_progress'
