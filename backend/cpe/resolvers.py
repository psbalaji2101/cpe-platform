"""Pure, testable resolvers over captured objects. Never query a live cluster."""
import re


def objects(files):
    result = []
    for file in files:
        data = file.metadata_json.get("structured")
        if not isinstance(data, dict):
            continue
        if data.get("kind") and data.get("kind") != "List" and not data.get("kind", "").endswith("List"):
            result.append((data, file))
        for field in ["items", "pods", "nodes", "services", "persistentVolumes", "persistentVolumeClaims", "endpointSlices"]:
            for item in data.get(field, []) if isinstance(data.get(field), list) else []:
                if isinstance(item, dict):
                    result.append((item, file))
    return result


def nfs_exports(component, captured):
    """Resolve direct NFS and PVC→PV NFS, respecting mounted volumes/containers."""
    exports, source_ids, gaps = set(), set(), []
    for pod, file in captured:
        meta = pod.get("metadata", {})
        if pod.get("kind") != "Pod" or meta.get("namespace") != component["namespace"] or meta.get("name") not in component.get("pod_names", []):
            continue
        spec = pod.get("spec", {})
        wanted = set(component.get("containers", []))
        containers = [c for c in spec.get("containers", []) if not wanted or c.get("name") in wanted]
        mounts = {m["name"]: m for c in containers for m in c.get("volumeMounts", []) if "name" in m}
        for vol in spec.get("volumes", []):
            if vol.get("name") not in mounts:
                continue
            mount = mounts[vol["name"]]
            source_ids.add(file.id)
            if mount.get("subPathExpr"):
                gaps.append("Unresolved subPathExpr for " + vol["name"])
                continue
            nfs = vol.get("nfs")
            claim_name = vol.get("persistentVolumeClaim", {}).get("claimName")
            if claim_name:
                claims = [(obj, src) for obj, src in captured if obj.get("kind") == "PersistentVolumeClaim"
                          and obj.get("metadata", {}).get("namespace") == component["namespace"]
                          and obj.get("metadata", {}).get("name") == claim_name]
                if len(claims) != 1:
                    gaps.append("Missing or ambiguous PVC " + claim_name)
                    continue
                claim, cf = claims[0]; source_ids.add(cf.id)
                pv_name = claim.get("spec", {}).get("volumeName")
                pvs = [(obj, src) for obj, src in captured if obj.get("kind") == "PersistentVolume"
                       and obj.get("metadata", {}).get("name") == pv_name]
                if len(pvs) != 1:
                    gaps.append("Missing or ambiguous PV for " + claim_name)
                    continue
                pv, pf = pvs[0]; source_ids.add(pf.id)
                nfs = pv.get("spec", {}).get("nfs")
                if not nfs:
                    gaps.append("PV storage driver is not an explicit NFS source: " + str(pv_name))
            if nfs and nfs.get("path"):
                exports.add(nfs["path"])
    return exports, source_ids, gaps


def service_mentioned(message, service, caller_namespace):
    meta, spec = service.get("metadata", {}), service.get("spec", {})
    name, namespace = meta.get("name", ""), meta.get("namespace", "default")
    if not name:
        return False
    boundary = r"(?![\w.-])"
    qualified = re.search(r"(?<![\w.-])" + re.escape(name + "." + namespace) + r"(?:\.svc(?:\.[\w.-]+)?)?" + boundary, message)
    short = namespace == caller_namespace and re.search(r"(?<![\w.-])" + re.escape(name) + boundary, message)
    ip = spec.get("clusterIP")
    address = ip and ip != "None" and re.search(r"(?<![\d.])" + re.escape(ip) + r"(?![\d.])", message)
    return bool(qualified or short or address)


def resolve_service(service, components, captured):
    meta, spec = service.get("metadata", {}), service.get("spec", {})
    name, namespace = meta.get("name"), meta.get("namespace", "default")
    if spec.get("type") == "ExternalName":
        return {"targets": [], "status": "External dependency", "detail": spec.get("externalName", "Unknown external target"), "sources": []}
    selector = spec.get("selector", {})
    selected, sources = set(), set()
    for obj, file in captured:
        m = obj.get("metadata", {})
        if obj.get("kind") == "Pod" and m.get("namespace") == namespace and selector and all(m.get("labels", {}).get(k) == v for k,v in selector.items()):
            selected.add(m.get("name")); sources.add(file.id)
        if obj.get("kind") == "EndpointSlice" and m.get("namespace") == namespace and m.get("labels", {}).get("kubernetes.io/service-name") == name:
            sources.add(file.id)
            for endpoint in obj.get("endpoints", []):
                target = endpoint.get("targetRef", {})
                if target.get("kind") == "Pod" and target.get("namespace", namespace) == namespace:
                    selected.add(target.get("name"))
    observed = [cid for cid,c in components.items() if c.get("namespace") == namespace and selected.intersection(c.get("pod_names", []))]
    hints = [cid for cid,c in components.items() if any(ref.get("name") == name and ref.get("namespace", c.get("namespace")) == namespace for ref in c.get("service_refs", []))]
    if observed:
        if hints and set(observed) != set(hints):
            return {"targets": [], "status": "Mapping conflict", "detail": "Captured backends disagree with configured service references", "sources": sorted(sources)}
        return {"targets": observed, "status": "Captured backend mapping", "detail": "Selector/EndpointSlice maps captured pods to configured components; mapping is not proof of causality", "sources": sorted(sources)}
    return {"targets": hints if len(hints)==1 else [], "status": "Config-mapped dependency" if len(hints)==1 else "Unresolved backend",
            "detail": "Backend membership could not be verified from captured objects", "sources": sorted(sources)}


def verified_pvc_nfs(mapping, captured):
    """Verify a captured PVC→PV binding for a description-backed mount mapping."""
    namespace, name = mapping.get('namespace'), mapping.get('pvc_claim')
    claims = [(obj, f) for obj, f in captured if obj.get('kind') == 'PersistentVolumeClaim'
              and obj.get('metadata', {}).get('namespace') == namespace
              and obj.get('metadata', {}).get('name') == name]
    if len(claims) != 1:
        return None
    claim, cf = claims[0]
    pv_name = claim.get('spec', {}).get('volumeName')
    pvs = [(obj, f) for obj, f in captured if obj.get('kind') == 'PersistentVolume'
           and obj.get('metadata', {}).get('name') == pv_name]
    if not pv_name or len(pvs) != 1:
        return None
    pv, pf = pvs[0]
    ref = pv.get('spec', {}).get('claimRef', {})
    if ref.get('namespace') != namespace or ref.get('name') != name:
        return None
    if ref.get('uid') and claim.get('metadata', {}).get('uid') != ref['uid']:
        return None
    nfs = pv.get('spec', {}).get('nfs', {})
    if not nfs.get('server') or not nfs.get('path'):
        return None
    return {'namespace': namespace, 'pvc_claim': name, 'pv': pv_name,
            'nfs_export': nfs['path'], 'source_file_ids': [cf.id, pf.id]}
