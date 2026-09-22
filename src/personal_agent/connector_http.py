"""Destination containment for owner-local connector HTTP.

Existing Solutions Review (C15), recorded here because it is the decision
this module encodes.

*Problem*: a connector request carries an owner OAuth bearer token in its
headers. The destination must stay the host the token was minted for, and
that has to hold across redirects -- an allowlist checked only on the URL the
caller named is an allowlist on the first hop.

*Considered*: **Adopt** `requests` / `httpx`, which have mature redirect
handling. Both strip `Authorization` on a cross-host redirect by default,
which is exactly the property wanted. Rejected for now: each is a new runtime
dependency for two call sites that issue GETs and one POST, they bring their
own TLS and connection-pool surface, and the repository already ships
stdlib-based owner-local HTTP in three places that would have to migrate
together to be worth it. Recorded as the obvious Adopt candidate if connector
HTTP grows.

*Considered*: **Adopt** stdlib defaults. Rejected on measured behaviour:
`urllib.request.HTTPRedirectHandler.redirect_request` strips only
`content-length` and `content-type`, and `http_error_302` permits `http`,
`https` and `ftp` targets -- so the default opener carries `Authorization`
verbatim to any host, including a scheme downgrade, for up to ten hops.
Independent review demonstrated an owner Gmail token arriving in cleartext at
a non-allowlisted host from a single allowlisted first hop.

*Decision*: **Adapt** -- stdlib `urllib` behind a narrow AgentOS-owned
redirect guard. The guard re-applies the caller's own destination predicate
to every hop, so containment is a property of the opener rather than of the
one URL the caller happened to check.
"""
from urllib.request import HTTPRedirectHandler, build_opener


def contained_opener(is_permitted):
    """An opener that re-checks the destination on every redirect hop.

    ``is_permitted(url)`` returns True for a destination this credential may
    reach. Refusing a hop returns ``None`` from ``redirect_request``, which
    makes urllib raise the original ``HTTPError`` -- so a refused redirect
    reaches the caller as the status it was, not as a silent success from
    wherever the chain ended.
    """
    if not callable(is_permitted):
        raise ValueError('a destination predicate is required')

    class Contained(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not is_permitted(newurl):
                return None
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    built = build_opener(Contained())
    # Carried so a caller's wiring can be asserted. Without it, a transport
    # that silently fell back to the bare default opener looked identical to
    # a contained one from every test that injected its own.
    built.agentos_destination_guard = is_permitted
    return built
