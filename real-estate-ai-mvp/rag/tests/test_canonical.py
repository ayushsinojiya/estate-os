from rag_ingestion.canonical import reconcile, representations, resolve_entities, normalize_fact
import pytest


def contribution(source, order, facts, entity='p1', kind='PROPERTY', parent=None):
    return dict(entity_id=entity, kind=kind, parent_id=parent, source_id=source,
                version_id=source, publication_order=order, identity={'name': 'Example'},
                facts={k: {'value': v, 'evidence': {'quote': str(v), 'method': 'native'}} for k, v in facts.items()})


def test_newest_overrides_only_conflict_and_delete_restores_previous():
    a = contribution('a', 1, {'price_min': '85 lakh', 'balconies': 2})
    b = contribution('b', 2, {'price_min': '90 lakh'})
    result = reconcile([a, b])['p1']
    assert result['facts']['price_min'] == 9000000
    assert result['facts']['balconies'] == 2
    assert result['provenance']['price_min']['source_id'] == 'b'
    assert reconcile([a])['p1']['facts']['price_min'] == 8500000
    assert reconcile([]) == {}


def test_area_types_and_original_are_kept():
    out = normalize_fact('carpet_area', '100 sq m')
    assert out['original'] == '100 sq m'
    assert round(out['sqft'], 2) == 1076.39
    assert normalize_fact('amenities', ['fitness centre', 'sky bridge']) == ['gym', 'sky bridge']


def test_weak_identity_never_merges_distinct_listings():
    entries = [{'key': 'row1', 'kind': 'PROPERTY', 'identity': {'locality': 'Bopal'}, 'facts': {}}]
    a = resolve_entities(entries, 'sourceA', [])
    b = resolve_entities(entries, 'sourceB', a)
    assert a[0]['entity_id'] != b[0]['entity_id']


def test_same_explicit_project_id_resolves_across_batch_files():
    a = resolve_entities([{'key': 'a', 'kind': 'PROJECT', 'identity': {'project_id': 'P1'}, 'facts': {}}], 's1', [])
    b = resolve_entities([{'key': 'b', 'kind': 'PROJECT', 'identity': {'project_id': 'P1'}, 'facts': {}}], 's2', a)
    assert a[0]['entity_id'] == b[0]['entity_id']


def test_parent_context_does_not_become_direct_facts():
    entities = reconcile([contribution('a', 1, {'name': 'Sky', 'amenities': ['gym']}, 'project', 'PROJECT'),
                          contribution('b', 2, {'bhk': 3, 'configuration_name': 'A'}, 'child', 'CONFIGURATION', 'project')])
    assert 'amenities' not in entities['child']['facts']
    rows = representations(entities['child'], entities)
    assert 'Sky' in rows[0]['content']
    assert rows[0]['metadata']['parent_id'] == 'project'


def test_name_only_is_not_a_cross_source_project_match():
    entry = [{'key': 'p', 'kind': 'PROJECT', 'identity': {'name': 'Sky'}, 'facts': {}}]
    a = resolve_entities(entry, 's1', [])
    assert resolve_entities(entry, 's2', a)[0]['entity_id'] != a[0]['entity_id']


def test_explicit_price_range_updates_both_bounds_not_stale_filter():
    a = contribution('a', 1, {'price_min': '80 lakh', 'price_max': '82 lakh'})
    b = contribution('b', 2, {'price': '85-90 lakh'})
    result = reconcile([a, b])['p1']
    assert result['facts']['price_min'] == 8500000
    assert result['facts']['price_max'] == 9000000
    assert result['provenance']['price_min']['original_value'] == '85-90 lakh'


def test_ambiguous_new_numeric_fact_clears_stale_filter_but_retains_source():
    result = reconcile([contribution('a', 1, {'price_min': 8000000}), contribution('b', 2, {'price_min': 'on request'})])['p1']
    assert 'price_min' not in result['facts']
    assert result['unresolved_facts']['price_min']['value'] == 'on request'
    assert result['provenance']['price_min']['source_id'] == 'b'


@pytest.mark.parametrize('kind,identity', [
    ('PROJECT', {'project_name': 'Green Meadows', 'developer_name': 'ABC', 'locality': 'MG Road'}),
    ('PROPERTY', {'address': '10 MG Road', 'unit_number': '101', 'property_type': 'Office'}),
])
def test_location_based_identity_does_not_merge_different_cities(kind, identity):
    first = {'key': 'row1', 'kind': kind, 'identity': {**identity, 'city': 'Pune'}, 'facts': {}}
    second = {'key': 'row1', 'kind': kind, 'identity': {**identity, 'city': 'Bengaluru'}, 'facts': {}}
    original = resolve_entities([first], 'sourceA', [])
    added = resolve_entities([second], 'sourceB', original)
    assert original[0]['entity_id'] != added[0]['entity_id']
