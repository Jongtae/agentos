#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from release_identity import build_release_identity_payload, validate_release_identity_payload


def cmd_write(args: argparse.Namespace) -> int:
    payload = build_release_identity_payload(
        artifact_type=args.artifact_type,
        agentos_version=args.agentos_version,
        package_version=args.package_version,
        arch=args.arch,
        output_path=args.output_path,
        sha256sums_path=args.sha256sums_path,
        build_manifest_path=args.build_manifest_path,
        base_image_path=args.base_image_path,
        asset_bundle_path=args.asset_bundle_path,
        asset_manifest_path=args.asset_manifest_path,
        install_root=args.install_root,
        default_workspace=args.default_workspace,
        boot_experience_contract=args.boot_experience_contract,
        iso_default_boot_path=args.iso_default_boot_path,
        iso_fallback_boot_path=args.iso_fallback_boot_path,
        grub_theme_contract=args.grub_theme_contract,
        splash_theme_contract=args.splash_theme_contract,
        base_image_type=args.base_image_type,
        remaster_mode=args.remaster_mode,
        welcome_shell_contract=args.welcome_shell_contract,
        recovery_shell_contract=args.recovery_shell_contract,
        boot_flow_proof_contract=args.boot_flow_proof_contract,
        boot_flow_proof_included=args.boot_flow_proof_included,
        default_boot_target_contract=args.default_boot_target_contract,
        default_boot_target_label=args.default_boot_target_label,
        boot_target_activated=args.boot_target_activated,
        vm_first_screen_evidence_contract=args.vm_first_screen_evidence_contract,
        vm_first_screen_evidence_included=args.vm_first_screen_evidence_included,
        installer_hidden_default_path=args.installer_hidden_default_path,
        ubuntu_installer_masked=args.ubuntu_installer_masked,
        agentos_welcome_assets_staged=args.agentos_welcome_assets_staged,
        agentos_welcome_runtime_observed=args.agentos_welcome_runtime_observed,
        agentos_welcome_owns_first_screen=args.agentos_welcome_owns_first_screen,
        live_guest_agent_bootstrap_staged=args.live_guest_agent_bootstrap_staged,
        live_guest_agent_prestaged=args.live_guest_agent_prestaged,
        live_guest_agent_reachability_path=args.live_guest_agent_reachability_path,
        bundled_local_provider_staged=args.bundled_local_provider_staged,
        bundled_local_model_staged=args.bundled_local_model_staged,
        bundled_local_service_staged=args.bundled_local_service_staged,
        bundled_local_firstrun_service_staged=args.bundled_local_firstrun_service_staged,
    )
    errors = validate_release_identity_payload(payload)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    errors = validate_release_identity_payload(payload)
    result = {
        "ok": not errors,
        "errors": errors,
        "input": args.input,
        "artifact_type": payload.get("artifact_type", ""),
        "schema_version": payload.get("schema_version", ""),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=True))
    else:
        if result["ok"]:
            print("release identity manifest: PASS")
        else:
            print("release identity manifest: FAIL")
            for error in errors:
                print(f"- {error}")
    return 0 if result["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write or validate AgentOS release identity manifests")
    subparsers = parser.add_subparsers(dest="command", required=True)

    write_parser = subparsers.add_parser("write", help="Write a release identity manifest")
    write_parser.add_argument("--output", required=True)
    write_parser.add_argument("--artifact-type", required=True, choices=("iso", "deb"))
    write_parser.add_argument("--agentos-version", required=True)
    write_parser.add_argument("--package-version", default="")
    write_parser.add_argument("--arch", default="amd64")
    write_parser.add_argument("--output-path", required=True)
    write_parser.add_argument("--sha256sums-path", required=True)
    write_parser.add_argument("--build-manifest-path", default="")
    write_parser.add_argument("--base-image-path", default="")
    write_parser.add_argument("--asset-bundle-path", default="")
    write_parser.add_argument("--asset-manifest-path", default="")
    write_parser.add_argument("--install-root", default="")
    write_parser.add_argument("--default-workspace", default="")
    write_parser.add_argument("--boot-experience-contract", default="agentos_direct_ai_boot")
    write_parser.add_argument("--iso-default-boot-path", default="continue_to_agentos_default_path")
    write_parser.add_argument("--iso-fallback-boot-path", default="installer_heavy_compatibility")
    write_parser.add_argument("--grub-theme-contract", default="agentos_minimal_appliance_grub.v1")
    write_parser.add_argument("--splash-theme-contract", default="agentos_minimal_appliance_splash.v1")
    write_parser.add_argument("--base-image-type", default="desktop-live-iso")
    write_parser.add_argument("--remaster-mode", default="required_for_product_path")
    write_parser.add_argument("--welcome-shell-contract", default="agentos_welcome_shell.v1")
    write_parser.add_argument("--recovery-shell-contract", default="agentos_recovery_shell.v1")
    write_parser.add_argument("--boot-flow-proof-contract", default="agentos-remastered-boot-flow-proof.v1")
    write_parser.add_argument("--boot-flow-proof-included", action="store_true")
    write_parser.add_argument("--default-boot-target-contract", default="agentos_continue_boot_target.v1")
    write_parser.add_argument("--default-boot-target-label", default="Continue to AgentOS")
    write_parser.add_argument("--boot-target-activated", action="store_true")
    write_parser.add_argument("--vm-first-screen-evidence-contract", default="agentos_vm_first_screen_evidence.v1")
    write_parser.add_argument("--vm-first-screen-evidence-included", action="store_true")
    write_parser.add_argument("--installer-hidden-default-path", action="store_true")
    write_parser.add_argument("--ubuntu-installer-masked", action="store_true")
    write_parser.add_argument("--agentos-welcome-assets-staged", action="store_true")
    write_parser.add_argument("--agentos-welcome-runtime-observed", action="store_true")
    write_parser.add_argument("--agentos-welcome-owns-first-screen", action="store_true")
    write_parser.add_argument("--live-guest-agent-bootstrap-staged", action="store_true")
    write_parser.add_argument("--live-guest-agent-prestaged", action="store_true")
    write_parser.add_argument("--bundled-local-provider-staged", action="store_true")
    write_parser.add_argument("--bundled-local-model-staged", action="store_true")
    write_parser.add_argument("--bundled-local-service-staged", action="store_true")
    write_parser.add_argument("--bundled-local-firstrun-service-staged", action="store_true")
    write_parser.add_argument(
        "--live-guest-agent-reachability-path",
        default="unstaged",
        choices=("prestaged", "runtime_apt_install", "unstaged"),
    )
    write_parser.set_defaults(func=cmd_write)

    validate_parser = subparsers.add_parser("validate", help="Validate a release identity manifest")
    validate_parser.add_argument("--input", required=True)
    validate_parser.add_argument("--json", action="store_true")
    validate_parser.set_defaults(func=cmd_validate)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
