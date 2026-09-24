"""Current Google Drive Picker authority regressions.

The retired MP1 PersonalAssistantOrchestrator had a second, incompatible Drive
read seam. PRESENCE-CONT-01 removes that duplicate router, but the shipped
Picker authority gate remains security-critical and stays in the normal suite.
"""
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from personal_agent.drive_web_oauth import (DRIVE_FILE, DriveWebOAuthError,
                                            DriveWebOAuthHandoff,
                                            EncryptedDriveSecretStore)
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore


PICKER_CHAT_ID = 42
SECRET_BYTES = b'private selected Drive bytes'


class DrivePickerAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(self.temp.name)
        self.transport_calls = []
        encrypted = EncryptedDriveSecretStore(self.store, Fernet.generate_key())
        self.flow = DriveWebOAuthHandoff(
            encrypted, 'web-client',
            'https://connect.example.test/oauth/callback',
            'https://connect.example.test',
            now=lambda: 1000,
        )

    def connect_and_select(self):
        offer = self.flow.begin(PICKER_CHAT_ID)
        state = parse_qs(urlparse(offer['button']['url']).query)['state'][0]
        self.flow.complete(
            {'state': state, 'code': 'short-code'},
            PICKER_CHAT_ID,
            lambda request: {
                'access_token': 'access-secret',
                'refresh_token': 'refresh-secret',
                'scope': DRIVE_FILE,
                'expires_in': 60,
            },
        )
        self.flow.select_files(
            PICKER_CHAT_ID,
            [{'id': 'file-1', 'name': 'plan', 'mime_type': 'text/plain'}],
        )
        self.assertEqual(self.flow.status()['state'], 'connected')

    def transport(self, url, body, headers):
        self.transport_calls.append(url)
        return SECRET_BYTES

    def test_read_selected_refuses_wrong_owner_and_unselected_file(self):
        self.connect_and_select()

        with self.assertRaises(DriveWebOAuthError):
            self.flow.read_selected(PICKER_CHAT_ID + 1, 'file-1', self.transport)
        with self.assertRaises(DriveWebOAuthError):
            self.flow.read_selected(PICKER_CHAT_ID, 'file-2', self.transport)
        self.assertEqual(self.transport_calls, [])

        self.assertEqual(
            self.flow.read_selected(PICKER_CHAT_ID, 'file-1', self.transport),
            SECRET_BYTES,
        )
        self.assertEqual(len(self.transport_calls), 1)

    def test_service_keeps_picker_handoff_without_a_second_assistant_router(self):
        self.connect_and_select()
        service = AgentService(self.store, drive_web_oauth=self.flow)

        self.assertIs(service.drive_web_oauth, self.flow)
        self.assertFalse(hasattr(service, 'assistant_orchestrator'))
        self.assertTrue(self.flow.assert_selected(PICKER_CHAT_ID, 'file-1'))


if __name__ == '__main__':
    unittest.main()
