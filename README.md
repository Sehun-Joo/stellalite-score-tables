# Stellalite scoring practice tables

Stella + Satellite, independently ranked for AAA (8/9), MAX− (17/18), and 98%.

https://sehun-joo.github.io/stellalite-score-tables/

Difficulty ranges are set using the entire eligible pool first. Each range then contains up to 20 charts by archived LR2IR total plays, displayed in descending popularity order. Sparse ranges stay smaller. See score-targets.html for coverage, exclusions, exact boundaries, model validation and limitations.

Distinct import URLs: root for 98%, aaa/ for AAA, max-minus/ for MAX−. No song files or player-level records are included. Original chart identifiers and links are retained; no blanket license is claimed over third-party metadata.

Reproduction scripts expect the original workspace layout and the local lr2ir-archive-v3.db. Python model dependencies: NumPy and SciPy. Snapshot manifests are included. Run fit_stellalite.py, then build_stellalite_site.py; its HTML template is from the original bms-98-table repository.
