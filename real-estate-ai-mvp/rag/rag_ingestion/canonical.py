"""Pure reconciliation: keep contributions, select field winners, render grounded sections."""
from __future__ import annotations

import copy
import json
import math
import re
import unicodedata
import uuid
from decimal import Decimal, InvalidOperation


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value)).casefold().split())


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value if math.isfinite(value) and value >= 0 else None
    text = normalized(value).replace(',', '').replace('₹', '').strip()
    m = re.fullmatch(r'(?:inr\s*)?(\d+(?:\.\d+)?)\s*(cr|crore|crores|l|lac|lacs|lakh|lakhs|k)?', text)
    if not m:
        return None
    factor = {'cr': 10000000, 'crore': 10000000, 'crores': 10000000,
              'l': 100000, 'lac': 100000, 'lacs': 100000, 'lakh': 100000, 'lakhs': 100000, 'k': 1000}
    try:
        result = float(Decimal(m[1]) * factor.get(m[2], 1))
        return result if math.isfinite(result) else None
    except InvalidOperation:
        return None


AREA_FIELDS = {'carpet_area', 'built_up_area', 'super_built_up_area', 'plot_area'}
NUMERIC_FIELDS = {'bhk', 'bedrooms', 'bathrooms', 'balconies', 'price_min', 'price_max', 'floor', 'total_floors'}
ALIASES = {'price': 'price_min', 'project': 'project_name', 'configuration': 'configuration_name',
           'availability': 'availability_status', 'subtype': 'property_subtype',
           'super_builtup_area': 'super_built_up_area', 'builtup_area': 'built_up_area',
           'rera': 'rera_id', 'developer': 'developer_name'}


def normalize_fact(field, value):
    if field in NUMERIC_FIELDS:
        parsed = number(value)
        if parsed is not None:
            return parsed
        # Retain the source value in provenance; an ambiguous number cannot be a filter.
        return None
    if field in AREA_FIELDS:
        if isinstance(value, dict):
            original = copy.deepcopy(value)
            raw = f"{value.get('value', '')} {value.get('unit', '')}"
        else:
            original, raw = value, str(value)
        m = re.fullmatch(r'\s*([\d,.]+)\s*(sq\.?\s*ft|sqft|ft2|sq\.?\s*m|sqm|m2|sq\.?\s*yd|sqyd|yd2)\s*', normalized(raw))
        if m:
            unit = m[2].replace('.', '').replace(' ', '')
            factor = 10.76391041671 if unit in ('sqm', 'm2') else 9 if unit in ('sqyd', 'yd2') else 1
            return {'original': original, 'value': float(m[1].replace(',', '')), 'unit': m[2],
                    'sqft': round(float(m[1].replace(',', '')) * factor, 6)}
        return {'original': original}
    if field == 'amenities':
        items = value if isinstance(value, list) else re.split(r'[,;|]', str(value))
        equivalents = {'fitness centre': 'gym', 'fitness center': 'gym', 'gymnasium': 'gym', 'swimming pool': 'swimming pool'}
        return list(dict.fromkeys(equivalents.get(normalized(x), str(x).strip()) for x in items if str(x).strip()))
    return copy.deepcopy(value)


def identity_signature(kind, identity, parent_id=None):
    """Strong exact identities only. No BHK/area-only matches or fuzzy merges."""
    i = {k: normalized(v) for k, v in identity.items() if v is not None and str(v).strip()}
    keys = ('rera_id', 'project_id', 'project_code') if kind == 'PROJECT' else ('property_id', 'listing_id') if kind == 'PROPERTY' else ('configuration_id',)
    for key in keys:
        if key in i:
            return (kind, parent_id if kind == 'CONFIGURATION' else None, key, i[key])
    geography = tuple(i.get(key, '') for key in ('country', 'state', 'city'))
    if kind == 'PROJECT':
        name = i.get('name') or i.get('project_name')
        if name and i.get('developer_name') and (i.get('locality') or i.get('address')):
            return (kind, name, i['developer_name'], i.get('address') or i['locality'], geography)
    if kind == 'CONFIGURATION' and parent_id and i.get('configuration_name'):
        differentiators = tuple((key, i[key]) for key in sorted({'configuration_type', 'variant_name', 'bhk'} | AREA_FIELDS) if key in i)
        return (kind, parent_id, i['configuration_name'], differentiators)
    if kind == 'PROPERTY' and i.get('address') and i.get('unit_number'):
        return (kind, i['address'], i['unit_number'], i.get('property_type', ''), geography)
    return None


def resolve_entities(entries, source_id, existing):
    known = {}
    for row in existing:
        signature = identity_signature(row['kind'], row['identity'], row.get('parent_id'))
        if signature:
            known.setdefault(signature, set()).add(str(row['entity_id']))
    result, local, pending = [], {}, list(entries)
    while pending:
        progressed = False
        for entry in list(pending):
            parent_key = entry.get('parent_key')
            if parent_key and parent_key not in local:
                continue
            parent_id = local.get(parent_key)
            identity = dict(entry.get('identity', {}))
            signature = identity_signature(entry['kind'], identity, parent_id)
            candidates = known.get(signature, set()) if signature else set()
            # Two conflicting known identities are never automatically collapsed.
            # Extraction keys are local to each file, not stable property IDs.
            # Include explicit identity so a replacement's reused AI key cannot
            # acquire surviving contributions from a different property.
            fallback = json.dumps([str(source_id), entry['kind'], entry['key'], parent_id,
                                   {k: normalized(v) for k, v in identity.items()}], sort_keys=True, ensure_ascii=False)
            entity_id = next(iter(candidates)) if len(candidates) == 1 else str(uuid.uuid5(uuid.NAMESPACE_URL, 'estraos:identity-v2:' + fallback))
            local[entry['key']] = entity_id
            row = dict(entry, entity_id=entity_id, parent_id=parent_id, source_id=str(source_id))
            result.append(row)
            if signature:
                known.setdefault(signature, set()).add(entity_id)
            pending.remove(entry)
            progressed = True
        if not progressed:
            raise ValueError('Unresolved or cyclic parent relationship; no knowledge was published')
    return result


def reconcile(contributions):
    entities = {}
    for row in sorted(contributions, key=lambda r: (r['publication_order'], str(r['version_id']))):
        eid = str(row['entity_id'])
        entity = entities.setdefault(eid, {'id': eid, 'kind': row['kind'], 'parent_id': row.get('parent_id'),
                                          'identity': {}, 'facts': {}, 'provenance': {}, 'unresolved_facts': {}})
        entity['identity'].update(row.get('identity', {}))
        # Parent may disappear after source deletion; only direct contributions survive.
        entity['parent_id'] = row.get('parent_id') or entity['parent_id']
        expanded = dict(row['facts'])
        for raw_field in ('price', 'price_min'):
            fact = expanded.get(raw_field, {})
            match = re.fullmatch(r'\s*(\d[\d,.]*)\s*[-–]\s*(\d[\d,.]*)\s*(lakh|lakhs|lac|crore|cr|k)?\s*', normalized(fact.get('value', '')))
            if match:
                low, high = number(match[1] + (match[3] or '')), number(match[2] + (match[3] or ''))
                if low is not None and high is not None and low <= high:
                    expanded.pop(raw_field)
                    for field, value in [('price_min', low), ('price_max', high)]:
                        expanded[field] = {**fact, 'value': value, 'original_value': fact['value']}
        for raw_field, fact in expanded.items():
            field = ALIASES.get(raw_field, raw_field)
            if not isinstance(fact, dict) or fact.get('value') is None:
                continue
            value = normalize_fact(field, fact['value'])
            entity['provenance'][field] = {**fact.get('evidence', {}), 'source_id': str(row['source_id']),
                'version_id': str(row['version_id']), 'original_value': fact.get('original_value', fact['value']),
                'filename': row.get('filename'), 'publication_order': row['publication_order']}
            if value is None:
                entity['facts'].pop(field, None)
                entity['unresolved_facts'][field] = {'value': fact['value'], 'warning': 'Explicit value could not be normalized; excluded from numeric filters'}
            else:
                entity['facts'][field] = value
                entity['unresolved_facts'].pop(field, None)
    for entity in entities.values():
        if entity['parent_id'] not in entities:
            entity['parent_id'] = None
    return entities


SECTION_FIELDS = {
    'AMENITIES': {'amenities'},
    'LOCATION_CONNECTIVITY': {'country', 'state', 'city', 'locality', 'address', 'nearby_places', 'connectivity'},
    'SPECIFICATIONS': {'specifications', 'flooring', 'water_supply'},
    'PRICING_DETAILS': {'price_min', 'price_max', 'currency', 'payment_plan', 'price_basis', 'offers'},
}
CORE_FIELDS = {'name', 'project_name', 'configuration_name', 'configuration_type', 'property_type',
    'property_subtype', 'availability_status', 'status',
    'bhk', 'bedrooms', 'bathrooms', 'balconies', 'possession_status', 'possession_date', 'floor',
    'total_floors', 'facing', 'furnishing_status', 'parking', 'developer_name', 'rera_id',
    'project_id', 'project_code', 'property_id', 'listing_id', 'unit_number'} | AREA_FIELDS
FILTER_FIELDS = ('city', 'locality', 'property_type', 'property_subtype', 'availability_status', 'bhk', 'price_min', 'price_max', 'possession_status')


def readable(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def representations(entity, all_entities):
    facts = entity['facts']
    parent = all_entities.get(entity.get('parent_id'))
    context_entities = [entity]
    ancestor = parent
    while ancestor and ancestor not in context_entities:
        context_entities.append(ancestor)
        ancestor = all_entities.get(ancestor.get('parent_id'))
    title_parts = []
    for context in reversed(context_entities):
        f = context['facts']
        title = f.get('name') or f.get('project_name') or f.get('configuration_name') or context['identity'].get('name')
        if title:
            title_parts.append(str(title))
    if facts.get('bhk') is not None:
        title_parts.append(f"{facts['bhk']:g} BHK")
    title = ' | '.join(dict.fromkeys(title_parts)) or entity['kind']
    groups, used = {}, set()
    for section, fields in SECTION_FIELDS.items():
        group = {k: v for k, v in facts.items() if k in fields}
        if group:
            groups[section] = group
        used |= fields
    core = {k: v for k, v in facts.items() if k in CORE_FIELDS}
    if core:
        groups[f"{entity['kind']}_CORE"] = core
    other = {k: v for k, v in facts.items() if k not in used | CORE_FIELDS}
    if other:
        groups['OTHER_DYNAMIC'] = other
    if entity.get('unresolved_facts'):
        groups['SOURCE_QUALIFICATIONS'] = {k: v['value'] for k, v in entity['unresolved_facts'].items()}
    rows = []
    inherited = {}
    for key in FILTER_FIELDS:
        if key not in facts:
            for context in context_entities[1:]:
                if key in context['facts'] and key in ('city', 'locality'):
                    inherited[key] = {'value': context['facts'][key], 'entity_id': context['id'],
                                      'provenance': context['provenance'].get(key)}
                    break
    for section, fields in groups.items():
        rows.append({'entity_id': entity['id'], 'entity_type': entity['kind'], 'section_type': section,
            'content': title + '\n' + '\n'.join(f"{k.replace('_', ' ')}: {readable(v)}" for k, v in sorted(fields.items())),
            'filters': {k: facts.get(k, inherited.get(k, {}).get('value')) for k in FILTER_FIELDS},
            'metadata': {'parent_id': entity.get('parent_id'), 'identity': entity['identity'],
                         'inherited_filters': inherited, 'parent_context_ids': [c['id'] for c in context_entities[1:]],
                         'areas': {k: facts[k] for k in AREA_FIELDS if k in facts}},
            'provenance': {k: entity['provenance'][k] for k in fields},
            'priority': 100 if section.endswith('_CORE') else 50})
    return rows
