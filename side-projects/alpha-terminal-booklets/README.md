# Alpha Terminal Field Guides

This side project contains three visual, eight-page research booklets. Each
describes a different terminal architecture for seeking and evaluating alpha;
none promises future returns or provides live trade recommendations.

## Volumes

1. **Market Regime Terminal** — classify trend, participation, volatility,
   positioning and policy context before selecting a playbook.
2. **Catalyst and Earnings Terminal** — preserve expectations and release
   timestamps, measure surprise, and test price confirmation and post-event
   drift.
3. **Relative Strength Portfolio Terminal** — rank leadership on common
   horizons, inspect holdings overlap, and simulate marginal portfolio risk
   before allocating capital.

## Outputs

- Final PDFs: `output/pdf/`
- DOCX page containers: `output/docx/`
- Reproducible source: `build_booklets.py`
- Original generated cover art: `assets/`
- Rendered source pages: `page-renders/`

Run the builder with the workspace Python runtime after installing its declared
Pillow, ReportLab and python-docx dependencies. The builder regenerates all
three PDFs and DOCX containers from the same content definitions.

## Research boundary

The Market Regime volume follows the current PG-terminal boundary: 12 June
2000, the NSE launch date for NIFTY index futures, is the temporary floor for
comparable quantitative regime evidence. Earlier Indian-market history remains
documentary context until auditable series support a consistent classifier.
