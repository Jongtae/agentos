import tempfile
import unittest
from pathlib import Path

from personal_agent.agent_runtime import Capabilities
from personal_agent.quickstart_store import QuickStore


class MemoryContinuityTests(unittest.TestCase):
    def test_explicit_memory_correction_supersedes_previous_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QuickStore(Path(tmp)/'state')
            caps=Capabilities(store,None,{},'','job',lambda *args:None)
            first=caps.execute('save_memory',{'memory_key':'meeting-time','content':'morning'})
            second=caps.execute('save_memory',{'memory_key':'meeting-time','content':'afternoons'})
            self.assertEqual(store.memories()[0]['content'],'afternoons')
            self.assertEqual(second['supersedes'],first['id'])
            self.assertEqual(len(store.memories()),1)

    def test_read_only_specialist_cannot_receive_memory_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            caps=Capabilities(QuickStore(Path(tmp)/'state'),None,{},'','job',lambda *args:None,readonly=True)
            self.assertNotIn('save_memory',{item['function']['name'] for item in caps.definitions()})

    def test_memory_is_visible_and_deletable_through_owner_space(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QuickStore(Path(tmp)/'state'); saved=store.save_memory('meeting-time','afternoons')
            space=store.personal_space()
            self.assertIn(saved['id'], {row['id'] for row in space['memories']})
            self.assertTrue(store.delete_personal_space_item('memories',saved['id'])['deleted'])
            self.assertEqual(store.memories(),[])

    def test_listed_memory_blocks_public_egress_in_same_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QuickStore(Path(tmp)/'state'); caps=Capabilities(store,None,{},'','job',lambda *args:None)
            caps.execute('list_memory',{})
            with self.assertRaisesRegex(ValueError,'공개 검색어'):
                caps.execute('web_search',{'query':'memory content'})


if __name__=='__main__': unittest.main()
