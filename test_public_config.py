"""Portable public setup must never depend on a developer's private credential module."""
import os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from mcd_transport import credential

class PublicCredentialConfig(unittest.TestCase):
    def test_server_environment_is_supported(self):
        with patch.dict(os.environ,{'MCD_TOKEN':'fixture-only-not-a-live-credential'},clear=True):
            self.assertEqual(credential(),'fixture-only-not-a-live-credential')

    def test_private_file_is_read_and_trimmed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixture.txt';path.write_text('fixture-only\n',encoding='utf-8')
            with patch.dict(os.environ,{'MCD_TOKEN_FILE':str(path)},clear=True):
                self.assertEqual(credential(),'fixture-only')

    def test_missing_config_fails_without_private_module_lookup(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(FileNotFoundError):credential()

if __name__=='__main__':unittest.main()
