from types import SimpleNamespace
from cpe.resolvers import service_mentioned, resolve_service, nfs_exports


def test_namespace_qualified_service_does_not_match_other_namespace():
    svc={"metadata":{"name":"storage","namespace":"team-b"},"spec":{}}
    assert not service_mentioned("storage.team-a.svc.cluster.local refused",svc,"team-a")
    assert not service_mentioned("storage refused",svc,"team-a")
    assert service_mentioned("storage.team-b.svc.cluster.local refused",svc,"team-a")


def test_selector_conflict_does_not_follow_config_hint():
    svc={"metadata":{"name":"db","namespace":"n"},"spec":{"selector":{"app":"actual"}}}
    components={"wrong":{"namespace":"n","pod_names":["wrong-0"],"service_refs":[{"name":"db"}]},
                "actual":{"namespace":"n","pod_names":["actual-0"]}}
    captured=[({"kind":"Pod","metadata":{"name":"actual-0","namespace":"n","labels":{"app":"actual"}}},SimpleNamespace(id="source"))]
    assert resolve_service(svc,components,captured)["status"] == "Mapping conflict"
    components["wrong"]["service_refs"]=[]
    assert resolve_service(svc,components,captured)["targets"] == ["actual"]


def test_pvc_to_pv_nfs_and_missing_pv():
    component={"namespace":"n","pod_names":["p"],"containers":["app"]}
    pod={"kind":"Pod","metadata":{"name":"p","namespace":"n"},"spec":{"containers":[{"name":"app","volumeMounts":[{"name":"logs","mountPath":"/logs"}]}],"volumes":[{"name":"logs","persistentVolumeClaim":{"claimName":"logs"}}]}}
    pvc={"kind":"PersistentVolumeClaim","metadata":{"namespace":"n","name":"logs"},"spec":{"volumeName":"pv-1"}}
    pv={"kind":"PersistentVolume","metadata":{"name":"pv-1"},"spec":{"nfs":{"server":"nfs","path":"/export"}}}
    captured=[(pod,SimpleNamespace(id="pod")),(pvc,SimpleNamespace(id="pvc")),(pv,SimpleNamespace(id="pv"))]
    exports,sources,gaps=nfs_exports(component,captured)
    assert exports=={"/export"} and sources=={"pod","pvc","pv"} and not gaps
    assert nfs_exports(component,captured[:2])[2]


def test_pvc_nfs_verification_requires_matching_binding_and_explicit_nfs():
    from types import SimpleNamespace
    from cpe.resolvers import verified_pvc_nfs
    mapping={'namespace':'opsb','pvc_claim':'logs'}
    claim={'kind':'PersistentVolumeClaim','metadata':{'name':'logs','namespace':'opsb','uid':'claim-1'},'spec':{'volumeName':'pv-1'}}
    pv={'kind':'PersistentVolume','metadata':{'name':'pv-1'},'spec':{'claimRef':{'name':'logs','namespace':'opsb','uid':'claim-1'},'nfs':{'server':'nfs.internal','path':'/logs'}}}
    captured=[(claim,SimpleNamespace(id='claim-file')),(pv,SimpleNamespace(id='pv-file'))]
    assert verified_pvc_nfs(mapping,captured)['nfs_export']=='/logs'
    assert verified_pvc_nfs(mapping,captured[:1]) is None
    pv['spec']['claimRef']['uid']='other-claim'
    assert verified_pvc_nfs(mapping,captured) is None
    pv['spec']['claimRef']['uid']='claim-1'
    pv['spec']['nfs']={}
    assert verified_pvc_nfs(mapping,captured) is None
