# Multica Done gate

Multica enforces no evidence rules on `issue.status`, and GitHub branch
protection is unavailable on the current plan. This controller is the
independent gate for the two rules that can be checked objectively:

1. **No self-approval** — a `RELEASE_APPROVED <sha>` / `PRODUCER <uuid>` pair
   authored by the producer itself is reverted.
2. **No unverified release** — a `Release ...` issue may stay Done only when
   `/var/lib/paperclip-gitops/zar-i-szlif.json` reports `status: healthy` with
   that PR in `release_prs`, or when the issue carries the controller's
   `no_runtime_release_required` evidence for a docs-only change.

Unknown data fails open: the gate only rewrites `done` when a rule is
violated, so it cannot hide a defect it does not understand. Each issue is
reverted at most once (recorded in `reverted.json`), so a human who re-closes
an issue deliberately is not fought by a revert loop; the second close is the
audited, explicit override.

## Install

```bash
install -m 0755 ops/multica-done-gate/multica_done_gate.py /usr/local/libexec/
install -m 0644 ops/systemd/multica-done-gate.service /etc/systemd/system/
install -m 0644 ops/systemd/multica-done-gate.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now multica-done-gate.timer
```

## Check

```bash
python3 /usr/local/libexec/multica_done_gate.py --self-test
python3 /usr/local/libexec/multica_done_gate.py --dry-run
journalctl -u multica-done-gate.service -n 20
```

Reverts are written to the issue timeline as a comment and to
`/var/lib/multica-done-gate/gate.log`. Rollback is the unit removal plus
`systemctl disable --now multica-done-gate.timer`; no data is migrated.
