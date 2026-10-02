"""Fixed-port listener behavior without binding ports or stopping processes."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import serve_viewer_hub as hub

class HubTests(unittest.TestCase):
    def test_no_listener(self):
        with patch.object(hub.subprocess,'check_output',return_value=''):
            self.assertIsNone(hub.listener())
    def test_correct_hub(self):
        args=['python','-u','-m','http.server','8765','--bind','127.0.0.1','--directory',str(hub.ROOT)]
        with patch.object(hub.subprocess,'check_output',return_value='LISTEN users:(("python",pid=123,fd=3))'),patch.object(Path,'read_bytes',return_value=('\0'.join(args)+'\0').encode()):
            self.assertEqual(hub.listener()['pid'],123)
    def test_other_server_fails_closed(self):
        args=['python','-m','http.server','8765','--bind','127.0.0.1','--directory','/tmp/unrelated']
        with patch.object(hub.subprocess,'check_output',return_value='LISTEN users:(("python",pid=123,fd=3))'),patch.object(Path,'read_bytes',return_value=('\0'.join(args)+'\0').encode()):
            with self.assertRaisesRegex(RuntimeError,'BLOCKED'):
                hub.listener()
    def test_ambiguous_listener(self):
        with patch.object(hub.subprocess,'check_output',return_value='LISTEN unknown'):
            with self.assertRaisesRegex(RuntimeError,'ambiguous'):
                hub.listener()

if __name__=='__main__':unittest.main()
