"""#936: a page's own alert/confirm/prompt during a step."""
import types
import unittest

from personal_agent import browser_session as bs
from personal_agent import browser_worker as bw

WORKER = next(value for value in vars(bw).values() if isinstance(value, type) and hasattr(value, 'js_dialog'))


def worker(step=None, owner_visible=False):
    return types.SimpleNamespace(owner_visible=owner_visible, dialog_step=step)


def answer(state, kind, message):
    return WORKER.js_dialog(state, kind, message)


class PageDialogRule(unittest.TestCase):
    def test_a_confirmation_during_the_ai_step_is_accepted(self):
        state = worker({'approved': False, 'dialogs': []})
        self.assertIs(answer(state, 'confirm', '해당 상품을 삭제하시겠습니까?'), True)
        self.assertIsNone(answer(state, 'alert', '장바구니 상품이 삭제되었습니다'))
        self.assertEqual([row['outcome'] for row in state.dialog_step['dialogs']], ['accepted', 'shown'])

    def test_a_payment_confirmation_needs_an_approved_step(self):
        for message in ('결제하시겠습니까?', '주문을 진행할까요?', 'Proceed to checkout?', '12,000원을 송금합니다. 계속할까요?'):
            state = worker({'approved': False, 'dialogs': []})
            self.assertIs(answer(state, 'confirm', message), False, message)
            self.assertEqual(state.dialog_step['dialogs'][0]['outcome'], 'declined_payment')
        approved = worker({'approved': True, 'dialogs': []})
        self.assertIs(answer(approved, 'confirm', '결제하시겠습니까?'), True)

    def test_nothing_is_confirmed_outside_a_step(self):
        self.assertIs(answer(worker(None), 'confirm', '이 페이지를 떠나시겠습니까?'), False)

    def test_a_prompt_is_dismissed_and_records_are_bounded(self):
        state = worker({'approved': False, 'dialogs': []})
        self.assertIsNone(answer(state, 'prompt', '이름을 입력하세요'))
        for _ in range(10):
            answer(state, 'alert', 'x' * 500)
        self.assertEqual(len(state.dialog_step['dialogs']), bw.DIALOG_RECORDS)
        self.assertTrue(all(len(row['message']) <= bw.DIALOG_TEXT_LIMIT for row in state.dialog_step['dialogs']))


class StepDialogsMediation(unittest.TestCase):
    def test_only_known_shapes_reach_the_model(self):
        rows = bs.step_dialogs({'dialogs': [{'kind': 'confirm', 'message': 'ok?', 'outcome': 'accepted'},
                                            {'kind': 'eval', 'message': 'x', 'outcome': 'accepted'},
                                            {'kind': 'alert', 'message': 'y', 'outcome': 'pwned'}, 'junk']})
        self.assertEqual(rows, [{'kind': 'confirm', 'message': 'ok?', 'outcome': 'accepted'}])
        self.assertEqual(bs.step_dialogs(None), [])

    def test_commit_question(self):
        self.assertTrue(bs.commit_question('결제하시겠습니까?'))
        self.assertFalse(bs.commit_question('해당 상품을 삭제하시겠습니까?'))


if __name__ == '__main__':
    unittest.main()
