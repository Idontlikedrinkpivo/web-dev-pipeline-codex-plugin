"""Progress links must work in Codex's browser even with a system proxy."""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request


SCRIPTS = Path(__file__).resolve().parents[1] / 'dev-pipeline/skills/pipeline/scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


link = load('progress_link')
server = load('progress_server')


class ProgressHTTPTests(unittest.TestCase):
    def run_link(self, folder, base):
        md = folder / 'progress.md'
        md.write_text('# Plan\nСделано: 1 из 4\n', encoding='utf-8')
        output = io.StringIO()
        with patch.object(sys, 'argv', ['progress_link.py', str(md)]), \
             patch.object(link, 'rebuild'), patch.object(link, 'start', return_value=base) as start, \
             contextlib.redirect_stdout(output):
            link.main()
        return output.getvalue(), start

    def test_fresh_codex_stage_starts_http_without_desktop_flag(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            text, start = self.run_link(folder, 'http://127.0.0.1:8791/')
            start.assert_called_once_with(folder.resolve())
            self.assertIn('[progress.html](http://127.0.0.1:8791/progress.html)', text)
            self.assertFalse((folder / '.progress-desktop').exists())

    def test_server_failure_never_emits_blocked_file_link(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(SystemExit, 'no file link emitted'):
                self.run_link(Path(td), None)

    def test_probes_ignore_system_proxy_and_default_global_opener(self):
        requests = []

        def response(handler, req):
            requests.append(req)
            headers = {server.HEADER: '/tmp/progress', server.CODE_HEADER: 'current-code'}
            # Directory HEAD can return 404 and still identify the progress server.
            raise urllib.error.HTTPError(req.full_url, 404, 'no index', headers, None)

        with patch('urllib.request.getproxies', return_value={'http': 'http://proxy.invalid:3128'}), \
             patch.object(urllib.request.HTTPHandler, 'http_open', response), \
             patch('urllib.request.urlopen', side_effect=AssertionError('global opener used')):
            self.assertTrue(server.serves(8791, Path('/tmp/progress')))
            self.assertEqual(server.code_of(8791), 'current-code')
            self.assertFalse(server.serves(8791, Path('/tmp/other-project')))
        self.assertEqual(len(requests), 3)
        self.assertTrue(all(req.host == '127.0.0.1:8791' for req in requests))
        self.assertTrue(all(req.get_method() == 'HEAD' for req in requests))


if __name__ == '__main__':
    unittest.main()
