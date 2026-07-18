# Component — FTD HA Pair (FMC)

Form an active/standby **FTD high-availability pair** via FMC. Used to make the
SD-WAN hubs resilient in the
[Firewall SD-WAN runbook](../../Cisco%20Validated%20Designs/Firewall%20SD-WAN/runbook.md).
Driven by **firewall-engineer** (`fmc_form_ha` / `POST /devicehapairs/ftddevicehapairs`).

## Prereq — a dedicated failover NIC on BOTH units, **before first boot**

FTD HA needs a spare data interface (e.g. **Gi0/3 / Ethernet0/3**) on each unit for
the LAN-failover + stateful link. **CML permanently locks a node's interface set once
it has booted** (even when STOPPED — only `wipe` frees it, which destroys the FTD disk
+ FMC registration). So **you cannot retrofit a failover NIC onto an already-registered
FTD** — build each HA unit with Gi0/3 present from the start. To HA-ify a live single
FTD (e.g. a running hub), **rebuild** it: stand up a fresh pair of NIC-equipped units,
re-apply its config, then delete the old node.

## Form the pair

```
fmc_form_ha(primary_id, secondary_id, name='NYC-HA',
            failover_interface='Ethernet0/3',
            active_ip='192.168.254.1', standby_ip='192.168.254.2', mask=24,
            shared_key='cisco123')
# ≡ POST /devicehapairs/ftddevicehapairs { primary{id}, secondary{id}, type:'DeviceHAPair',
#     ftdHABootstrap:{ sharedKey, useSameLinkForFailovers:true,
#       lanFailover:{ interfaceObject:<Eth0/3>, activeIP, standbyIP, logicalName:'FAILOVER' },
#       statefulFailover:{…} } }
```

## The two gotchas that cause "split-brain" / "Unknown"

1. **Start the failover interface immediately.** A link created while the unit is
   running comes up **STOPPED** (hot-interface) → both units go **Active**
   (split-brain) until you `set_interface_state start` the failover Gi0/3 on each end.
2. **Secondary stuck at "Unknown"** after forming the pair is usually a **pending FMC
   config push**, not a link/HA fault — check `fmc_deployable_devices` and **deploy the
   pending config to the pair**; the secondary then syncs into **Standby**. (Transient
   Failed→Standby during initial sync is normal; cosmetic red health = sftunnel flap.)

## Verify

```
fmc_get_ha_pair(id)     → primary Active / secondary Standby
# on the FTD:  show failover   → this host Active, peer Standby, both interfaces Normal
```
**Failover test:** stop the active unit (`control_node stop`) → the standby becomes
Active and takes over the role (for an SD-WAN hub: the DVTIs + inside gateway), traffic
**0% loss**; restart the old active → it rejoins as standby.
