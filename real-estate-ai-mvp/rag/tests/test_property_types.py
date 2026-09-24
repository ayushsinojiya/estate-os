import pytest
from rag_ingestion.parsing import extract_facts
from rag_ingestion.canonical import resolve_entities, reconcile, representations


@pytest.mark.parametrize('property_type,extra,value', [
    ('Apartment', 'bedrooms', '2'), ('Villa', 'balconies', '1'),
    ('Commercial Shop', 'frontage', '18 ft'), ('Showroom', 'shutter_count', '3'),
    ('Office', 'workstations', '40'), ('Warehouse', 'clear_height', '32 ft'),
    ('Industrial Property', 'power_capacity', '120 kVA'), ('Land / Plot', 'road_width', '40 ft'),
    ('Future mixed-use asset', 'special_access', 'freight-only'),
])
def test_all_types_use_same_canonical_model_without_required_residential_fields(property_type, extra, value):
    raw = {'structured': True, 'blocks': [{'text': '', 'locator': {'sheet': 'Properties'}, 'rows': [
        {'values': {'property id': 'P1', 'property type': property_type, 'property subtype': 'Source subtype',
                    'availability': 'Available', 'city': 'Pune', extra: value}, 'locator': {'row': 2}}
    ]}]}
    parsed = extract_facts(raw)['entities']
    resolved = resolve_entities(parsed, 'source1', [])
    contributions = [dict(row, version_id='v1', filename='types.csv', publication_order=1) for row in resolved]
    entities = reconcile(contributions)
    entity = next(iter(entities.values()))
    assert entity['kind'] == 'PROPERTY'
    assert entity['facts']['property_type'] == property_type
    assert entity['facts']['property_subtype'] == 'Source subtype'
    assert entity['facts']['availability_status'] == 'Available'
    assert 'bhk' not in entity['facts']
    assert extra in entity['facts']
    sections = representations(entity, entities)
    assert any(extra.replace('_', ' ') in section['content'] for section in sections)
    assert all(section['filters']['property_type'] == property_type for section in sections)
    assert all(section['filters']['property_subtype'] == 'Source subtype' for section in sections)
    assert all(section['filters']['bhk'] is None for section in sections)


def test_explicit_project_configuration_property_hierarchy_is_preserved():
    raw = {'structured': True, 'blocks': [{'text': '', 'locator': {}, 'rows': [
        {'values': {'property_id': 'SHOP1', 'project_id': 'PROJECT1', 'project_name': 'Synthetic Plaza',
                    'configuration_name': 'Retail A', 'property_type': 'Shop', 'carpet_area': '400 sqft'}, 'locator': {'row': 2}}
    ]}]}
    entities = extract_facts(raw)['entities']
    by_kind = {row['kind']: row for row in entities}
    assert set(by_kind) == {'PROJECT', 'CONFIGURATION', 'PROPERTY'}
    assert by_kind['PROPERTY']['parent_key'] == by_kind['CONFIGURATION']['key']
    assert by_kind['CONFIGURATION']['parent_key'] == by_kind['PROJECT']['key']


def test_configuration_name_with_different_explicit_areas_does_not_collapse_variants():
    rows = [{'key': str(n), 'kind': 'CONFIGURATION', 'parent_key': 'p', 'identity': {'configuration_name': 'Retail A', 'carpet_area': area}, 'facts': {}} for n, area in enumerate(['400 sqft', '600 sqft'])]
    project = {'key': 'p', 'kind': 'PROJECT', 'identity': {'project_id': 'P1'}, 'facts': {}}
    resolved = resolve_entities([project, *rows], 'source1', [])
    assert resolved[1]['entity_id'] != resolved[2]['entity_id']
