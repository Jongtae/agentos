#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

python3 - <<'PY'
from pathlib import Path

readme = Path("README.md").read_text(encoding="utf-8")
acceptance = Path("docs/acceptance/docker-runtime-preview.md").read_text(encoding="utf-8")
operations = Path("docs/operations/public-preview-operations.md").read_text(encoding="utf-8")
roadmap = Path("docs/next-roadmap.md").read_text(encoding="utf-8")
tasks = Path("TASKS.md").read_text(encoding="utf-8")

required_readme_terms = [
    "Docker is the easiest way to try the AgentOS runtime today",
    "cp .env.example .env",
    "docker compose up",
    "http://localhost:8787",
    "Docker preview is the default public Product Layer try path",
    "Docker does not prove boot ownership",
    "No required API key for the basic local preview",
    "Docker Product Layer completion gate",
]
for term in required_readme_terms:
    assert term in readme, term

required_acceptance_terms = [
    "Docker is the easiest public way to try the AgentOS runtime today",
    "git clone git@github.com:Jongtae/agentos.git",
    "cp .env.example .env",
    "docker compose up",
    "http://localhost:8787",
    "scripts/smoke_docker_product_layer_completion.sh",
    "does not claim",
    "live OAuth",
    "hardware attestation proof",
]
for term in required_acceptance_terms:
    assert term in acceptance, term

required_operations_terms = [
    "README quickstart",
    "Docker or local runtime",
    "not the product target",
    "boot ownership",
    "unobserved proof",
]
for term in required_operations_terms:
    assert term in operations, term

assert "docker-first-customer-onboarding-proof-epic" in roadmap
assert "P2-97" in roadmap
assert "Docker-first customer onboarding proof epic is closed" in tasks
assert "scripts/smoke_docker_customer_onboarding_quickstart.sh" in tasks
assert "scripts/smoke_docker_onboarding_status_contract.sh" in tasks
assert "/api/onboarding" in acceptance
assert "readiness checklist" in acceptance.lower()
assert "Docker Onboarding Status" in readme
PY

echo "docker customer onboarding quickstart smoke: PASS"
