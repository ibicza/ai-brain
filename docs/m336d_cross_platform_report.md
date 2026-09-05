# M-33.6d cross-platform report

Windows and Karina received byte-identical vault contents: 4,469 files, portable byte-sorted tree hash `e8d6eae2b740643d4a77277e9b165d2bdfe308ea80cad30fad87eea244102150`, physical difference count zero.

The frozen verifier reports FAIL on both sides because Windows manifest construction and portable verification use different ordering rules. Production, evaluator, pack, replay, and runtime comparisons are `NOT RUN` after selector failure. Therefore a final semantic difference count cannot be claimed.
