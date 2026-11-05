# Opik run enricher — Paperclip + Hindsight/VAI

Source derived from production local/opik-run-enricher:d27babc915c0 with one additive paperclip.run.safe_timeline span per finished, verified Paperclip run. No raw run logs, prompts, model responses, tool arguments, bearer grants or bank memories enter Opik.

The exporter joins an existing Opik trace by both paperclip_run_id and Paperclip agent UUID, and requires an end_time; it does not create a fake trace or claim run success. For each matched run it emits at most one paperclip.run.audit_summary, paperclip.run.safe_timeline, and hindsight.bank.stats_snapshot span. IDs are deterministic, and any previously published span is preserved. Snapshot data is from the agent's own bank, counts only; snapshot does not prove memory use by the run. pc_obs recall/retain entries provide independent per-run evidence only if observed. Missing events and missing traces are not imputed.

The timeline uses strict allowlisting: kind, ordinal, source timestamp, tool and MCP server name, normalized error category, limited integer fields and verification flag. Unsafe arg_excerpt, error_excerpt, auth_context, full content and any other unexpected fields are always discarded. Invalid/foreign agent records are ignored. At most 200 timeline events are attached, with truncation counters and source-log hash for provenance.

Opik MCP still exposes Opik-indexed projects, traces and spans, not arbitrary direct queries against Paperclip, private Hindsight bank memories, Ubuntu or Coolify. The protected public MCP endpoint must be accessed through its existing Cloudflare Managed OAuth identity policy; never disable or bypass Access. For genuine production validation test authenticated MCP initialize/tools-list/list(project)/read(trace), plus denied unauthenticated calls.

## Verify locally
python3 -m unittest -q test_worker && python3 -m py_compile worker.py

## Release
Use the service-specific reviewed promotion flow. Build a candidate from this source at an exact git SHA, record immutable image digest, run a bounded container against a read-only Paperclip log mount and isolated network, verify new spans by trace ID and negative data-leak tests, then promote to Coolify opik-run-enricher with verified rollback. Do not change a running production image on the basis of this file or an unreviewed PR alone. Memory/source credentials must not be copied into source or logs.
