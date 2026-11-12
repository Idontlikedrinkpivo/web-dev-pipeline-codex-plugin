# Dates and time across the contract

Read when the scoped requirements, API, storage or screen include a date/time field or a calendar rule.
Apply to affected fields, not an unrelated whole-product rewrite. SRS owns the meaning; downstream stages
carry it forward. An unclear meaning is an upstream question, not permission to select the user's time zone.

## Requirements

For each distinct date/time meaning, state its kind, the source of any time zone, input/display policy and
calendar boundaries. Fields sharing one meaning cite it rather than repeating it in every table.

| Kind | Decision required |
|---|---|
| Instant, e.g. payment received | One point in time; specify the display zone (user, organisation or named location), not an automatic user-zone default |
| Calendar date, e.g. birthday | A day without a time or zone; it must remain the same date for users in different zones |
| Local scheduled time, e.g. an office booking | Local date/time and the location's IANA zone; define what happens when a local time is missing or occurs twice during a clock change |

Use an IANA identifier such as `Europe/Moscow` when geographic clock rules matter; an offset alone does not
describe those rules. A fixed-offset requirement remains valid when the product explicitly means that.
For future/recurring schedules, state whether local wall time or the resolved instant is authoritative and
what happens if zone rules change. Do not invent recurrence for a one-off event.
Define whose «today»/«end of day» applies and whether boundaries are inclusive. The same policy must drive
validation, queries and displayed values. Only ask about clock-change cases relevant to the product.

## Downstream ownership

- **DB:** preserve `db-schema-design`'s `date` for calendar days and `timestamptz` for instants. Persist the
  IANA zone (on the location or schedule) and local scheduling intent when required; `timestamptz` alone
  does not preserve a location's zone name. Do not force a UTC timestamp onto a birthday.
- **OpenAPI:** calendar date is a string with `format: date`; an instant uses `format: date-time` with an
  explicit offset or `Z`, and the documented normalization policy. Local scheduled time is explicitly
  modelled with its zone; never mislabel an offset-free local value as an instant. Describe the source of
  the zone and examples, and carry the SRS's ambiguity/error decisions. Contract changes follow versioning.
- **Architecture:** keep calendar computations in the existing domain value object and Clock design
  (`clean-architecture-design/references/rich-entities.md`), including zone ownership; no duplicate client rule.
- **Screen spec:** for affected input/output/derived values, cite the API field and specify the input/display
  zone or «calendar date — no zone». Missing policy returns to its owner; the screen does not invent it.
- **Implementation:** keep date-only values as dates through the wire and UI. Do not manufacture an instant
  with `new Date(dateOnly)` or `${dateOnly}T00:00:00Z` and then format it in a local zone. Instant formatting
  uses `Intl.DateTimeFormat` with the chosen zone. Use the project's supported date facilities; this rule
  requires neither a new library nor Temporal. The backend remains authoritative for business boundaries.
- **Consistency/review:** compare meaning as well as type across SRS → DB → API → domain → screen.
  A matching `string` type does not prove agreement on the zone or date-only semantics.

## Verification

For affected behaviour, assert concrete expected values: a date-only value stays unchanged in zones on
opposite sides of UTC; an instant renders in the declared zone; a booking uses its location's time even
when the user's zone differs. Test midnight/calendar boundaries and missing/repeated local times where
the requirements make them possible. A server/client render must agree on the chosen zone and value.
Use the same cases in component/domain/API tests as appropriate; do not duplicate every case at every layer.
