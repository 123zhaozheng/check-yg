# Restore LLM Prompt and Normalization Parity

## Goal

Migrate the mature LLM prompt and fallback behavior from the original `src/llm` modules into the FastAPI backend so document portrait, table classification, and row normalization keep the same structured-output guarantees.

## Problem

The current backend prompts are shorter than the original `src` prompts. They lose important rules for account type, amount sign conventions, credit card semantics, missing years in dates, `raw_amount`, `amount`, `header_attributes`, and `column_mapping`. This creates a quiet quality regression even when API calls succeed.

## Scope

- Port or adapt the mature prompts from:
  - `src/llm/document_portrait.py`
  - `src/llm/flow_table_classifier.py`
  - `src/llm/data_normalizer.py`
- Preserve backend async HTTP implementation, but match original output contracts.
- Ensure portrait output includes the expected fields: `account_type`, `account_holder`, `account_number_masked`, `institution`, `statement_period`, `key_observations`, `amount_sign_rule`, `header_attributes`, `column_mapping`.
- Ensure normalizer output preserves `raw_amount`, positive `amount`, `transaction_type`, and `source_file` semantics.
- Reintroduce safe fallback logic for failed portrait extraction and transaction type inference where original logic had it.

## Reference Files

- `src/llm/document_portrait.py`
- `src/llm/flow_table_classifier.py`
- `src/llm/data_normalizer.py`
- `src/core/flow_extractor_v2.py`
- `backend/app/llm/portrait.py`
- `backend/app/llm/classifier.py`
- `backend/app/llm/normalizer.py`
- `backend/app/services/extraction/extractor.py`

## Acceptance Criteria

- Backend LLM modules document their input/output contracts in code or tests.
- Unit tests cover JSON parsing, empty content handling, malformed JSON fallback, and the expected field set.
- Normalization tests verify `raw_amount` is not lost and `amount` is positive.
- Portrait tests verify `column_mapping` and `header_attributes` flow into normalization payloads.
- Existing backend tests pass.

## Out of Scope

- Changing model provider UI beyond consuming existing settings keys.
- Adding vendor-specific structured schema APIs unless done as a backward-compatible enhancement.
