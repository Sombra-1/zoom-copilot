# Community and branding validation

The v2 release includes coverage for cumulative usage, the three-hour threshold,
sleep/idle handling, persisted one-time display and dismissal, hidden workspaces,
the live Patreon link, browser fallback, timer cleanup, and real Tk interaction.
Update tests cover numeric comparison, stable-release validation, response bounds,
timeouts, anonymous requests, cache reuse, per-version dismissal, manual retry,
offline behavior, shutdown races, and notices in the minimum-size workspace.

Branding checks cover multi-size icons, the GUI executable's embedded resources,
window icon application, and CustomTkinter icon persistence. Both notices were
visually checked together at the minimum workspace size. The answer, input and
listening controls remain accessible.

Public media shows only the app with synthetic Demo-mode content. The logo's
editable SVG, deterministic icon builder, C# launcher source and PowerShell build
script are included. No new runtime dependency was needed for these features.

See [RELEASE_CHECKS.md](RELEASE_CHECKS.md) for the complete release results.
