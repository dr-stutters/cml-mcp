# V6/V7 — Cisco Security Cloud app + Secure Firewall dashboard (Splunk)

**Goal:** install Cisco's **Cisco Security Cloud** Splunk app and light up its
**`secure_firewall_dashboard`** from the SDA lab's live **FTD syslog** — Allow/Block, access
rules, TrustSec SGT, user, destinations/ports — with **no eStreamer / FMC-GUI cert**. Target:
Splunk **198.18.128.51** (fresh Splunk **10.4.0**), FTDv **FTDv** (mgmt via FMC **198.18.128.80**).
**DONE ✅ (2026-07-17).**

## V6 — install the app (34 MB local `.tgz`, box has SSH closed)
The only REST install path is a name/URL Splunk can fetch, but **SSH is closed on `.51`** and the
lab→host tunnel is **one-way** (Splunk `Connect Timeout` fetching back to this host), and
`POST /services/apps/local` rejects a multipart body. **Working path: upload through Splunk Web
(port 8000, plain HTTP):**
1. `GET /en-US/account/login` → sets `cval` cookie.
2. `POST /en-US/account/login` with `username`/`password`/`cval` → Splunk 10 returns `{"status":0}`
   (SPA JSON) and sets the `splunkweb_csrf_token_8000` cookie.
3. `curl -F appfile=@cisco-security-cloud_*.tar.gz -H "X-Splunk-Form-Key: <csrf>"`
   `…/en-US/manager/appinstall/_upload` → **303** = success.
4. `POST /services/server/control/restart`; verify `apps/local/CiscoSecurityCloud` enabled.

> `.env` var is **`SPLUNK_PASSWORD`** (not `SPLUNK_PASS`). `cisco-secure-firewall_102.tgz` is the
> **Splunk SOAR** connector, *not* an Enterprise TA — don't use it as a feeder.

## V7 — populate the Secure Firewall dashboard from FTD syslog
The 4.0 `Cisco_Security.Secure_Firewall_Dataset` base search is
`index=* (sourcetype="cisco:sfw:estreamer" OR sourcetype="cisco:ftd:*")` — so **plain FTD syslog
works** (no eStreamer). The app ships the full parser: `cisco:ftd:syslog` has an index-time
`TRANSFORMS-set_sourcetype` that sub-classifies by FTD message-id
(**430002/430003 → `cisco:ftd:connection`**, 430001 → intrusion, 430004/5 → file/malware).

1. **Dedicated Splunk input** — UDP **5514 → sourcetype `cisco:ftd:syslog`, index `network`**,
   `connection_host=ip`. (UDP 514 is *shared* with the IOS fabric switches `.71/.72/.73` tagged
   `cisco:ios`, so you can't blanket-retag 514 — give the FTD its own port.)
2. **Re-point the FTD syslog server 514→5514** in FMC: `GET/PUT
   …/policy/ftdplatformsettingspolicies/{SDA-PlatformSettings}/syslog/servers/{id}` — change the
   server object's `port` `"514"`→`"5514"` (host-splunk, UDP, outside-zone), then `fmc_deploy`.
   *(`fmc_api_call` rejects object bodies — the harness coerces JSON to a dict; use `curl` with a
   token from `/api/fmc_platform/v1/auth/generatetoken`.)* Source stays the FTD outside IP `.82`,
   so the hand-built V1/V4 boards (`host=198.18.128.82`, rex `_raw`) keep working.
3. **One search-time props fix** — the child datasets constrain on a **`message_id`** field, but
   FTD syslog only yields `rec_type`. Add, for `cisco:ftd:{connection,intrusion,file,malware}`
   (e.g. in `search/local/props.conf`, no restart):
   `EXTRACT-zz_msgid = %FTD-\d+-(?P<message_id>\d{6})`.
4. **Enable data-model acceleration** on `Cisco_Security` (`configs/conf-datamodels/Cisco_Security`
   `acceleration=1`, `acceleration.earliest_time=-7d`). The dashboard's `tstats` panels use the
   default `summariesonly=false` (raw fallback), so they populate once `message_id` extracts; the
   child-dataset `tstats` needs the search-time field, which acceleration/​raw-fallback supplies.

**Verify:** `| tstats count from datamodel=Cisco_Security.Secure_Firewall_Dataset where
nodename=Secure_Firewall_Dataset.Connection_Events` → 83; open **CiscoSecurityCloud →
Secure Firewall** (last 24 h).

## Validation caveat + the live-traffic blocker
Validated by **replaying the day's real captured FTD `430002/430003` connection events** through
5514 (rewriting the syslog header + `FirstPacketSecond` to "now"). They carry genuine fields —
`AccessControlRuleAction` Allow/**Block**, `AccessControlRuleName` (`Permit-CAMPUS-Services` /
`Deny-CAMPUS-to-CatC`), `SourceSecurityGroup` `Employees`, `User` `mitchcloud-AD\alice`, dst
`198.18.134.35:443`. **New live events aren't flowing** because the SDA fabric east-west path is
down — **EDGE1 `Vlan1021` (anycast GW `172.16.10.1`) line-protocol DOWN**, HOST1's edge port
`Gi1/0/3` has **no auth session** (Closed-Auth MAB not authorizing → autostate drops the SVI).
CML links/interfaces are all `STARTED`, so it's a **NAC/ISE fault**, not cabling — a separate fix
(ise-engineer/catalyst-engineer). Once HOST1 authorizes and traffic crosses the FTD again, the
dashboard fills automatically.

## Alt path (richer, deferred) — eStreamer
`CiscoSecurityCloud`'s bundled `sbg_fw_estreamer_input` pulls connection **+ intrusion + file +
malware** events straight from FMC (TCP **8302** + a pkcs12 client cert minted in **FMC → System →
Integration → eStreamer**, GUI-only). That also closes the **D13** firewall-event gap syslog
doesn't carry. Syslog (above) is enough for the connection dashboard.
