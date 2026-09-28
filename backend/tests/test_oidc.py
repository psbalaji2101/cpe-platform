import time
from types import SimpleNamespace
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cpe.config import settings


@pytest.mark.parametrize('verified, audience, expires, expected', [
    (True, 'cpe-test', 300, 200),
    (False, 'cpe-test', 300, 401),
    ('false', 'cpe-test', 300, 401),
    (True, 'wrong-audience', 300, 401),
    (True, 'cpe-test', -300, 401),
])
def test_oidc_signature_and_claim_validation(client, monkeypatch, verified, audience, expires, expected):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(settings, 'oidc_issuer', 'https://identity.example.internal')
    monkeypatch.setattr(settings, 'oidc_audience', 'cpe-test')
    monkeypatch.setattr(settings, 'oidc_jwks_url', 'https://identity.example.internal/keys')
    monkeypatch.setattr(jwt, 'PyJWKClient', lambda *args, **kwargs:
                        SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private.public_key())))
    token = jwt.encode({'sub': 'test-user', 'iss': settings.oidc_issuer, 'aud': audience,
                        'exp': int(time.time()) + expires, 'email': 'admin@cpe.local',
                        'email_verified': verified}, private, algorithm='RS256')
    response = client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == expected
