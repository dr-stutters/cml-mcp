# Module — Endpoints: MAB + 802.1X PEAP (installing wpa_supplicant)

Two auth paths off the same alpine HOST1 on EDGE1 Gi1/0/3.

## MAB (no supplicant) → SGT IoT
Speed the dot1x-timeout-to-MAB fallthrough, then bounce the port:
```
interface GigabitEthernet1/0/3
 dot1x timeout tx-period 5
 dot1x max-reauth-req 1
 shutdown
 no shutdown
```
`show access-session int Gi1/0/3 det` → `mab`, **Authorized**, **SGT Value: 100**.
ISE (`ise_session_by_mac`) → `authentication_method:mab`, `ISEPolicySetName:SDA_Wired`,
`AuthorizationPolicyMatchedRule:IoT_MAB`, `cts_security_group:IoT`, av-pair
`cts:security-group-tag=0064-00`, NAS `EDGE1.lab.local` (10.1.0.3).

## 802.1X PEAP as alice → SGT Employees

The alpine has **no `wpa_supplicant`** and the fabric has **no internet**. Install it by
temporarily moving HOST1 to the 198.18.x external segment:

```text
# 1. repoint HOST1 eth0 from EDGE1 to the mgmt/EXT bridge (cml MCP):
delete_link  HOST1-eth0 ↔ EDGE1-Gi1/0/3
create_link  HOST1-eth0 ↔ MGMT-SW           # the unmanaged switch bridged to EXT (System Bridge)
# 2. give it a 198.18.x address + internet DNS, then apk add (host console, sudo):
sudo ip addr flush dev eth0
sudo ip addr add 198.18.128.201/18 dev eth0
sudo ip route del default; sudo ip route add default via 198.18.128.1
printf 'nameserver 8.8.8.8\n' | sudo tee /etc/resolv.conf
ping -c2 8.8.8.8            # confirm internet
sudo apk add wpa_supplicant # → v2.11 (pulls libnl3, openssl, etc.)
# 3. write the wired supplicant config:
sudo tee /etc/wpa_supplicant/wired.conf <<'EOF'
ctrl_interface=/var/run/wpa_supplicant
eapol_version=2
ap_scan=0
network={
  key_mgmt=IEEE8021X
  eap=PEAP
  identity="alice"
  password="Cisco12345!"
  phase2="auth=MSCHAPV2"
  eapol_flags=0
}
EOF
# 4. move it back to the fabric and reset the fabric IP:
delete_link  HOST1-eth0 ↔ MGMT-SW
create_link  HOST1-eth0 ↔ EDGE1-Gi1/0/3
sudo ip addr flush dev eth0; sudo ip addr add 172.16.10.10/24 dev eth0
sudo ip route add default via 172.16.10.1
# 5. run the supplicant:
sudo wpa_supplicant -D wired -i eth0 -c /etc/wpa_supplicant/wired.conf -B
sudo wpa_cli -i eth0 status   # → EAP state=SUCCESS, PAE=AUTHENTICATED, Authorized, EAP-PEAP/MSCHAPV2
```

- **CML gotchas:** newly-created links come up **STOPPED** (`set_interface_state start`); UADP
  front-panel ports lag **~1–2 min** after a link change/bounce; a node added mid-lab needs
  `pyats_sessions refresh_testbed` before pyATS can reach it.
- Result — EDGE1 `show access-session int Gi1/0/3 det`: User `alice`, dot1x, **SGT Value: 4**.
  ISE: `PEAP (EAP-MSCHAPv2)`, `identity_store:mitchcloud`, `AuthorizationPolicyMatchedRule:
  Employees_SGT`, `cts_security_group:Employees` (`0004-00`), resolved DN
  `CN=Alice Employee,CN=Users,DC=mitchcloud,DC=lab`, group `mitchcloud.lab/Users/Employees`.
- Server-cert validation is off in the config (no `ca_cert`); for strict EAP-TLS/PEAP add
  `ca_cert=/path/mitchcloudca.pem` once ISE's EAP cert (MitchcloudCA) is bound.

## Enforcement (control-plane)
```
cts role-based enforcement
cts role-based enforcement vlan-list 1021
cts role-based sgt-map <dest-ip> sgt 200      # a Shared_Services destination binding
cts refresh policy
show cts role-based permissions   # → 4:Employees→200 SDA_Web_Permit, 5→200 Deny_IP_Log, 100→200 Deny_IP_Log
```
A live packet-drop between two hosts is not reproducible on virtual cat9000v (see the runbook's
"control-plane vs data-plane" note) — the SGACL matrix downloading onto the edge is the proof.

## Persistence — survive a HOST1 reboot (learned the hard way)

The alpine console user is **`cisco` (a sudoer, not root)** — every privileged command needs
`sudo` (an un-`sudo`'d `wpa_supplicant` fails `socket(PF_PACKET): Operation not permitted`).
The static IP + supplicant above are applied at **runtime only**, so a plain **reboot loses
them** (the alpine day-0 `node.cfg` is the default template and CatC/the port-assignment don't
touch the host). The apk-installed `wpa_supplicant` binary + `wired.conf` **do** survive a reboot
(disk persists); only the runtime state is lost. Persist the onboarding with an OpenRC boot
script (runs as root at boot, so no `sudo`/privilege problem):
```sh
sudo sh -c 'printf "#!/bin/sh\nip addr add 172.16.10.10/24 dev eth0 2>/dev/null\nip link set eth0 up\nip route add default via 172.16.10.1 2>/dev/null\n[ -x /sbin/wpa_supplicant ] && wpa_supplicant -D wired -i eth0 -c /etc/wpa_supplicant/wired.conf -B\n" > /etc/local.d/sda-endpoint.start'
sudo chmod +x /etc/local.d/sda-endpoint.start
sudo rc-update add local default        # enable the OpenRC `local` service (idempotent)
```
- **A full `wipe`** (not a reboot) reverts the disk to the base alpine image → loses the
  apk-installed `wpa_supplicant` *and* this script, and the fabric has no internet to re-`apk`.
  So the reproducible-from-scratch flow is still the link-surgery install above (move HOST1 to
  the external segment, `apk add`, move back), then drop this boot script. Editing the CML
  `node.cfg` day-0 needs the node **wiped** (config drive only regenerates on wipe), which hits
  the same no-`wpa_supplicant` problem — hence the on-disk `/etc/local.d` script is the pragmatic
  persistence layer.
