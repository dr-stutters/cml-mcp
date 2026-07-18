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
`198.18.134.35:443`. Also **live-verified** once the NAC fault below was cleared: HOST1's live
traffic through the FTD logs real `430002/430003` (host `.82` → `cisco:ftd:connection`) onto the
same board — no replay.

### NAC fault that had blocked live traffic (FIXED 2026-07-17)
The SDA east-west path was down — **EDGE1 `Vlan1021` (anycast GW `172.16.10.1`) line-protocol
DOWN**, because HOST1's edge port `Gi1/0/3` had **no auth session** (Closed-Auth MAB not initiating
→ autostate drops the SVI). Diagnosis: ISE/RADIUS reachable + `current UP`, port config correct
(`mab`, `access-session closed/port-control auto`, `PMAP_DefaultWiredDot1xClosedAuth_1X_MAB`),
frames arriving — but **no session, no MAC-learn, no dot1x client, ISE saw zero attempts, and a
port flap didn't clear it**: the cat9000v **edge-auth (SMD/session-manager) subsystem was wedged**.
**Fix = reload EDGE1** (`write mem` → CML `control_node` stop/start): on reboot MAB re-authorized
HOST1 → SVI up → HOST1→ISE 0% loss. **pyats gotcha:** after a CML node reload the cached console
session wedges at "Press RETURN to get started!" and never reaches the EXEC prompt — verify from a
*neighbor* node (HOST1) or restart the CML MCP to refresh the console cache.

## eStreamer — real FMC data end-to-end (DONE 2026-07-18)
`CiscoSecurityCloud`'s bundled `sbg_fw_estreamer_input` pulls connection **+ intrusion + file +
malware** events straight from FMC over TCP **8302** — genuine data that also closes the **D13**
firewall-event gap syslog doesn't carry. Recipe:

1. **FMC (GUI, `admin1`):** Integrations → eStreamer → tick the event types (all 9: Discovery,
   Correlation, Impact-Flag, Intrusion, Intrusion-Packet, User-Activity, Malware, File, Connection)
   → **Save** → **Create Client**, Hostname = the Splunk box IP `198.18.128.51` + a pkcs12 password
   → download the **pkcs12** (cert CN = the client IP; enabling eStreamer opens FMC:8302).
2. **Splunk input** — the cert isn't cleanly scriptable (the 4.0 REST handler
   `CiscoSecurityCloud_sbg_fw_estreamer_input` accepts `pkcs_certificate` but **rejects the
   `password` arg**), so use the app's **Add-Input UI** (Splunk Web → Application Setup → *Cisco
   Secure Firewall* → **E-Streamer** tab): Input Name, FMC Host `198.18.128.80`, Port 8302, upload
   the pkcs12, Password, Import Time Range = **All Firewall Event Data**, Event Types = **All**,
   Index = **network** (the app default `cisco_secure_fw` doesn't exist → save fails otherwise).
   Save validates the FMC connection with the cert. Data lands as **`cisco:sfw:estreamer`**
   (`EventType=ConnectionEvent/IntrusionEvent/FileEvent/…`) → the model's eStreamer child datasets
   → every panel. *(For a browser upload, `file_upload` only accepts session-shared files, so drop
   the pkcs12 into the chat or let the user pick it from the native dialog.)*
3. **Generate real threats** (fabric traffic must flow — see the NAC fix above):
   - **C6 intrusion:** from HOST1 `printf 'C6TRIGGER…' | nc -w1 198.18.134.35 443` — use raw **:443**
     so the Snort `content:"C6TRIGGER"` rule matches (HTTP normalization on :80/:8000 hides it) →
     real `IntrusionEvent`, signature `LOCAL C6 RTC test trigger` → IPS-by-Signature panel.
   - **C9 malware:** EICAR *server* placement is the blocker — DC01 (`.130`) is unreachable from
     CAMPUS, `SHARED-SVC` is a non-root fabric-VN alpine with no `httpd` applet. **What works: HOST1
     UPLOADS EICAR** (file policy is `direction:ANY`): `wget --post-data='<68-byte EICAR>'
     http://198.18.128.51:8000/en-US/eicar.com` → the FTD reconstructs+scans the POST body → real
     `FileEvent` (`file_name=eicar.com, SHA_Disposition=Malware, ThreatName=EICAR`) → File **and**
     Malware panels (SHA_Disposition=Malware satisfies the Malware_Events constraint).

**Verified 2026-07-18:** Connection/Intrusion/File/Malware all streaming via eStreamer; data model
datasets all populated; the Secure Firewall dashboard is **100% real** — only *Indications of
Compromise* stays empty (impact **Level 5 = not determined**; no IOC without host-vuln profiling).
Syslog (5514, above) remains fine for the connection-only board; eStreamer is the full-fidelity path.
