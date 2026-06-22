# Restore MinerU PDF Extraction Parity

## Goal

Port the original `src` MinerU-based PDF parsing behavior into `backend/app/parsers/pdf_parser.py` so web extraction can handle heterogeneous PDFs with the same production assumptions as the desktop pipeline.

## Problem

The original flow in `src/parsers/pdf_parser.py` uses MinerU to parse PDFs into markdown/HTML tables, supports local/public MinerU modes, encrypted PDFs, and non-table context extraction for document portrait. The web backend currently uses `pdfplumber` directly, which is simpler but weaker for complex/scanned/heterogeneous PDF statements.

## Scope

- Replace or augment `backend/app/parsers/pdf_parser.py` with MinerU local/public parsing behavior from `src/parsers/pdf_parser.py`.
- Preserve encrypted PDF handling and filename password extraction behavior where applicable.
- Return `RawTable` objects with HTML/table rows compatible with current backend extractor.
- Implement `extract_non_table_context()` by removing table blocks from MinerU markdown and truncating according to runtime settings.
- Wire runtime MinerU settings into `FlowExtractor`/`PDFParser` construction.
- Keep `pdfplumber` only as an explicit fallback if the team chooses that fallback and documents it.

## Reference Files

- `src/parsers/pdf_parser.py`
- `src/parsers/html_parser.py`
- `backend/app/parsers/pdf_parser.py`
- `backend/app/parsers/base.py`
- `backend/app/services/extraction/extractor.py`
- `.trellis/tasks/06-16-architecture-settings-review/review.md`

## Acceptance Criteria

- PDF parser supports local MinerU endpoint and public MinerU agent mode, matching the original mode concepts.
- Parser extracts raw tables and non-table context from the same parsed markdown content without making redundant API calls when avoidable.
- Encrypted PDF behavior is either ported or explicitly documented as unsupported with a clear user-facing error.
- Existing backend extraction tests still pass.
- Add parser tests for client selection, markdown-to-table extraction, non-table context stripping, and failure fallback.
- Settings needed by the parser are sourced from backend runtime settings, not hardcoded.

## Out of Scope

- Rewriting the whole extraction pipeline.
- Changing frontend task UX except for settings visibility required by parser configuration.
