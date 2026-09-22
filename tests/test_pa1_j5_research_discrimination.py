"""J5's discrimination, asserted against the product instead of the fixture.

`EPIC-PA1` J5 requires that AgentOS *"distinguishes observed facts from
unknown price/inventory/fees"*.  The first-use acceptance appeared to prove
that and did not: both of its assertions checked strings the fixture itself
had put in `model_text`, so they would have passed against a product that
echoes whatever the model says.  The module that implements the
discrimination, `research.PublicResearch`, was imported by nothing in `src/`.

Every assertion here is driven from **page content this file controls**,
through the wired `bounded_public_research` routing branch, with no model in
the loop at all -- `Capabilities.execute` is called directly.  A product that
echoed a model could not pass, because there is nothing to echo.
"""
import json
import tempfile
import unittest
from pathlib import Path

from personal_agent.agent_runtime import Capabilities
from personal_agent.providers import ProviderError
from personal_agent.quickstart_store import QuickStore

CFG = {'provider': 'compatible', 'endpoint': 'https://openrouter.ai/api/v1', 'model': 'm'}
SECRET = 'SECRET 급여 연 1억 2천, 계좌 110-222-333333'
LAUNDERED = 'compare noise cancelling headphones for commuting'

#: A page that states a fee and an inventory position in the qualified,
#: adjacent form the extractor is built to recognise.
OBSERVED_PAGE = (
    'Model A noise cancelling headphones. '
    'Shipping fee is 3,000 KRW for all domestic orders. '
    'In stock: 12 units available for immediate dispatch today. '
    'Total payable at checkout is 252,000 KRW including shipping.')

#: The same product, written the way most vendor pages are: the numbers are
#: present but nothing commits to them.
UNKNOWN_PAGE = (
    'Model A noise cancelling headphones. '
    'Battery life is 30 hours in our measured test. '
    'Shipping fees are calculated at checkout and are not shown here. '
    'Availability varies by region and is confirmed after you place the order.')


class Net:
    """Records everything that reached the wire and serves controlled pages."""

    def __init__(self, page=OBSERVED_PAGE, results=None, fail=None):
        self.plans, self.page, self.fail = [], page, fail
        self.results = results if results is not None else [
            {'url': 'https://example.com/a', 'title': 'Model A', 'snippet': 'headphones'}]

    def execute(self, plan):
        self.plans.append(plan)
        if plan['tool'] == 'web_search':
            return {'tool': 'web_search', 'results': self.results, 'retrieved_at': 1}
        if self.fail is not None:
            raise self.fail
        page = self.page(plan['url']) if callable(self.page) else self.page
        return {'tool': 'public_page_read', 'url': plan['url'],
                'content': page, 'retrieved_at': 2}


class ResearchDiscriminationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent))
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')

    def caps(self, net, **kwargs):
        return Capabilities(self.store, None, CFG, '', 'job', lambda *a: None,
                            network=net, **kwargs)

    def research(self, net, mode='product_comparison', query='headphone comparison'):
        return self.caps(net).execute('bounded_public_research',
                                      {'mode': mode, 'query': query})

    # -- the journey ------------------------------------------------------

    def test_it_is_reachable_at_all(self):
        """The whole defect: this module used to be imported by nothing."""
        net = Net()
        result = self.research(net)
        self.assertEqual(result['tool'], 'bounded_public_research')
        self.assertEqual([plan['tool'] for plan in net.plans],
                         ['web_search', 'public_page_read'])

    def test_the_product_classifies_a_qualified_page_as_observed(self):
        result = self.research(Net(OBSERVED_PAGE))
        facts = result['dynamic_facts']
        self.assertEqual(facts['fee']['status'], 'observed')
        self.assertEqual(facts['inventory']['status'], 'observed')
        # The classification carries the evidence it was drawn from, so an
        # owner can check it rather than trust it.
        self.assertTrue(facts['fee']['evidence'])

    def test_the_product_classifies_a_hedged_page_as_unknown(self):
        """The opposing pin. Without it, 'always observed' passes the test above."""
        facts = self.research(Net(UNKNOWN_PAGE))['dynamic_facts']
        for name in ('fee', 'inventory', 'payable_total'):
            with self.subTest(fact=name):
                self.assertEqual(facts[name]['status'], 'unknown')
                self.assertFalse(facts[name]['evidence'])

    def test_the_classification_comes_from_the_page_not_from_a_model(self):
        """No model is involved, so there is nothing for the product to echo.

        This is the assertion the first-use acceptance was missing. Both
        results below come from the same code path with the same query; only
        the page text differs, and the classification follows the page.
        """
        observed = self.research(Net(OBSERVED_PAGE))['dynamic_facts']
        unknown = self.research(Net(UNKNOWN_PAGE))['dynamic_facts']
        self.assertNotEqual(observed['fee']['status'], unknown['fee']['status'])
        self.assertNotEqual(observed['inventory']['status'], unknown['inventory']['status'])

    def test_sources_and_timestamps_are_cited(self):
        result = self.research(Net(OBSERVED_PAGE))
        self.assertEqual(result['sources'], ['https://example.com/a'])
        self.assertTrue(result['evidence'][0]['retrieved_at'])
        self.assertTrue(result['search_retrieved_at'])
        self.assertIn('untrusted', result['brief'].casefold())

    # -- the egress boundary ----------------------------------------------

    def test_private_provenance_closes_public_research(self):
        """The #391 precondition, applied to the destination this PR adds.

        The query shares no token with the private material, so a lexical scan
        of the outgoing text would let it through.
        """
        root = Path(self.temp.name) / 'docs'
        root.mkdir()
        (root / 'pay.txt').write_text(SECRET, encoding='utf-8')
        from personal_agent.quickstart_service import AgentService
        AgentService(self.store).save_roots({'paths': [str(root)]})
        net = Net()
        caps = self.caps(net)
        caps.execute('read_file', {'root_id': caps.roots()[0]['id'], 'path': 'pay.txt'})
        with self.assertRaises(ValueError):
            caps.execute('bounded_public_research',
                         {'mode': 'product_comparison', 'query': LAUNDERED})
        self.assertEqual(net.plans, [], 'nothing may reach the wire')

    def test_a_delegated_private_label_closes_it_too(self):
        net = Net()
        child = self.caps(net, inherited_provenance={'delegated:connected-document'})
        with self.assertRaises(ValueError):
            child.execute('bounded_public_research',
                          {'mode': 'travel_plan', 'query': LAUNDERED})
        self.assertEqual(net.plans, [])

    def test_a_clean_context_may_still_research(self):
        """The opposing pin: refused by provenance, not disabled."""
        net = Net()
        self.research(net)
        self.assertEqual([plan['tool'] for plan in net.plans],
                         ['web_search', 'public_page_read'])

    # -- bounds -----------------------------------------------------------

    def test_only_the_two_declared_modes_are_accepted(self):
        for mode in ('checkout', 'booking', 'account_creation', ''):
            with self.subTest(mode=mode):
                net = Net()
                with self.assertRaises(ValueError):
                    self.research(net, mode=mode)
                self.assertEqual(net.plans, [])

    def test_at_most_three_pages_are_read(self):
        net = Net(results=[{'url': f'https://example.com/{n}', 'title': f'p{n}',
                            'snippet': ''} for n in range(10)])
        self.research(net)
        reads = [plan for plan in net.plans if plan['tool'] == 'public_page_read']
        self.assertEqual(len(reads), 3)

    def test_an_access_controlled_page_is_refused_rather_than_read(self):
        """401/403/paywalled: the reader rejects any non-2xx.

        This is generic non-2xx handling rather than access-control awareness,
        which is the honest description -- see the limitation test below.
        """
        net = Net(fail=ProviderError('공개 페이지가 정상 응답하지 않았습니다.'))
        with self.assertRaises(ValueError) as refused:
            self.research(net)
        self.assertIn('근거를 읽지 못했습니다', str(refused.exception))

    def test_the_research_path_has_no_mutating_http_verb(self):
        """It cannot purchase, book, reserve or sign in, structurally.

        `gmail.py` has the same assertion. Without it, "does not purchase"
        is a sentence in a scope string rather than a property of the code.
        """
        source = (Path(__file__).resolve().parents[1] / 'src' / 'personal_agent'
                  / 'research.py').read_text(encoding='utf-8')
        for verb in ('POST', 'PUT', 'PATCH', 'DELETE'):
            with self.subTest(verb=verb):
                self.assertNotIn(f"'{verb}'", source)
                self.assertNotIn(f'"{verb}"', source)

    def test_the_declared_scope_names_what_it_will_not_do(self):
        scope = self.research(Net())['scope'].casefold()
        for refused in ('login', 'cart', 'booking', 'payment', 'mutation'):
            with self.subTest(refused=refused):
                self.assertIn(refused, scope)

    # -- the measured rate, recorded rather than described -----------------

    #: Ten vendor pages that genuinely state a fee and a stock position, in
    #: the wording real listings use. #391 reported 0/10 with a disclaimer
    #: adjacent to the claim and 5/10 on realistic pages; this is the same
    #: kind of measurement against the wired path, on a corpus stored here so
    #: the number can be re-derived instead of trusted.
    VENDOR_PAGES = (
        'Model A headphones. Shipping fee is 3,000 KRW for all domestic orders. '
        'In stock: 12 units available today.',
        'Sony XM5. Delivery charge 2,500 KRW nationwide. Currently 4 units remain '
        'in our Seoul warehouse.',
        'Bose QC. The shipping cost is 5,000 KRW. Stock status: available, 30 units '
        'ready to ship.',
        'AirPods Max. We charge a flat 3,500 KRW shipping fee. There are 7 units in '
        'stock right now.',
        'Sennheiser. Standard delivery fee of 4,000 KRW applies. In stock and ships '
        'within one business day.',
        'Beats Studio. Shipping is 3,000 KRW per order. Inventory: 25 units on hand.',
        'Anker Q45. A 2,000 KRW handling fee is added. 15 units currently available '
        'for immediate dispatch.',
        'Jabra Elite. Courier fee 4,500 KRW. We have 9 units in stock at this price.',
        'Shure Aonic. Delivery fee is 6,000 KRW to all regions. Stock on hand: 3 units.',
        'Bowers PX7. Shipping fee 3,200 KRW. Available now, 18 units in the warehouse.',
    )

    def measure(self):
        """Observed-count per fact across VENDOR_PAGES, through the wired path."""
        counts = {'fee': 0, 'inventory': 0, 'payable_total': 0}
        for page in self.VENDOR_PAGES:
            facts = self.research(Net(page))['dynamic_facts']
            for name in counts:
                counts[name] += facts[name]['status'] == 'observed'
        return counts

    def test_the_measured_discrimination_rate_is_what_it_is(self):
        """The number, pinned. It is not good, and that is the point of pinning it.

        Measured on the corpus above, through the wired routing branch:

            fee         7/10
            inventory   1/10
            payable     0/10

        The fee extractor recognises "shipping fee is X", "flat X shipping
        fee", "delivery fee of X", "handling fee" and "courier fee", and
        misses "delivery charge", "shipping cost" and "Shipping is X per
        order". **Inventory recognises one phrasing out of ten** -- every
        page above states a real, countable stock position and nine are
        reported as unknown.

        The error runs in the safe direction: the product under-claims rather
        than telling an owner something is in stock when the page did not
        commit to it. But "distinguishes observed from unknown" is, for
        inventory, mostly "says unknown", and that should be visible here
        rather than inferred from a journey matrix.

        Raising recall is deliberately NOT done in the same change as the
        wiring: every point of recall is a chance to classify a hedge as a
        commitment, which is the direction that misleads an owner. Tracked
        separately.
        """
        counts = self.measure()
        self.assertEqual(counts['fee'], 7, 'fee recall moved; update the record')
        self.assertEqual(counts['inventory'], 1, 'inventory recall moved; update the record')
        self.assertEqual(counts['payable_total'], 0,
                         'payable_total recall moved; update the record')

    def test_recall_never_silently_becomes_over_claiming(self):
        """The direction that matters: a hedged page must stay unknown.

        If a future recall improvement starts reading "availability varies"
        or "calculated at checkout" as an observation, this fails -- which is
        the failure worth catching, because it puts a number in front of the
        owner that the page never committed to.
        """
        facts = self.research(Net(UNKNOWN_PAGE))['dynamic_facts']
        self.assertEqual(
            [facts[name]['status'] for name in ('fee', 'inventory', 'payable_total')],
            ['unknown', 'unknown', 'unknown'])

    # -- recorded limitation ----------------------------------------------

    def test_robots_txt_is_not_consulted_and_that_is_recorded(self):
        """A known gap, asserted so it cannot be forgotten or overclaimed.

        Nothing fetches or honours robots.txt, and a soft wall that returns
        200 with a login form is read like any other page. Non-2xx access
        control is refused (above); politeness rules and 200-status walls are
        not handled. Stated here rather than in prose so that implementing it
        forces this test to be updated deliberately.
        """
        source_root = Path(__file__).resolve().parents[1] / 'src' / 'personal_agent'
        joined = ' '.join(path.read_text(encoding='utf-8')
                          for path in source_root.glob('*.py'))
        self.assertNotIn('robots.txt', joined,
                         'robots.txt handling appeared; update this test and '
                         'the J5 evidence entry together')


if __name__ == '__main__':
    unittest.main()
