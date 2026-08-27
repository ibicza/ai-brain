# M-28 Chemistry Source Research

Retrieved 2026-08-27. The runtime performs no network access; production uses the frozen structured extracts in `artifacts/domains/chemistry/m28/sources`.

## Primary Sources

- International Union of Pure and Applied Chemistry, *Periodic Table of Elements*, release 4 May 2022: https://iupac.org/what-we-do/periodic-table-of-elements/. Supports atomic number, exact symbol, English name, period, and group for the selected identity set. The committed extract contains 33 selected elements, not the whole table.
- IUPAC Commission on Isotopic Abundances and Atomic Weights, *Standard Atomic Weights 2024*: https://ciaaw.org/atomic-weights.htm. Supports single values and intervals.
- CIAAW, *Abridged Standard Atomic Weights 2024*: https://www.ciaaw.org/abridged-atomic-weights.htm. Supports the explicit classroom conventional-value policy. Conventional values are not exact constants.
- Bureau International des Poids et Mesures, *The International System of Units (SI)*, 9th edition, version 3.02, updated 2026, DOI `10.59161/AUEZ1291`: https://www.bipm.org/documents/20126/41483022/SI-Brochure-9.pdf. Supports the mole and exact Avogadro constant `6.02214076e23 mol^-1`; BIPM labels the brochure CC BY 4.0.

## Classification

- Source fact: symbols, atomic numbers, English names, period/group, CIAAW weight data, exact Avogadro constant.
- Policy choice: the 33-element computational subset and conventional classroom mode as default.
- Reviewed translation policy: Russian school names in `ru_element_names_policy_v1.json`; these are not represented as IUPAC facts.
- Derived value: formula composition and calculation outputs.
- Educational rounding: rendering only. Internal arithmetic remains Decimal and unrounded.

Every source extract records authority, title, version/date, locator, publication and retrieval dates, language, license metadata, source family, limitations, byte SHA-256, and semantic hash in the domain manifest.
