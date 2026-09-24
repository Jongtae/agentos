import tempfile
import unittest
from personal_agent.capabilities import CapabilityRegistry
from personal_agent.quickstart_store import QuickStore

class CapabilityTests(unittest.TestCase):
 def test_enable_requires_exact_declared_scope(self):
  with tempfile.TemporaryDirectory() as root:
   registry=CapabilityRegistry(QuickStore(root))
   with self.assertRaises(ValueError): registry.transition('builtin-mcp-read','enabled',())
   self.assertEqual(registry.transition('builtin-mcp-read','enabled',('read',))['state'],'enabled')
   self.assertEqual(registry.transition('builtin-mcp-read','paused')['state'],'paused')
   self.assertEqual(registry.transition('builtin-mcp-read','disconnected')['state'],'disconnected')


class RetiredCapabilityMigrationTests(unittest.TestCase):
 def test_retired_a2a_state_is_hidden_revoked_and_archived(self):
  with tempfile.TemporaryDirectory() as root:
   store=QuickStore(root)
   store.put('capability_registry',{
    'compatibility-a2a-peer': {
     'state':'paused','changed_at':2.0,'grant':['delegate'],
     'audit':[
      {'state':'enabled','changed_at':1.0,'approved_scopes':['delegate']},
      {'state':'paused','changed_at':2.0},
     ],
    },
    'builtin-mcp-read': {
     'state':'enabled','changed_at':1.0,'grant':['read'],
     'audit':[{'state':'enabled','changed_at':1.0,'approved_scopes':['read']}],
    },
   })
   registry=CapabilityRegistry(store)
   ids=[item['id'] for item in registry.list()]
   self.assertNotIn('compatibility-a2a-peer',ids)
   saved=store.config('capability_registry')
   self.assertNotIn('compatibility-a2a-peer',saved)
   self.assertEqual(saved['builtin-mcp-read']['state'],'enabled')
   retired=store.config('retired_capability_evidence')
   self.assertEqual(retired['compatibility-a2a-peer']['last_state'],'paused')
   self.assertEqual(retired['compatibility-a2a-peer']['changed_at'],2.0)
   self.assertEqual(retired['compatibility-a2a-peer']['audit'][0]['approved_scopes'],['delegate'])
   self.assertNotIn('grant',retired['compatibility-a2a-peer'])
   before=retired['compatibility-a2a-peer']
   registry.list()
   self.assertEqual(store.config('retired_capability_evidence')['compatibility-a2a-peer'],before)

 def test_unknown_persisted_capability_still_fails_closed(self):
  with tempfile.TemporaryDirectory() as root:
   store=QuickStore(root)
   store.put('capability_registry',{'invented-capability': {'legacy':'row'}})
   with self.assertRaises(ValueError):
    CapabilityRegistry(store).list()
