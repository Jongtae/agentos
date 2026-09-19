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


if __name__=='__main__': unittest.main()
