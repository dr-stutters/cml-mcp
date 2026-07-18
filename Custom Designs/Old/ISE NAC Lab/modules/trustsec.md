# Module — TrustSec (SGT assignment + SGACL enforcement)

Layers onto the [base runbook](../runbook.md). ISE assigns a **Security Group Tag**
to the authenticated session, and the cat9000v enforces an **SGACL** between SGTs —
in **hardware**.

## ISE

```python
# SGTs already exist by default (Employees=4, Production_Servers=11, …); get values via ERS /ers/config/sgt
# SGACL (ERS raw body — drive the client directly to avoid tool-body coercion)
ers POST /ers/config/sgacl  {"Sgacl":{"name":"TS_Deny_ICMP","aclcontent":"deny icmp\npermit ip","ipVersion":"IPV4"}}
# egress matrix cell: src SGT -> dst SGT -> SGACL
ers POST /ers/config/egressmatrixcell {"EgressMatrixCell":{
     "sourceSgtId":<Employees id>,"destinationSgtId":<Production_Servers id>,
     "matrixCellStatus":"ENABLED","defaultRule":"NONE","sgacls":[<sgacl id>]}}
# assign the SGT as a RULE RESULT (not part of the profile)
authZ rule Dot1X_Restricted:  profile=['PermitAccess'], securityGroup='Employees'
```

## Switch

```
cts role-based enforcement
cts role-based enforcement vlan-list 100
! statically tag the destination (or learn it dynamically)
cts role-based sgt-map 198.18.128.1 sgt 11
! device-tracking so the endpoint IP binds to its session SGT
device-tracking policy IPDT
 tracking enable
 no protocol ndp
interface GigabitEthernet1/0/3
 device-tracking attach-policy IPDT
```
The **source SGT comes from ISE** (the session's `SGT Value`). Device-tracking maps
the endpoint's IP to that session, producing the IP→SGT binding the dataplane needs.
(The 4→11 SGACL can be configured locally, **or** downloaded from ISE — see
[CTS](cts.md).)

## Verify

```
show access-session interface Gi1/0/3 details   →  SGT Value: 4     ← assigned by ISE
show cts role-based sgt-map all                 →  198.18.160.80  4  LOCAL   (endpoint→SGT)
                                                   198.18.128.1  11  CLI     (dest→SGT)
show cts role-based permissions from 4 to 11    →  TS_Deny_ICMP
show cts role-based counters from 4 to 11       →  HW-Denied increments   ← hardware enforcement
```
**Enforcement (contrast):** endpoint (SGT 4) → `.128.1` (SGT 11) is **denied**
(the `deny icmp` SGACL); endpoint → an **unmapped** dest (SGT 0) is **permitted**.

## Gotchas

- **No device-tracking → no enforcement.** Without the IP→SGT binding the endpoint's
  traffic is SGT 0 (unknown) and nothing matches the 4→11 cell — the ping goes
  through. Attach a device-tracking policy and generate traffic so the switch learns
  the IP.
- SGT is a **rule result** (`securityGroup`), not a field of the authZ profile.
- The virtual **cat9000v-uadp genuinely enforces in HW** (the `HW-Denied` counter
  moves) — not a given on a virtual switch.
