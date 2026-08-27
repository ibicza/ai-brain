# CIAAW Atomic-Weight and Uncertainty Model

The selected 33-element extract retains both CIAAW 2024 representations:

- standard atomic weight as either `SINGLE` nominal plus uncertainty or an
  interval with lower and upper endpoints;
- abridged standard atomic weight as classroom value plus uncertainty;
- original source notation for both representations.

There are 21 single and 12 interval standard records. H, C, O, and Cl are
interval examples; Fe, Cu, and Ag are single-value examples.

`CONVENTIONAL_CLASSROOM` calculations use the CIAAW abridged value and expose
its uncertainty as provenance, not propagated measurement uncertainty.
`NATURAL_VARIABILITY_ENVELOPE` sums standard endpoints. It never silently uses
an interval midpoint. This envelope is not a complete uncertainty propagation.
