# Module — CoA (Change of Authorization)

Layers onto the [base runbook](../runbook.md). ISE pushes a **live re-authorization**
to an existing session — the policy changes **in place, with no link bounce**.

## Prereq — the CoA client must be in the RADIUS-source table

This is the trap. After moving RADIUS to the global-table Vlan100 (base runbook),
the `dynamic-author` (CoA) client must live in the **same** table, or ISE's CoA is
silently dropped:

```
aaa server radius dynamic-author
 no client 198.18.134.35 vrf Mgmt-vrf server-key ISEsecret123   ! wrong table
 client 198.18.134.35 server-key ISEsecret123                   ! global table — correct
```
Symptom when wrong: ISE session shows `failed:1`, reason **`11213 No response
received from Network Access Device after sending a Dynamic Authorization request`**,
and the switch log shows **no** CoA received. (This is the CoA analog of the
SMD-RADIUS-over-Mgmt-vrf trap — task #18.)

## Trigger (via ISE MnT)

```python
ise_mnt_call(path='/CoA/Reauth/ise35/52:54:00:B6:41:10/1')
#            path form: /CoA/Reauth/{MnT node}/{endpoint MAC}/{reauthType}
#            reauthType is a NUMBER (1/2) — NOT the NAS IP (a common mistake;
#            a NAS IP in that slot gives "For input string: <ip>")
```
`{'@requestType':'reauth','results':'true'}` = the switch ACKed it. Disconnect
(bounce) variant: `/CoA/Disconnect/{node}/{mac}/{nasIp}/{disconnectType}`.

**To make the change visible:** edit the authZ rule *before* the CoA (e.g. add a
dACL profile), then CoA-reauth — the live session picks up the new result.

## Verify

```
show access-session interface Gi1/0/3 details
   before CoA:  SGT 4, no ACS ACL (PermitAccess)
   after  CoA:  SGT 4, ACS ACL: xACSACLx-…          ← new policy applied in place
show logging | include LINK-3|LINEPROTO|1/0/3       ← EMPTY: the port never went down
```
No `LINK`/`LINEPROTO` events during the CoA is the whole point — the session
re-authorized without the endpoint reconnecting.
