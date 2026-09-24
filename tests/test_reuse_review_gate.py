import unittest

from scripts.verify_reuse_review import ReuseReviewError, validate_pr_body


def body(section):
    return "## User outcome\n\nAnything\n\n## Existing solutions review (Adopt / Adapt / Build)\n\n" + section + "\n\n## Validation\n"


VALID_ADAPT = """- problem/boundary: OAuth URL construction
- internal repository candidates: shared oauth helper in src/personal_agent/oauth.py
- search evidence (paths/symbols/docs checked): searched oauth, PKCE, authorization_url in src/ and tests/
- standard-library/platform candidates: urllib.parse covers encoding but not the protocol contract
- official SDK/reference/standard candidates: RFC 6749/7636 and provider docs
- mature open-source/framework candidates: oauthlib
- maintenance/security/supply-chain fit: maintained and reviewed
- licence fit: BSD-3-Clause compatible
- runtime/deployment/compatibility fit: pure Python and supported on the current runtime
- decision: `Adapt`
- why rejected candidates are insufficient: internal helper lacks PKCE protocol construction
- AgentOS-owned policy/authority boundary kept outside the dependency: scope and secret policy remain in AgentOS
- N/A reason:
"""


class ReuseReviewGateTests(unittest.TestCase):
    def test_accepts_complete_adapt_review(self):
        validate_pr_body(body(VALID_ADAPT))

    def test_accepts_na_with_concrete_reason(self):
        validate_pr_body(body("""- decision: `N/A`
- N/A reason: bug fix changes one condition and introduces no new component, abstraction, integration, dependency, or framework
"""))

    def test_rejects_na_without_reason(self):
        with self.assertRaisesRegex(ReuseReviewError, "concrete reason"):
            validate_pr_body(body("- decision: `N/A`\n- N/A reason:\n"))

    def test_rejects_missing_internal_search_record(self):
        section = VALID_ADAPT.replace(
            "- internal repository candidates: shared oauth helper in src/personal_agent/oauth.py",
            "- internal repository candidates:",
        )
        with self.assertRaisesRegex(ReuseReviewError, "internal repository candidates"):
            validate_pr_body(body(section))

    def test_rejects_missing_section(self):
        with self.assertRaisesRegex(ReuseReviewError, "missing Existing solutions review"):
            validate_pr_body("## User outcome\n\nNo reuse section")


if __name__ == "__main__":
    unittest.main()
