# Community support and release notices

## Support buttons

**Support on Patreon** opens [Sombra's membership page](https://www.patreon.com/cw/Sombra551/membership).
Patreon membership is optional and recurring. App features remain free and open
source. The **Star on GitHub** button opens this repository; the user signs in
and confirms the star on GitHub. No GitHub/Patreon credentials are collected,
and opening a link is not treated as proof of a star or payment.

Public links are configured in `support.json`. Only HTTPS links are accepted;
the repository link must use github.com. Forks may change these links.

## One-time invitation

After three accumulated hours, the workspace displays an inline invitation:
**KEEP THE CODE FREE. Back the dev, choom.** It uses original cyberpunk-inspired
copy with no licensed character artwork or quoted dialogue.

The invitation is marked shown locally as soon as it appears in a visible
workspace. It stays in that view until dismissal or a successful support-link
open. It does not reappear in later workspaces or app launches, even if the user
simply closes the app. Existing saved dismissals are respected.

Usage accumulates while the workspace is visible or listening/watching in the
background. Settings, idle tray time and long sleep gaps do not count. Progress
is saved approximately once per minute and on clean shutdown. The local file
`%LOCALAPPDATA%\ZoomCopilot\community-support.json` stores `usage_seconds`
(capped at three hours), `reminder_shown`, and `reminder_dismissed`. No usage
data is uploaded. Removing this local file resets the invitation.

## Update reminders

The installed version is defined in `copilot_core/version.py`. After startup,
the app checks the public GitHub latest-stable-release API in a background
thread. Automatic checks occur at most once per 24 hours, including across app
restarts. **Settings → version button** checks immediately, bypassing the cache.

If a newer numeric `vMAJOR.MINOR.PATCH` release exists, a quiet inline notice
shows both versions. **View release** opens only this project's GitHub releases
page. Nothing is downloaded or executed. **Later** hides that version's notice
across restarts; a newer release can notify again. A manual check restores a
dismissed notice if the update is still available. Drafts, prereleases, invalid
tags, oversized responses and redirects are rejected.

Only the latest version, dismissed version, and check timestamp are saved in
`%LOCALAPPDATA%\ZoomCopilot\updates.json`. The request sends no account token,
meeting data, screenshots, or machine identifier. GitHub receives normal
connection metadata and the app version in the User-Agent. Timeouts, rate limits,
offline operation and unwritable cache files leave the app usable.

Maintainers: publish a stable GitHub Release with a higher numeric version tag
to notify users. A Git commit by itself does not create an update notification.
Versions before 2.0 lack this checker and need one manual update first.
