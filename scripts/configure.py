"""Generate local deployment credentials without printing secrets."""
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env = root / ".env"
if env.exists():
    if "CPE_RUNTIME_PASSWORD=" not in env.read_text():
        with env.open("a") as f:
            f.write(f"CPE_RUNTIME_PASSWORD={secrets.token_hex(24)}\n")
    print("Existing credentials preserved; runtime credential is configured.")
else:
    password = secrets.token_urlsafe(24)
    env.write_text(f"POSTGRES_PASSWORD={secrets.token_hex(24)}\nCPE_RUNTIME_PASSWORD={secrets.token_hex(24)}\nCPE_ADMIN_EMAIL=admin@cpe.local\nCPE_ADMIN_PASSWORD={password}\nCPE_LLM_PROVIDER=mock\nCPE_PORT=8097\nCPE_ORIGIN=http://localhost:8097\n")
    env.chmod(0o600)
    access = root / "LOCAL_ACCESS.md"
    access.write_text(f"# Local deployment access\n\nURL: http://localhost:8097\n\nEmail: `admin@cpe.local`\n\nPassword: `{password}`\n\nGenerated locally. Keep this file and .env private; neither belongs in source control or an exported project archive.\n")
    access.chmod(0o600)
    print("Generated .env and private LOCAL_ACCESS.md. No credentials printed.")
