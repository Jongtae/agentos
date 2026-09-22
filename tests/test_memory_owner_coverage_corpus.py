"""The owner-coverage corpus, encoded rather than described.

``Capabilities.memory_write_refusal`` decides whether the owner's own request
covers the exact value a model proposes to write into canonical Memory.  Two
independent reviews have now found defects in that decision, and the second
one found something worse than a defect: the corpus that established the fix
existed only as prose in a commit message.  Six mutations of the matching
rule -- including a straight revert to the pre-fix form -- survived the entire
994-test suite, because nothing anywhere encoded a single one of the cases.

So this file is the corpus.  Each row is one owner utterance and one value a
model proposed from it, and the expectation is the whole point: an adversarial
row must stay a pending MemoryCandidate, a legitimate row must be accepted.
Adding a matching rule that breaks any row breaks this file.

The two directions have to be tested together.  Refusing everything passes the
adversarial half and is useless; accepting everything passes the legitimate
half and is the defect.  Neither half is evidence on its own.
"""
import unittest

from personal_agent.agent_runtime import _digit_order_ok, memory_words, owner_covers

# Values the owner never said, built to survive a plausible weakening of the
# rule.  Each names the specific approximation it defeats.
ADVERSARIAL = [
    ('계좌번호는 12345678 이야', '12349999', 'a digit run sharing a long prefix'),
    ('카드번호 1234567890 등록해줘', '1234567899', 'a digit run differing in its last place'),
    ('커피값 5000원 냈어', '50000원', 'an amount off by one order of magnitude'),
    ('커피값 5000원 냈어', '5000달러', 'the owner digits under a different currency'),
    ('3월15일에 만나기로 했어', '3월25일', 'a date off by ten days'),
    ('3월15일에 만나기로 했어', '15월3일', 'the owner digits permuted inside one token'),
    ('2026-03-15 회의', '2026-15-03', 'a date whose parts are transposed'),
    ('3월15일 3시에 만나자', '15월3일',
     'digits permuted inside one token where the value-level order rule still '
     'passes - the owner said 3 again later, so only the per-token rule refuses it'),
    ('계좌 110-222-333333 로 보내', '333333-222-110',
     'an account number permuted across tokens - every digit run is the '
     'owner\'s own, so per-token exactness alone accepts it'),
    ('friday is the conference', 'confidential',
     'a different word sharing four leading characters'),
    ('보고서는 report2026 이야', 'report',
     'the owner word with its identifier stripped off'),
    ('회의 일정 잡아줘', '회사', 'a different word sharing one CJK character'),
    ('내 차 car 는 파란색', 'card', 'a longer word riding on a short owner word'),
]

# Values the owner did say, in the forms a model actually returns them: an
# English plural, a Korean conjugation, a reordered phrase, a subset.  A rule
# that refuses these is not safe, it is broken, and the owner pays for it by
# approving their own words by hand.
LEGITIMATE = [
    ('병원 예약은 목요일 오후 3시야', '목요일 오후 3시', 'a phrase lifted verbatim'),
    ('계좌 110-222-333333 로 보내', '110-222-333333', 'the account number in the owner order'),
    ('커피값 5000원 냈어', '5000원', 'an amount with its unit'),
    ('3월15일에 만나기로 했어', '3월15일', 'a date with a particle dropped'),
    ('i prefer an aisle seat', 'aisle seat', 'a subset of the owner words'),
    ('meeting is on monday', 'meetings monday', 'an English plural'),
    ('내 선호를 기억해: 창가 자리', '선호 창가 자리', 'a Korean particle dropped'),
    ('my password manager is bitwarden', 'password manager bitwarden', 'a reordered subset'),
    ('연봉은 1억 2천이야', '1억 2천', 'a figure with its Korean units'),
    ('the conference is friday', 'conference friday', 'the word confidential was tested against'),
]


class OwnerCoverageCorpusTests(unittest.TestCase):
    def test_no_adversarial_value_is_covered(self):
        for owner, value, why in ADVERSARIAL:
            with self.subTest(value=value):
                self.assertFalse(
                    owner_covers(value, memory_words(owner)),
                    f'{value!r} would be written to canonical Memory though the owner '
                    f'said {owner!r}: {why}')

    def test_every_legitimate_value_is_covered(self):
        for owner, value, why in LEGITIMATE:
            with self.subTest(value=value):
                self.assertTrue(
                    owner_covers(value, memory_words(owner)),
                    f'{value!r} would be refused though the owner said {owner!r}: {why}')

    def test_the_corpus_covers_both_directions(self):
        """A corpus of one shape proves nothing; guard against it shrinking."""
        self.assertGreaterEqual(len(ADVERSARIAL), 13)
        self.assertGreaterEqual(len(LEGITIMATE), 10)

    def test_digit_order_is_a_property_of_the_whole_value(self):
        """The narrow rule the permuted-account row depends on, stated directly.

        ``owner_covers`` is set membership over tokens, so without a value-level
        order check every permutation of the owner's own digit runs is covered.
        """
        owner = memory_words('계좌 110-222-333333 로 보내')
        self.assertTrue(owner_covers('110-222-333333', owner))
        self.assertFalse(owner_covers('333333-222-110', owner))
        self.assertFalse(owner_covers('222-110-333333', owner))

    def test_digit_order_is_also_a_property_of_each_token(self):
        """The per-token rule, isolated from the value-level one.

        Both rules refuse a permuted date, so either one alone looks sufficient
        and a mutation of either survives a corpus that only tests the common
        case.  Here the owner repeats ``3`` later in the sentence, which
        satisfies the value-level order check, leaving the per-token digit
        comparison as the only thing standing between the model and a wrong
        date in canonical Memory.
        """
        owner = memory_words('3월15일 3시에 만나자')
        self.assertTrue(_digit_order_ok(memory_words('15월3일'), owner),
                        'precondition: the value-level rule must not mask this')
        self.assertFalse(owner_covers('15월3일', owner))
        self.assertTrue(owner_covers('3월15일', owner))

    def test_short_word_prefix_containment_is_a_recorded_tension(self):
        """A known, deliberate weakness, asserted so it cannot change silently.

        Replacing the four-character shared stem with prefix containment fixed
        `conference` covering `confidential`, and it regressed the other
        direction: a short owner word now covers a longer unrelated one.
        The CJK branch still keeps a near-equal-length guard; the Latin branch
        cannot, because the pairs collide.  `prefer`/`preference` is the
        inflection the rule exists for and `pass`/`password` is an unrelated
        word, and they have the identical 4-to-8-character prefix shape, so no
        length rule separates them.

        The exposure is bounded by ``owner_covers`` requiring *every* word of
        the value, so a value only lands if each of its words rides on a
        shorter owner word.  It is not eliminated.  Both rows below are the
        current behaviour, not the desired one; a future rule must decide them
        together and this test is what will notice.
        """
        wanted = owner_covers('preference', memory_words('i prefer an aisle seat'))
        unwanted = owner_covers('password', memory_words('let me pass on that'))
        self.assertTrue(wanted, 'the inflection the prefix rule exists for')
        self.assertTrue(unwanted, 'the recorded regression - see the docstring')
        self.assertEqual(
            wanted, unwanted,
            'these two have the same shape; a rule that separates them is a '
            'real improvement and should update this test deliberately')

    def test_a_single_digit_run_is_unaffected_by_the_order_rule(self):
        """Ordering cannot refuse a value that has nothing to reorder."""
        self.assertTrue(owner_covers('5000원', memory_words('커피값 5000원 냈어')))
        self.assertTrue(owner_covers('3월15일', memory_words('3월15일에 만나기로 했어')))


if __name__ == '__main__':
    unittest.main()
