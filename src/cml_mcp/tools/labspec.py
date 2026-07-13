"""Declarative topology-as-code: a concise YAML lab spec -> validate / build / export.

The spec is a small, agent-friendly YAML document (see build_lab_from_spec's
docstring) that compiles into a CML lab through the granular API path
(POST /labs -> /nodes -> /links) so errors are precise, interface labels can be
pinned, and a partial build is recoverable. export_lab_spec reverse-compiles a
live lab back into the spec format.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

from ..client import CMLAPIError, CMLClient
from . import dumps
from .annotations import _BASE_DEFAULTS, _TYPE_DEFAULTS, _with_defaults

_TOP_KEYS = {"version", "lab", "defaults", "nodes", "links", "annotations", "groups"}
_LAB_KEYS = {"title", "description", "notes"}
_DEFAULT_KEYS = {"definition", "image", "ram", "cpus", "tags"}
_NODE_KEYS = {"definition", "config", "config_json", "config_files",
              "x", "y", "image", "ram", "cpus", "tags"}
_GROUP_KEYS = {"agent", "nodes", "addressing", "tasks", "acceptance"}

_LINK_RE = re.compile(r"^\s*(.+?)\s+--\s+(.+?)\s*$")
_MAX_IFACE_CREATES = 16


class LabSpecError(ValueError):
    """All spec problems, accumulated (not just the first one)."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("invalid lab spec:\n- " + "\n- ".join(errors))


# ---------------------------------------------------------------------------
# data model
# ---------------------------------------------------------------------------

@dataclass
class NodeSpec:
    label: str
    definition: str
    config: str | list[dict[str, str]] | None = None
    x: int | None = None
    y: int | None = None
    image: str | None = None
    ram: int | None = None
    cpus: int | None = None
    tags: list[str] | None = None


@dataclass
class Endpoint:
    node: str
    interface: str | None = None


@dataclass
class LinkSpec:
    a: Endpoint
    b: Endpoint
    raw: str


@dataclass
class GroupSpec:
    name: str
    agent: str
    nodes: list[str]
    addressing: str | None = None
    tasks: str | None = None
    acceptance: str | None = None


@dataclass
class Plan:
    title: str
    description: str
    notes: str
    nodes: list[NodeSpec]
    links: list[LinkSpec]
    annotations: list[dict[str, Any]]
    groups: list[GroupSpec]
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# YAML helpers (dup-key-rejecting loader; block-scalar-friendly dumper)
# ---------------------------------------------------------------------------

class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys (YAML silently overwrites)."""

    def construct_mapping(self, node, deep=False):
        seen: set[Any] = set()
        for key_node, _value in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue  # merge keys (<<: *anchor) may legitimately be overridden
            key = self.construct_object(key_node, deep=True)
            try:
                if key in seen:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping", node.start_mark,
                        f"found duplicate key {key!r}", key_node.start_mark)
                seen.add(key)
            except TypeError:
                continue  # unhashable key; let the base constructor complain
        return super().construct_mapping(node, deep=deep)


class _SpecDumper(yaml.SafeDumper):
    """Local dumper (never mutate the global yaml module - labs.py shares it)."""


def _str_representer(dumper: yaml.Dumper, data: str):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_SpecDumper.add_representer(str, _str_representer)


# ---------------------------------------------------------------------------
# pure: parse + validate
# ---------------------------------------------------------------------------

def _parse_endpoint(value: Any) -> Endpoint:
    if isinstance(value, str):
        v = value.strip()
        node, _, iface = v.partition(":")
        node, iface = node.strip(), iface.strip()
        if not node:
            raise ValueError(f"bad endpoint {value!r}")
        return Endpoint(node=node, interface=iface or None)
    if isinstance(value, dict):
        unknown = set(value) - {"node", "interface"}
        if unknown:
            raise ValueError(f"endpoint has unknown key(s) {sorted(unknown)}")
        node = value.get("node")
        if not isinstance(node, str) or not node:
            raise ValueError("endpoint.node is required (string)")
        iface = value.get("interface")
        if iface is not None and not isinstance(iface, str):
            raise ValueError("endpoint.interface must be a string")
        return Endpoint(node=node, interface=iface or None)
    raise ValueError("endpoint must be 'node[:interface]' or {node, interface}")


def _parse_link(item: Any) -> LinkSpec:
    if isinstance(item, str):
        m = _LINK_RE.match(item)
        if not m:
            raise ValueError(
                f"{item!r} - expected 'A[:iface] -- B[:iface]' (spaces around --) "
                "or the structured {a, b} form")
        return LinkSpec(a=_parse_endpoint(m.group(1)), b=_parse_endpoint(m.group(2)),
                        raw=item.strip())
    if isinstance(item, dict):
        if set(item) != {"a", "b"}:
            raise ValueError("structured link needs exactly the keys a and b")
        a, b = _parse_endpoint(item["a"]), _parse_endpoint(item["b"])
        raw = f"{a.node}:{a.interface or '(auto)'} -- {b.node}:{b.interface or '(auto)'}"
        return LinkSpec(a=a, b=b, raw=raw)
    raise ValueError("link must be a string or an {a, b} mapping")


def _auto_layout(nodes: list[NodeSpec]) -> None:
    """Grid-place nodes without explicit coords, below any explicitly placed ones."""
    auto = [n for n in nodes if n.x is None]
    if not auto:
        return
    explicit_y = [n.y for n in nodes if n.y is not None]
    y0 = (max(explicit_y) + 200) if explicit_y else 0
    cols = max(1, math.ceil(math.sqrt(len(auto))))
    for i, n in enumerate(auto):
        n.x = (i % cols) * 180
        n.y = y0 + (i // cols) * 180


def parse_spec(text: str) -> Plan:  # noqa: C901 - one linear validation pass
    """Parse + validate a lab spec; raises LabSpecError listing ALL problems."""
    errors: list[str] = []
    warnings: list[str] = []
    try:
        data = yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as e:
        raise LabSpecError([f"YAML parse error: {e}"]) from e
    if not isinstance(data, dict):
        raise LabSpecError(["spec must be a YAML mapping with lab: and nodes: keys"])

    unknown = set(data) - _TOP_KEYS
    if unknown:
        errors.append(f"unknown top-level key(s): {sorted(map(str, unknown))} "
                      f"(allowed: {sorted(_TOP_KEYS)})")
    if data.get("version", 1) != 1:
        errors.append(f"unsupported spec version {data.get('version')!r} (only 1)")

    lab = data.get("lab")
    title = description = notes = ""
    if not isinstance(lab, dict) or not isinstance(lab.get("title"), str) \
            or not lab["title"].strip():
        errors.append("lab.title is required (string)")
    else:
        bad = set(lab) - _LAB_KEYS
        if bad:
            errors.append(f"lab: unknown key(s) {sorted(bad)} (allowed: {sorted(_LAB_KEYS)})")
        title = lab["title"]
        description = str(lab.get("description") or "")
        notes = str(lab.get("notes") or "")

    defaults = data.get("defaults") or {}
    if not isinstance(defaults, dict):
        errors.append("defaults must be a mapping")
        defaults = {}
    bad = set(defaults) - _DEFAULT_KEYS
    if bad:
        errors.append(f"defaults: unknown key(s) {sorted(bad)} (allowed: {sorted(_DEFAULT_KEYS)})")

    nodes_raw = data.get("nodes")
    if not isinstance(nodes_raw, dict) or not nodes_raw:
        errors.append("nodes is required: a non-empty mapping of label -> node object")
        nodes_raw = {}

    node_specs: list[NodeSpec] = []
    for raw_label, body in nodes_raw.items():
        label = str(raw_label)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            errors.append(f"node '{label}': must be a mapping (or empty to use defaults)")
            continue
        bad = set(body) - _NODE_KEYS
        if bad:
            errors.append(f"node '{label}': unknown key(s) {sorted(bad)} "
                          f"(allowed: {sorted(_NODE_KEYS)})")

        def _int_field(name: str, value: Any, label: str = label) -> int | None:
            if value is None:
                return None
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(f"node '{label}': {name} must be an integer")
                return None
            return value

        definition = body.get("definition", defaults.get("definition"))
        if not isinstance(definition, str) or not definition:
            errors.append(f"node '{label}': definition is required "
                          "(set it on the node or in defaults.definition)")
            definition = ""
        image = body.get("image", defaults.get("image"))
        if image is not None and not isinstance(image, str):
            errors.append(f"node '{label}': image must be a string")
            image = None
        ram = _int_field("ram", body.get("ram", defaults.get("ram")))
        cpus = _int_field("cpus", body.get("cpus", defaults.get("cpus")))
        x = _int_field("x", body.get("x"))
        y = _int_field("y", body.get("y"))
        if (x is None) != (y is None):
            errors.append(f"node '{label}': x and y must be given together")
            x = y = None
        tags = body.get("tags", defaults.get("tags"))
        if tags is not None and (not isinstance(tags, list)
                                 or not all(isinstance(t, str) for t in tags)):
            errors.append(f"node '{label}': tags must be a list of strings")
            tags = None

        forms = [k for k in ("config", "config_json", "config_files") if k in body]
        config: str | list[dict[str, str]] | None = None
        if len(forms) > 1:
            errors.append(f"node '{label}': use exactly one of config/config_json/config_files")
        elif forms == ["config"]:
            if not isinstance(body["config"], str):
                errors.append(f"node '{label}': config must be a string "
                              "(use config_json for a JSON day-0 document)")
            else:
                config = body["config"]
        elif forms == ["config_json"]:
            if not isinstance(body["config_json"], dict):
                errors.append(f"node '{label}': config_json must be a mapping")
            else:
                config = json.dumps(body["config_json"], indent=2)
        elif forms == ["config_files"]:
            v = body["config_files"]
            ok = (isinstance(v, list) and v and all(
                isinstance(f, dict) and set(f) == {"name", "content"}
                and isinstance(f.get("name"), str) and isinstance(f.get("content"), str)
                for f in v))
            if not ok:
                errors.append(f"node '{label}': config_files must be a non-empty list "
                              "of {name, content} string pairs")
            else:
                config = [dict(f) for f in v]
        node_specs.append(NodeSpec(label=label, definition=definition, config=config,
                                   x=x, y=y, image=image, ram=ram, cpus=cpus, tags=tags))

    for n in node_specs:
        if n.definition in ("ftdv", "fmcv"):
            if n.config is None:
                errors.append(f"node '{n.label}': {n.definition} requires a day-0 JSON document "
                              "(config_json with EULA/AdminPassword/mgmt fields)")
            elif isinstance(n.config, list):
                errors.append(f"node '{n.label}': {n.definition} day-0 must be a single JSON "
                              "document (config or config_json), not config_files")
            else:
                try:
                    json.loads(n.config)
                except json.JSONDecodeError:
                    errors.append(f"node '{n.label}': {n.definition} day-0 must be valid JSON "
                                  "(prefer config_json)")

    labels = {n.label for n in node_specs}
    links_raw = data.get("links") or []
    if not isinstance(links_raw, list):
        errors.append("links must be a list")
        links_raw = []
    link_specs: list[LinkSpec] = []
    for idx, item in enumerate(links_raw, 1):
        try:
            lk = _parse_link(item)
        except ValueError as e:
            errors.append(f"link {idx}: {e}")
            continue
        for ep in (lk.a, lk.b):
            if ep.node not in labels:
                errors.append(f"link {idx} ({lk.raw}): unknown node '{ep.node}' "
                              "(labels containing ':' or ' -- ' need the structured "
                              "{a: {node, interface}, b: ...} form)")
        link_specs.append(lk)

    ext_labels = {n.label for n in node_specs if n.definition == "external_connector"}
    ext_refs = Counter(ep.node for lk in link_specs for ep in (lk.a, lk.b)
                       if ep.node in ext_labels)
    for lbl, cnt in sorted(ext_refs.items()):
        if cnt > 1:
            errors.append(f"external connector '{lbl}' is referenced by {cnt} links - "
                          "it is a single-port device (add one connector per attachment)")

    anns_raw = data.get("annotations") or []
    if not isinstance(anns_raw, list):
        errors.append("annotations must be a list")
        anns_raw = []
    annotations: list[dict[str, Any]] = []
    for idx, a in enumerate(anns_raw, 1):
        if not isinstance(a, dict) or a.get("type") not in _TYPE_DEFAULTS:
            errors.append(f"annotation {idx}: must be a mapping with "
                          f"type one of {sorted(_TYPE_DEFAULTS)}")
            continue
        annotations.append(a)

    groups_raw = data.get("groups") or {}
    if not isinstance(groups_raw, dict):
        errors.append("groups must be a mapping of group name -> {agent, nodes, ...}")
        groups_raw = {}
    group_specs: list[GroupSpec] = []
    assigned: dict[str, str] = {}
    for raw_name, g in groups_raw.items():
        name = str(raw_name)
        if not isinstance(g, dict):
            errors.append(f"group '{name}': must be a mapping")
            continue
        bad = set(g) - _GROUP_KEYS
        if bad:
            errors.append(f"group '{name}': unknown key(s) {sorted(bad)} "
                          f"(allowed: {sorted(_GROUP_KEYS)})")
        agent = g.get("agent")
        if not isinstance(agent, str) or not agent:
            errors.append(f"group '{name}': agent is required (specialist agent name)")
            agent = "?"
        gnodes = g.get("nodes")
        if not isinstance(gnodes, list) or not gnodes \
                or not all(isinstance(v, str) for v in gnodes):
            errors.append(f"group '{name}': nodes must be a non-empty list of node labels")
            gnodes = []
        for lbl in gnodes:
            if lbl not in labels:
                errors.append(f"group '{name}': unknown node '{lbl}'")
            elif lbl in assigned:
                errors.append(f"node '{lbl}' is in groups '{assigned[lbl]}' and '{name}' - "
                              "device groups must be disjoint "
                              "(two specialists never share a console)")
            else:
                assigned[lbl] = name
        texts: dict[str, str | None] = {}
        for fname in ("addressing", "tasks", "acceptance"):
            v = g.get(fname)
            if v is not None and not isinstance(v, str):
                errors.append(f"group '{name}': {fname} must be a string")
                v = None
            texts[fname] = v
        if not (texts["tasks"] or "").strip():
            warnings.append(f"group '{name}': no tasks given - "
                            "the brief will say '(none provided)'")
        group_specs.append(GroupSpec(name=name, agent=agent, nodes=gnodes, **texts))
    if group_specs:
        uncovered = [n.label for n in node_specs if n.label not in assigned]
        if uncovered:
            warnings.append("nodes not covered by any group (fine for infra like "
                            f"connectors/unmanaged switches): {', '.join(uncovered)}")

    if ext_labels:
        warnings.append("external connector(s) present: after starting the lab, confirm they "
                        "are STARTED (they come up DEFINED_ON_CORE and nothing reaches the "
                        "underlay until started)")
    if any(n.definition in ("ftdv", "fmcv") for n in node_specs):
        warnings.append("ftdv/fmcv boot slowly (FTDv API 10-20 min after BOOTED, "
                        "FMCv 15-30 min) - wait before delegating configuration")
    for n in node_specs:
        if n.definition.startswith("cat9000v") and n.ram is None:
            warnings.append(f"node '{n.label}': cat9000v wants ~18 GB RAM - consider setting ram")
    if link_specs:
        linked = {ep.node for lk in link_specs for ep in (lk.a, lk.b)}
        loners = [n.label for n in node_specs if n.label not in linked]
        if loners:
            warnings.append(f"node(s) with no links: {', '.join(loners)}")

    if errors:
        raise LabSpecError(errors)
    plan = Plan(title=title, description=description, notes=notes, nodes=node_specs,
                links=link_specs, annotations=annotations, groups=group_specs,
                warnings=warnings)
    _auto_layout(plan.nodes)
    return plan


# ---------------------------------------------------------------------------
# pure: interface matching, briefs, reports
# ---------------------------------------------------------------------------

def _split_iface_label(label: str) -> tuple[str, str]:
    """'GigabitEthernet0/1' -> ('gigabitethernet', '0/1'); 'ens2' -> ('ens', '2')."""
    i = 0
    while i < len(label) and not label[i].isdigit():
        i += 1
    return label[:i].strip().casefold(), "".join(label[i:].split())


def match_interface(requested: str, ifaces: list[dict[str, Any]],
                    node_label: str) -> dict[str, Any] | None:
    """Match an interface label, allowing IOS-style abbreviations (Gi0/1).

    Returns None if nothing matches (caller may create interfaces); raises
    ValueError when the abbreviation is ambiguous - never guesses.
    """
    phys = [i for i in ifaces if i.get("type", "physical") == "physical"]
    req_cf = requested.strip().casefold()
    exact = [i for i in phys if str(i.get("label", "")).casefold() == req_cf]
    if exact:
        return exact[0]
    rp, rt = _split_iface_label(requested)
    cands = []
    for i in phys:
        cp, ct = _split_iface_label(str(i.get("label", "")))
        if rp and cp.startswith(rp) and ct == rt:
            cands.append(i)
    if len(cands) > 1:
        raise ValueError(f"interface '{requested}' on {node_label} is ambiguous: matches "
                         + ", ".join(str(i.get("label")) for i in cands))
    return cands[0] if cands else None


def _brief_field(name: str, text: str | None) -> str:
    if not text or not text.strip():
        return f"{name}: (none provided)"
    text = text.rstrip("\n")
    if "\n" in text:
        return f"{name}:\n" + "\n".join("  " + ln for ln in text.split("\n"))
    return f"{name}: {text}"


def render_briefs(plan: Plan, lab_id: str, link_report: list[dict[str, Any]],
                  started: bool) -> list[str]:
    """Render per-group delegation briefs in the cml-lab-architect contract format."""
    defs = {n.label: n.definition for n in plan.nodes}
    state = "started, awaiting convergence" if started else "built, not started"
    briefs = []
    for g in plan.groups:
        glinks = [lr for lr in link_report
                  if lr["a"]["node"] in g.nodes or lr["b"]["node"] in g.nodes]
        links_text = "\n".join(
            f"{lr['a']['node']} {lr['a']['interface']} <-> "
            f"{lr['b']['node']} {lr['b']['interface']}" for lr in glinks) or "(none)"
        briefs.append("\n".join([
            f"### Brief: {g.name} -> {g.agent}",
            f"lab_id: {lab_id}",
            f"state: {state}",
            "nodes: " + ", ".join(f"{lbl} ({defs.get(lbl, '?')})" for lbl in g.nodes),
            _brief_field("links", links_text),
            _brief_field("addressing", g.addressing),
            _brief_field("tasks", g.tasks),
            _brief_field("acceptance", g.acceptance),
        ]))
    return briefs


def _dry_link_report(plan: Plan) -> list[dict[str, Any]]:
    return [{"spec": lk.raw,
             "a": {"node": lk.a.node, "interface": lk.a.interface or "(auto)"},
             "b": {"node": lk.b.node, "interface": lk.b.interface or "(auto)"}}
            for lk in plan.links]


def _plan_report(plan: Plan) -> dict[str, Any]:
    nodes: dict[str, Any] = {}
    for n in plan.nodes:
        e: dict[str, Any] = {"definition": n.definition, "x": n.x, "y": n.y}
        if n.image:
            e["image"] = n.image
        if n.ram is not None:
            e["ram"] = n.ram
        if n.cpus is not None:
            e["cpus"] = n.cpus
        if n.tags:
            e["tags"] = n.tags
        if isinstance(n.config, str):
            e["config"] = f"({len(n.config)} chars)"
        elif isinstance(n.config, list):
            e["config_files"] = [f["name"] for f in n.config]
        nodes[n.label] = e
    return {
        "lab": {"title": plan.title},
        "nodes": nodes,
        "links": [{"spec": lk.raw,
                   "a": {"node": lk.a.node, "interface": lk.a.interface,
                         "pinned": lk.a.interface is not None},
                   "b": {"node": lk.b.node, "interface": lk.b.interface,
                         "pinned": lk.b.interface is not None}}
                  for lk in plan.links],
        "annotations": len(plan.annotations),
        "groups": [g.name for g in plan.groups],
        "warnings": plan.warnings,
    }


# ---------------------------------------------------------------------------
# pure: export (live lab -> spec)
# ---------------------------------------------------------------------------

def spec_from_topology(topology: dict[str, Any]) -> str:
    """Reverse-compile a /labs/{id}/topology document into the concise spec YAML."""
    lab = topology.get("lab") or {}
    nodes = topology.get("nodes") or []
    links = topology.get("links") or []
    anns = topology.get("annotations") or []

    spec: dict[str, Any] = {"version": 1}
    lab_out: dict[str, Any] = {"title": lab.get("title") or "untitled"}
    if lab.get("description"):
        lab_out["description"] = lab["description"]
    if lab.get("notes"):
        lab_out["notes"] = lab["notes"]
    spec["lab"] = lab_out

    hoist = None
    defs = [n.get("node_definition") for n in nodes]
    if defs:
        modal, count = Counter(defs).most_common(1)[0]
        if count > 1:
            hoist = modal
            spec["defaults"] = {"definition": hoist}

    node_out: dict[str, Any] = {}
    iface_names: dict[str, tuple[str, str]] = {}  # iface id -> (node label, iface label)
    for n in nodes:
        label = n.get("label") or "?"
        for i in n.get("interfaces") or []:
            iface_names[i.get("id")] = (label, i.get("label") or "?")
        e: dict[str, Any] = {}
        if n.get("node_definition") != hoist:
            e["definition"] = n.get("node_definition")
        cfg = n.get("configuration")
        if isinstance(cfg, str) and cfg:
            e["config"] = cfg
        elif isinstance(cfg, list) and cfg:
            if len(cfg) == 1:
                e["config"] = cfg[0].get("content") or ""
            else:
                e["config_files"] = [{"name": f.get("name") or "", "content": f.get("content") or ""}
                                     for f in cfg]
        if n.get("x") is not None:
            e["x"] = n["x"]
        if n.get("y") is not None:
            e["y"] = n["y"]
        if n.get("image_definition"):
            e["image"] = n["image_definition"]
        if n.get("ram") is not None:
            e["ram"] = n["ram"]
        if n.get("cpus") is not None:
            e["cpus"] = n["cpus"]
        if n.get("tags"):
            e["tags"] = list(n["tags"])
        node_out[label] = e or None
    spec["nodes"] = node_out

    link_out: list[Any] = []
    for lk in links:
        a = iface_names.get(lk.get("interface_a"))
        b = iface_names.get(lk.get("interface_b"))
        if not a or not b:
            continue
        if any(":" in nl or " -- " in nl for nl, _ in (a, b)):
            link_out.append({"a": {"node": a[0], "interface": a[1]},
                             "b": {"node": b[0], "interface": b[1]}})
        else:
            link_out.append(f"{a[0]}:{a[1]} -- {b[0]}:{b[1]}")
    if link_out:
        spec["links"] = link_out

    ann_out = []
    for a in anns:
        atype = a.get("type")
        if atype not in _TYPE_DEFAULTS:
            continue
        base = {**_BASE_DEFAULTS, **_TYPE_DEFAULTS[atype]}
        keep = {k: v for k, v in a.items()
                if k != "id" and (k not in base or base[k] != v)}
        keep["type"] = atype
        ann_out.append(keep)
    if ann_out:
        spec["annotations"] = ann_out

    return yaml.dump(spec, Dumper=_SpecDumper, sort_keys=False,
                     default_flow_style=False, allow_unicode=True, width=100)


# ---------------------------------------------------------------------------
# async: live checks + the compiler
# ---------------------------------------------------------------------------

async def _live_check_definitions(client: CMLClient, plan: Plan) -> list[str]:
    errors = []
    defs = await client.get("/node_definitions")
    known = {d.get("id") for d in defs if isinstance(d, dict)}
    for n in plan.nodes:
        if n.definition not in known:
            errors.append(f"node '{n.label}': unknown node definition '{n.definition}'")
    if any(n.image for n in plan.nodes):
        imgs = await client.get("/image_definitions")
        known_imgs = {d.get("id") for d in imgs if isinstance(d, dict)}
        for n in plan.nodes:
            if n.image and n.image not in known_imgs:
                errors.append(f"node '{n.label}': unknown image definition '{n.image}'")
    return errors


class _IfaceAllocator:
    """Per-build interface resolver: label pinning + next-free, no double allocation."""

    def __init__(self, client: CMLClient, lab_id: str):
        self.client = client
        self.lab_id = lab_id
        self.cache: dict[str, list[dict[str, Any]]] = {}
        self.used: set[str] = set()

    async def _ifaces(self, node_id: str) -> list[dict[str, Any]]:
        if node_id not in self.cache:
            self.cache[node_id] = await self.client.get(
                f"/labs/{self.lab_id}/nodes/{node_id}/interfaces", params={"data": True})
        return self.cache[node_id]

    async def _create_one(self, node_id: str) -> list[dict[str, Any]]:
        created = await self.client.post(f"/labs/{self.lab_id}/interfaces",
                                         json_body={"node": node_id})
        new = created if isinstance(created, list) else [created]
        have = {i.get("id") for i in self.cache.get(node_id, [])}
        fresh = [i for i in new if i.get("id") not in have]
        self.cache.setdefault(node_id, []).extend(fresh)
        return fresh

    async def resolve(self, node_label: str, node_id: str, requested: str | None,
                      warnings: list[str]) -> tuple[str, str]:
        """Return (interface_id, interface_label) for one link endpoint."""
        ifaces = await self._ifaces(node_id)
        if requested is None:
            for i in ifaces:
                if (i.get("type", "physical") == "physical"
                        and not i.get("is_connected") and i["id"] not in self.used):
                    self.used.add(i["id"])
                    return i["id"], i.get("label") or "?"
            for i in await self._create_one(node_id):
                if i.get("type", "physical") == "physical" and i["id"] not in self.used:
                    self.used.add(i["id"])
                    return i["id"], i.get("label") or "?"
            raise ValueError(f"could not allocate a free interface on {node_label}")

        match = match_interface(requested, ifaces, node_label)
        creates = 0
        while match is None and creates < _MAX_IFACE_CREATES:
            fresh = await self._create_one(node_id)
            creates += 1
            if not fresh:
                break
            match = match_interface(requested, ifaces, node_label)
            if match is not None:
                warnings.append(
                    f"created {match.get('label')} on {node_label} to satisfy the pin - "
                    "interfaces added to a running node come up STOPPED "
                    "(start with set_interface_state)")
        if match is None:
            have = ", ".join(str(i.get("label")) for i in ifaces
                             if i.get("type", "physical") == "physical")
            raise ValueError(
                f"interface '{requested}' not found on {node_label} (have: {have}) - "
                "this node definition may not produce that label; check get_node_definition")
        if match.get("is_connected") or match["id"] in self.used:
            raise ValueError(f"interface '{match.get('label')}' on {node_label} "
                             "is already connected")
        self.used.add(match["id"])
        return match["id"], match.get("label") or requested


async def _execute(client: CMLClient, plan: Plan, start: bool,
                   rollback: bool) -> dict[str, Any]:
    warnings = list(plan.warnings)
    node_ids: dict[str, str] = {}
    link_report: list[dict[str, Any]] = []
    ann_count = 0
    lab_id: str | None = None
    started = False
    step = "create lab"
    try:
        lab = await client.post("/labs", json_body={
            "title": plan.title, "description": plan.description, "notes": plan.notes})
        lab_id = lab["id"]
        for n in plan.nodes:
            step = f"add node {n.label}"
            body: dict[str, Any] = {"label": n.label, "node_definition": n.definition,
                                    "x": n.x, "y": n.y}
            if n.config is not None:
                body["configuration"] = n.config
            if n.image:
                body["image_definition"] = n.image
            if n.ram is not None:
                body["ram"] = n.ram
            if n.cpus is not None:
                body["cpus"] = n.cpus
            if n.tags:
                body["tags"] = n.tags
            r = await client.post(f"/labs/{lab_id}/nodes", json_body=body,
                                  params={"populate_interfaces": True})
            node_ids[n.label] = r["id"]
        alloc = _IfaceAllocator(client, lab_id)
        for lk in plan.links:
            step = f"link {lk.raw}"
            a_id, a_lbl = await alloc.resolve(lk.a.node, node_ids[lk.a.node],
                                              lk.a.interface, warnings)
            b_id, b_lbl = await alloc.resolve(lk.b.node, node_ids[lk.b.node],
                                              lk.b.interface, warnings)
            r = await client.post(f"/labs/{lab_id}/links",
                                  json_body={"src_int": a_id, "dst_int": b_id})
            link_report.append({"spec": lk.raw,
                                "link_id": r.get("id") if isinstance(r, dict) else None,
                                "a": {"node": lk.a.node, "interface": a_lbl},
                                "b": {"node": lk.b.node, "interface": b_lbl}})
        for ann in plan.annotations:
            step = "annotations"
            await client.post(f"/labs/{lab_id}/annotations", json_body=_with_defaults(ann))
            ann_count += 1
        if start:
            step = "start lab"
            await client.put(f"/labs/{lab_id}/start")
            started = True
            warnings.append("lab starting - poll get_lab_state until converged "
                            "before delegating device configuration")
        return {"lab_id": lab_id, "title": plan.title,
                "state": "started" if started else "built",
                "nodes": node_ids, "links": link_report, "annotations": ann_count,
                "briefs": render_briefs(plan, lab_id, link_report, started),
                "warnings": warnings}
    except (CMLAPIError, ValueError) as e:
        failure: dict[str, Any] = {
            "state": "partial", "error": str(e), "failed_step": step, "lab_id": lab_id,
            "nodes": node_ids, "links": link_report, "warnings": warnings}
        if rollback and lab_id:
            try:
                if started:
                    await client.put(f"/labs/{lab_id}/stop")
                    await client.put(f"/labs/{lab_id}/wipe")
                await client.delete(f"/labs/{lab_id}")
                failure.update({"state": "rolled_back", "nodes": {}, "links": []})
            except CMLAPIError as rb_err:
                failure["rollback_error"] = str(rb_err)
        return failure


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------

def register(mcp: FastMCP, client: CMLClient) -> None:
    @mcp.tool()
    async def validate_lab_spec(spec: str, live: bool = True) -> str:
        """Validate a declarative YAML lab spec without building anything.

        Returns {valid, errors?, warnings, nodes, links, ...}. With live=True
        (default) node/image definition names are also checked against the
        server; live=False is a purely offline schema check. See
        build_lab_from_spec for the spec format.
        """
        try:
            plan = parse_spec(spec)
        except LabSpecError as e:
            return dumps({"valid": False, "errors": e.errors})
        if live:
            errors = await _live_check_definitions(client, plan)
            if errors:
                return dumps({"valid": False, "errors": errors, "warnings": plan.warnings})
        return dumps({"valid": True, **_plan_report(plan)})

    @mcp.tool()
    async def build_lab_from_spec(spec: str, start: bool = False, dry_run: bool = False,
                                  rollback_on_error: bool = False) -> str:
        """Build a complete CML lab from a declarative YAML spec in one call.

        Spec format (topology-as-code; also produced by export_lab_spec):

            version: 1
            lab: {title: My Lab, description: ..., notes: ...}
            defaults: {definition: iol-xe}       # merged under every node
            nodes:                               # label -> node ({} ok with defaults)
              R1:
                definition: iol-xe               # or from defaults
                config: |                        # day-0 text (exactly one of
                  hostname R1                    #  config/config_json/config_files)
                x: 100                           # optional; auto grid layout if omitted
                y: 0
                ram: 4096                        # optional: image, ram, cpus, tags
              FTD-1:
                definition: ftdv
                config_json: {EULA: accept, ...} # JSON day-0 (ftdv/fmcv) as native YAML
              AP-1:
                definition: wireless-ap
                config_files:                    # multi-file day-0 (cloud-init)
                  - {name: user-data, content: "#cloud-config\\n..."}
                  - {name: network-config, content: "..."}
              SYS-EXT: {definition: external_connector, config: System Bridge}
            links:
              - R1:GigabitEthernet0/1 -- SW1:Gi1/0/1   # pinned (IOS abbreviations ok)
              - R2 -- SW1                              # auto next-free interface
              - {a: "R1:Gi0/2", b: {node: SW2, interface: Gi1/0/2}}
            annotations:
              - {type: text, text_content: CORE, x1: 0, y1: -80}
            groups:                              # optional -> delegation briefs
              access: {agent: catalyst-engineer, nodes: [SW1],
                       addressing: ..., tasks: ..., acceptance: ...}

        Nothing is created unless the whole spec validates (incl. live definition
        names). dry_run=True returns the resolved plan without building.
        start=True starts the lab after building (poll get_lab_state yourself -
        this never waits for convergence). On a mid-build failure the report has
        state=partial plus what was built, or the lab is deleted when
        rollback_on_error=True. The report's briefs array contains one
        delegation brief per group, ready to hand to specialist agents.
        """
        plan = parse_spec(spec)
        errors = await _live_check_definitions(client, plan)
        if errors:
            raise LabSpecError(errors)
        if dry_run:
            if start:
                plan.warnings.append("dry_run beats start: nothing was started")
            report = _plan_report(plan)
            report["dry_run"] = True
            report["briefs"] = render_briefs(plan, "(dry run)", _dry_link_report(plan),
                                             started=False)
            return dumps(report)
        return dumps(await _execute(client, plan, start=start, rollback=rollback_on_error))

    @mcp.tool()
    async def export_lab_spec(lab_id: str) -> str:
        """Export a lab as a concise declarative YAML spec (topology-as-code).

        The reverse of build_lab_from_spec - suitable for version control
        (e.g. 'Custom Designs/<Design>/topology.yaml') and rebuilding. Lossy by
        design: UUIDs, MACs, extra unconnected interfaces, smart annotations
        (regenerated from tags), and lab state are not represented. For CML's
        native verbose format use export_lab instead.
        """
        topo = await client.get(f"/labs/{lab_id}/topology",
                                params={"exclude_configurations": False})
        return spec_from_topology(topo)
