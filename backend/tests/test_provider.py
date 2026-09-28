import json
import pytest
from cpe.config import settings
from cpe.providers import synthesize


def setup_provider(monkeypatch):
    for k,v in {"llm_provider":"compatible", "llm_base_url":"https://approved.internal/v1", "llm_allowed_hosts":"approved.internal", "llm_model":"test-model", "llm_api_key":"not-a-real-key"}.items():
        monkeypatch.setattr(settings,k,v)


def test_endpoint_allowlist(monkeypatch):
    setup_provider(monkeypatch)
    monkeypatch.setattr(settings,"llm_base_url","https://unapproved.example/v1")
    with pytest.raises(ValueError,match="allowlist"):
        synthesize([])


@pytest.mark.parametrize("unauthorized",[False,True])
def test_compatible_tool_loop(monkeypatch,unauthorized):
    setup_provider(monkeypatch)
    calls=[]
    class Response:
        def __init__(self,message):self.message=message
        def raise_for_status(self):pass
        def json(self):return {"choices":[{"message":self.message}]}
    class Client:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kw):
            calls.append(kw)
            if len(calls)==1:
                return Response({"role":"assistant","tool_calls":[{"id":"call-1","type":"function","function":{"name":"read_evidence","arguments":json.dumps({"event_id":999 if unauthorized else 17})}}]})
            return Response({"content":json.dumps({"summary":"Observed failure, initiating cause unknown.","evidence_ids":[17]})})
    monkeypatch.setattr("cpe.providers.httpx.Client",Client)
    findings=[{"title":"Example","evidence":[{"event_id":17,"excerpt":"ERROR failure"}]}]
    if unauthorized:
        with pytest.raises(ValueError,match="unauthorized"):
            synthesize(findings)
    else:
        assert "Evidence event IDs: 17" in synthesize(findings)
        assert len(calls)==2
