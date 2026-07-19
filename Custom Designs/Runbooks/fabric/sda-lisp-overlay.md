---
id: fabric/sda-lisp-overlay
category: fabric
agent: catalyst-engineer
human: none
requires: [fabric.underlay]
provides: [fabric.overlay]
params: [fabric.roles]
est: 20m
---

# fabric/sda-lisp-overlay

> LISP + pub/sub; CP/border/edge roles; map-server/resolver.

## Preflight — assert `requires`
- [ ] `fabric.underlay`

## Steps (LISP pub/sub — see [[sda-fabric-cli-cml]] + `Old/SD-Access Fabric/modules/cli-provisioning.md`)
1. **BORDER-CP (collapsed CP / Map-Server+Map-Resolver):** `router lisp` → `locator-table default` +
   `locator-set RLOC_BORDER` + **`locator default-set RLOC_BORDER`** → `service ipv4` { `map-server`,
   `map-resolver` } → `instance-id 4099` / `service ipv4` / `eid-table vrf CAMPUS_VN` → `site FABRIC`
   { `authentication-key`, `eid-record instance-id 4099 172.16.10.0/24 accept-more-specifics` }.
2. **EDGE1 (xTR):** same `locator-set` + **`locator default-set`** → `service ipv4`
   { `itr map-resolver 10.1.0.2`, `etr map-server 10.1.0.2 key <k>`, `itr`, `etr` } → `instance-id 4099`
   { `dynamic-eid CAMPUS` `database-mapping 172.16.10.0/24 locator-set …`; `service ipv4` / `eid-table vrf CAMPUS_VN` }.

## Verify — prove `provides`
BORDER-CP `show lisp session` → edge peer **Up, established 1**; `show lisp instance-id 4099 ipv4 server
summary` → **Registered 1** (once the host attaches and the edge registers its /32).

## Rollback
`no router lisp` on both (or CML wipe → day-0).

## Gotchas
- **`locator default-set <name>` is MANDATORY** — without it the map-server opens NO socket (nothing on
  4342, session "Down (never)") even though config is accepted. The #1 SD-Access-on-CML unlock.
- **Pub/sub syntax** — the MS/MR role is `service ipv4` → bare `map-server` / `map-resolver`, NOT legacy
  `ipv4 map-server` (errors `% Invalid input`).
