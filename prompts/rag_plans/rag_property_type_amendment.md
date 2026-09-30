# RAG Property-Type Generalization Amendment

## Purpose
This amendment extends the approved `rag.md` V1 specification to explicitly support all real-estate property types. It does not replace the existing architecture. Apply it to the current implementation and change only what is necessary.

## Generic Property Model
The canonical property model must support all real-estate property types and must not assume every property is residential.

Examples include, but are not limited to:
- Apartment / Flat
- Villa / Bungalow
- Independent House
- Residential Plot
- Commercial Shop
- Showroom
- Office
- Commercial Space
- Warehouse / Godown
- Industrial Property
- Land / Plot
- Other future property types

Use one generic canonical property architecture rather than separate schemas/tables for each property category.

## Common Fields
Fields broadly applicable should remain standardized when available:
- property type
- property subtype
- identity/name
- project/configuration relationship
- location
- price
- applicable area types
- possession/availability/status
- parking
- other genuinely common fields

These are standardized when available, not automatically mandatory.

## Type-Specific Fields
Type-specific fields must only be populated when applicable and explicitly available in the source.

### Residential examples
- BHK
- bedrooms
- bathrooms
- balconies

### Commercial shop / showroom examples
- frontage
- shop width/depth
- floor
- shutter count
- washroom

### Office examples
- workstations
- cabins
- conference rooms
- pantry

### Warehouse / industrial examples
- clear height
- loading docks
- power capacity
- truck access

### Land / plot examples
- plot dimensions
- road width
- corner plot
- applicable land-specific attributes

These examples do not define mandatory fields and are not a complete allowed-field list.

Unknown, uncommon, or future property-type-specific attributes should use the existing dynamic JSONB mechanism rather than requiring a new schema/table for every property type.

Do not infer type-specific attributes that are not explicitly present in the source.

## Residential Fields Are Not Universal
The implementation must not require `bhk`, `bedrooms`, `bathrooms`, or `balconies` for every property. These fields are optional and should only be used where applicable.

## Search / RAG Read Model
All property types must continue to produce the same property-aware canonical search representations and use the existing denormalized RAG read model.

```text
Apartment ───────┐
Villa ───────────┤
Shop ────────────┤
Showroom ────────┤
Office ──────────┤
Warehouse ───────┼──→ Canonical Text
Industrial ──────┤        ↓
Land / Plot ─────┤   Search Read Model
Other ───────────┘        ↓
                     FTS + pgvector
```

The voice agent should not require a different retrieval architecture for apartments, shops, offices, warehouses, land, or other property types.

Type-specific attributes may be compiled into canonical searchable text when explicitly available.

## Existing Grounding Rules Still Apply
All existing `rag.md` accuracy and grounding rules remain unchanged:
- Extract explicit facts only.
- Do not invent missing property characteristics.
- Do not infer subjective characteristics.
- Preserve source provenance.
- Preserve original terminology where useful.
- Use deterministic normalization where appropriate.
- Keep uncertain facts out rather than guessing.

## Implementation Instruction for Codex
Implementation has already started. Do not restart or redesign already-correct generic components.

Inspect the current implementation and identify only places where residential assumptions have been hard-coded.

Adjust those areas so that:
1. the canonical model accepts non-residential properties;
2. residential-only fields are optional;
3. common property fields remain standardized;
4. uncommon/type-specific fields can use the existing dynamic JSONB mechanism;
5. all property types generate compatible canonical search representations;
6. all property types continue to use the same RAG read/retrieval model.

Do not introduce separate property tables/schemas for every property category solely because of this amendment.

All other requirements and architecture decisions from the approved `rag.md` remain unchanged.
