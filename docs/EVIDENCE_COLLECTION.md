# Preparing a case evidence bundle

The application analyzes captured evidence. It does not connect to or change the customer cluster. A support engineer collects the files using their approved customer access process, then uploads them through the case intake screen.

## Intake categories

| UI card | Recommended content |
|---|---|
| NFS product logs | ZIP, TAR or TAR.GZ preserving relative paths for the affected five-day period |
| Pod descriptions | `kubectl describe pod` output in `.log` files, including namespace and volume/mount sections |
| Cluster snapshot | JSON/YAML objects for pods, nodes, PVCs and PVs; capture time and installed product/chart versions |
| Service mappings | All-namespace services plus EndpointSlices as JSON/YAML |
| Kubernetes pod logs | Current and previous container logs with timestamps; one file per namespace/pod/container |
| Import config | JSON/YAML case mapping identifying affected components, observed pods, container names, filename patterns and NFS archive prefixes |

The sample bundle and `samples/investigation-config.json` show the currently supported format. Select affected components after importing the configuration. The form supports draft cases while missing evidence is collected.

## Read-only collection examples

Run these examples in an authorized environment, with the intended context selected. Store output in a private collection directory. They are examples for the collector, not commands the analysis agent runs against customer systems.

```sh
kubectl get pods --all-namespaces -o json > pods.json
kubectl get nodes -o json > nodes.json
kubectl get services --all-namespaces -o json > services.json
kubectl get endpointslices --all-namespaces -o json > endpointslices.json
kubectl get persistentvolumeclaims --all-namespaces -o json > pvcs.json
kubectl get persistentvolumes -o json > pvs.json
kubectl get events --all-namespaces -o json > events.json
helm list --all-namespaces -o json > charts.json
```

For each affected pod/container, substitute actual names:

```sh
kubectl describe pod POD_NAME -n NAMESPACE > NAMESPACE-POD_NAME-describe.log
kubectl logs POD_NAME -n NAMESPACE -c CONTAINER_NAME --timestamps --since=120h > current.log
kubectl logs POD_NAME -n NAMESPACE -c CONTAINER_NAME --timestamps --previous > previous.log
```

Preserve current/previous logs under unique paths such as `kubernetes/NAMESPACE/POD_NAME/CONTAINER_NAME/`. A missing previous container log or an expired event is a coverage gap, not evidence of health. Cluster log retention may be shorter than five days; request the archived logging-system export when needed. Preserve collection failures in a separate manifest rather than substituting empty “successful” files.

Do not collect Kubernetes Secrets, kubeconfig credentials or model API keys. The application has basic redaction, not a complete data-loss-prevention system. Apply the company's customer-data handling policy before uploading.

## Mapping the product logs

Given a captured pod volume with NFS export `/exports/product-logs`, and files stored as `nfs/product/processor.log`, configure:

```json
{
  "schema_version": 1,
  "components": [{
    "id": "product.processor",
    "namespace": "product",
    "pod_names": ["processor-0"],
    "containers": ["processor"],
    "kubernetes_log_patterns": ["kubernetes/product/processor-0/*/*"],
    "product_log_patterns": ["processor*.log*"],
    "service_refs": [{"namespace": "product", "name": "processor-api"}]
  }],
  "archive_path_mappings": [{
    "nfs_export": "/exports/product-logs",
    "archive_prefix": "nfs/product/"
  }]
}
```

Add separate component entries for dependencies so service selectors, EndpointSlices and configured service ownership can resolve to the correct component. Supply captured PVC/PV objects for indirect NFS mounts. Unresolved CSI mounts or dynamic subPathExpr remain visible gaps.

Explicit pod names are required by the current config adapter. The configured namespace prevents equally named services in different namespaces from being treated as the same dependency. Include mappings for every relevant namespace.

## Product versions and time

Pod container image versions are read from captured pod objects. For the product overview, a structured snapshot can additionally contain a `products` list. Raw Helm chart output is retained as evidence, but arbitrary vendor chart schemas are not automatically normalized into product records. Finalize the actual product metadata adapter when the OpsB/NOM/AIOM capture samples are available.

Preserve original timestamps and timezone offsets. The current parser recognizes explicit ISO timestamps and normalizes them to UTC. It does not infer missing timezones or correct clock skew. Unknown-time records remain searchable but are excluded from chronological timeline ordering.

Embedded NUL bytes are rendered as `␀` (U+2400) in indexed text; the original archive and extracted bytes remain unchanged. File metadata includes `nul_bytes_rendered`. Invalid UTF-8 uses replacement characters; supply a known text encoding conversion as a separate evidence version for UTF-16 or other encodings.
