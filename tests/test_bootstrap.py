"""Offline tests for bootstrap integrity and machine relocation boundaries."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


@unittest.skipUnless(POWERSHELL, "PowerShell is not installed")
class BootstrapTests(unittest.TestCase):
    def ps(self, command):
        bootstrap = str(ROOT / "scripts" / "bootstrap.ps1").replace("'", "''")
        return subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
             f". '{bootstrap}'; {command}"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )

    def test_verified_archive_accepts_correct_hash_and_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "archive.zip"
            archive.write_bytes(b"a checked release archive")
            quoted = str(archive).replace("'", "''")
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            good = self.ps(f"Assert-FileHash '{quoted}' '{expected}'")
            self.assertEqual(good.returncode, 0, good.stderr)
            archive.write_bytes(b"corrupted download")
            bad = self.ps(f"Assert-FileHash '{quoted}' '{expected}'")
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("checksum failed", bad.stderr)

    def test_environment_key_changes_after_relocation_or_machine_change(self):
        result = self.ps(
            "Get-EnvironmentKey 'C:\\a' 'ONE' 'AMD64'; "
            "Get-EnvironmentKey 'D:\\a' 'ONE' 'AMD64'; "
            "Get-EnvironmentKey 'C:\\a' 'TWO' 'AMD64'; "
            "Get-EnvironmentKey 'C:\\a' 'ONE' 'ARM64'; "
            "Get-EnvironmentKey 'C:\\a' 'ONE' 'AMD64'"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        keys = result.stdout.strip().splitlines()
        self.assertEqual(len(keys), 5)
        self.assertEqual(len(set(keys[:4])), 4)
        self.assertEqual(keys[0], keys[4])

    def test_unsupported_architecture_fails_before_download(self):
        result = self.ps("Get-PlatformAsset 'x86'")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unsupported Windows architecture", result.stderr)

    def test_child_command_failure_is_propagated(self):
        executable = str(POWERSHELL).replace("'", "''")
        result = self.ps(f"Invoke-Checked '{executable}' @('-NoProfile', '-Command', 'exit 7')")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exit 7", result.stderr)


if __name__ == "__main__":
    unittest.main()
