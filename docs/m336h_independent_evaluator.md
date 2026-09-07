# M-33.6h independent evaluator

The M336H evaluator is count-neutral and runs only after valid Windows and Karina production seals and their sealed replay receipts are available. Its request uses public-safe production results, independent reference material, thresholds, both platform seals, and a non-authoritative evaluator ledger.

The evaluator neither imports nor calls production, selector, materializer, source acquisition, or disclosed golden constants. It verifies seal agreement, replay and pack integrity, threshold-derived semantic results when present, platform-neutral differences, isolation, and publication-boundary counters. A failed precondition leaves evaluator one-shot counters at zero.
