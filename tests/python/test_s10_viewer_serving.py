"""Serving policy fails closed without killing or choosing fallback ports."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import pytest

spec = importlib.util.spec_from_file_location('serving', Path(__file__).resolve().parents[2] / 'scripts/serve_s10_viewer.py')
serving = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serving)


def args(root=None):
    return ['python', '-u', '-m', 'http.server', '8765', '--bind', '127.0.0.1', '--directory', str(root or serving.ROOT)]


def test_exact_command():
    assert serving.command_root(args()) == serving.ROOT
    for bad in [args()[:5], ['node'] + args()[1:], [x.replace('8765', '8766') for x in args()], [x.replace('127.0.0.1', '0.0.0.0') for x in args()]]:
        assert serving.command_root(bad) is None


def test_free_and_unknown_listener():
    with patch.object(serving.subprocess, 'check_output', return_value=''):
        assert serving.listener() is None
        with pytest.raises(RuntimeError, match='no listener'):
            serving.verify_http()
    with patch.object(serving.subprocess, 'check_output', return_value='LISTEN 0 5 127.0.0.1:8765 0.0.0.0:*'):
        with pytest.raises(RuntimeError, match='unknown'):
            serving.listener()


@pytest.mark.parametrize('command', [args(serving.ROOT.parent/'viewer_old'), ['node', 'unrelated.js']])
def test_other_listener_is_never_replaced(command):
    with patch.object(serving.subprocess, 'check_output', return_value='LISTEN pid=123'), patch.object(Path, 'read_bytes', return_value=('\0'.join(command)+'\0').encode()):
        with pytest.raises(RuntimeError, match='BLOCKED'):
            serving.listener()


def test_config_mismatch_rejected():
    from io import BytesIO
    with patch.object(serving, 'listener', return_value={'pid': 123}), patch.object(serving, 'urlopen', return_value=BytesIO(b'{}')), patch.object(Path, 'read_bytes', return_value=b'different'):
        with pytest.raises(RuntimeError, match='differs'):
            serving.verify_http()
