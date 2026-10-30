import unittest
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'aveniq' / 'app'))
import server

class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / 'settings.json'
        self.patch_file = patch.object(server, 'PREFS_FILE', self.file)
        self.patch_dir = patch.object(server, 'DATA_DIR', Path(self.tmp.name))
        self.patch_file.start()
        self.patch_dir.start()

    def tearDown(self):
        self.patch_file.stop()
        self.patch_dir.stop()
        self.tmp.cleanup()

    def test_roundtrip_shared_settings(self):
        config = {'theme':'dark', 'compact':True,
                  'rooms':{'Salotto':['light.salotto','climate.netatmo_smart_thermostat']},
                  'widgets':[{'type':'proxmox','title':'Proxmox','entity':'sensor.node_proxmox_cpu_usata'}]}
        server.save_prefs(config)
        self.assertEqual(server.read_prefs(), config)
        self.assertTrue(self.file.exists())

    def test_reject_invalid_entity_id(self):
        with self.assertRaises(ValueError):
            server.save_prefs({'rooms':{'Salotto':['../etc/passwd']},'widgets':[]})

    def test_reject_unapproved_widget(self):
        with self.assertRaises(ValueError):
            server.save_prefs({'rooms':{},'widgets':[{'type':'shell','title':'Bad','entity':'sensor.test'}]})

    def test_invalid_json_load_fallback(self):
        self.file.write_text('bad json')
        self.assertEqual(server.read_prefs()['theme'], 'light')

    def test_no_credential_field(self):
        with self.assertRaises(ValueError):
            server.save_prefs({'rooms':{},'widgets':[], 'SUPERVISOR_TOKEN':'secret'})

if __name__ == '__main__':
    unittest.main()
