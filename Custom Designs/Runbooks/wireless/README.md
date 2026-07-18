# Wireless — C9800 + hostapd

C9800 RESTCONF config (WLAN/AAA/tags) and the live 802.1X path via CML's hostapd AP + wpa_supplicant. Driven by **wireless-engineer**. Optional stack.

## Atoms

| atom | human | provides | purpose |
|---|---|---|---|
| [`wlc-base`](wlc-base.md) | none | wlc.restconf | C9800 RESTCONF up (aaa new-model, priv-15 user, http secure-server, restconf). |
| [`wlc-radius-ise`](wlc-radius-ise.md) | none | wlc.aaa | RADIUS server + AAA group + dot1x method list to ISE; onboard the WLC as an ISE NAD. |
| [`wlc-wlan-dot1x`](wlc-wlan-dot1x.md) | none | wlc.wlan | 802.1X WLAN + policy/site/RF tags. |
| [`hostapd-dot1x`](hostapd-dot1x.md) | none | wireless.authenticated | Live 802.1X via CML's hostapd AP + wpa_supplicant (hostapd != CAPWAP). |

## Example prompts
- "Configure the C9800 WLAN with RADIUS to ISE"
- "Run the live hostapd 802.1X path and confirm the ISE session"

## Category gotchas
- RESTCONF/nginx lags boot by minutes; needs aaa new-model + priv-15 user + ip http secure-server + restconf.
- hostapd != CAPWAP: the C9800 config path and the live RF client are two SEPARATE proofs in CML.

---
See [../../REBUILD.md](../../REBUILD.md) for the atom contract, the `human:` taxonomy, and how Deployments compose atoms.
