# Edge watchdog

`coolify-caddy` publishes 80/443 for every public host. On 2026-11-13 it exited
0 during a Docker daemon restart, could not start because a referenced network
was gone, and the panel plus all Hindsight endpoints stayed unreachable for
33 minutes with no alert.

Every minute the timer checks `panel.zariszlif.pl/healthz` and
`mcp.zariszlif.pl/health`. On failure it starts `coolify-caddy` and rechecks;
the result is written to the journal as `edge-watchdog`.

```bash
install -m 0755 ops/edge-watchdog/edge-watchdog.sh /usr/local/libexec/
install -m 0644 ops/systemd/edge-watchdog.service /etc/systemd/system/
install -m 0644 ops/systemd/edge-watchdog.timer /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now edge-watchdog.timer
```

If the container still cannot start, the journal names the reason (usually
`network <id> not found`); recreate the missing network or reconnect the
container manually. The watchdog only restarts, it never deletes anything.
