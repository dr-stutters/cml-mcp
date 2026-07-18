---
id: wireless/hostapd-dot1x
category: wireless
agent: wireless-engineer
human: none
requires: [ise.policy_sets, ad.users]
provides: [wireless.authenticated]
params: []
est: 15m
---

# wireless/hostapd-dot1x

> Live 802.1X via CML's hostapd AP + wpa_supplicant (hostapd != CAPWAP).

## Preflight — assert `requires`
- [ ] `ise.policy_sets`
- [ ] `ad.users`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
wpa_supplicant EAP auth → ISE session.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
