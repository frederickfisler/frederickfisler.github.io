import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa

import digital_signature_benchmark as benchmark


ROOT = Path(__file__).resolve().parents[1]


class StatisticsTests(unittest.TestCase):
    def test_summary_contains_percentiles_and_raw_samples(self):
        stats = benchmark.compute_stats([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(stats["sample_count"], 4)
        self.assertEqual(stats["median_ms"], 2.5)
        self.assertEqual(stats["p25_ms"], 1.75)
        self.assertEqual(stats["p75_ms"], 3.25)
        self.assertEqual(stats["iqr_ms"], 1.5)
        self.assertEqual(stats["raw_latencies_ms"], [1.0, 2.0, 3.0, 4.0])

    def test_empty_samples_raise_a_clear_error(self):
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            benchmark.compute_stats([])


class SignatureBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.message = b"portfolio correctness test"
        self.changed_message = b"changed portfolio correctness test"

    def cases(self):
        rsa_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        rsa_wrong = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
        rsa_parameters = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH)
        ecdsa_private = ec.generate_private_key(ec.SECP256R1())
        ecdsa_wrong = ec.generate_private_key(ec.SECP256R1()).public_key()
        ed_private = ed25519.Ed25519PrivateKey.generate()
        ed_wrong = ed25519.Ed25519PrivateKey.generate().public_key()
        return [
            ("RSA-PSS", rsa_private, rsa_private.public_key(), rsa_wrong,
             lambda key, msg: key.sign(msg, rsa_parameters, hashes.SHA256()),
             lambda key, sig, msg: key.verify(sig, msg, rsa_parameters, hashes.SHA256())),
            ("ECDSA", ecdsa_private, ecdsa_private.public_key(), ecdsa_wrong,
             lambda key, msg: key.sign(msg, ec.ECDSA(hashes.SHA256())),
             lambda key, sig, msg: key.verify(sig, msg, ec.ECDSA(hashes.SHA256()))),
            ("Ed25519", ed_private, ed_private.public_key(), ed_wrong,
             lambda key, msg: key.sign(msg), lambda key, sig, msg: key.verify(sig, msg)),
        ]

    def test_valid_signature_is_accepted(self):
        for name, private, public, _, sign, verify in self.cases():
            with self.subTest(algorithm=name):
                verify(public, sign(private, self.message), self.message)

    def test_tampered_message_corrupted_signature_and_wrong_key_are_rejected(self):
        for name, private, public, wrong_public, sign, verify in self.cases():
            signature = sign(private, self.message)
            corrupted = bytearray(signature)
            corrupted[0] ^= 1
            for label, key, sig, message in [
                ("changed message", public, signature, self.changed_message),
                ("corrupted signature", public, bytes(corrupted), self.message),
                ("wrong public key", wrong_public, signature, self.message),
            ]:
                with self.subTest(algorithm=name, scenario=label):
                    with self.assertRaises((InvalidSignature, ValueError)):
                        verify(key, sig, message)


class CommandLineTests(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "digital_signature_benchmark.py"), *args], cwd=ROOT, capture_output=True, text=True)

    def test_zero_iterations_are_rejected(self):
        result = self.run_script("--iterations", "0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("at least 1", result.stderr)

    def test_whitespace_message_is_rejected(self):
        result = self.run_script("--message", "   ")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot be empty", result.stderr)

    def test_nonpositive_payload_size_is_rejected(self):
        result = self.run_script("--payload-size", "0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("at least 1", result.stderr)

    def test_json_output_has_all_algorithms_and_required_fields(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "result.json"
            result = self.run_script("--iterations", "1", "--skip-tests", "--output", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            document = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(document["metadata"]["payload_size_bytes"], 1024)
        self.assertEqual(document["metadata"]["warmup_iterations_per_operation"], 5)
        self.assertEqual(set(document["metadata"]["configuration_order"]), {row["algorithm"] for row in document["benchmarks"]})
        self.assertIn("configuration_seed", document["metadata"])
        self.assertEqual(len(document["benchmarks"]), 7)
        for item in document["benchmarks"]:
            self.assertIn("algorithm", item)
            for operation in ("gen_stats", "sign_stats", "verify_stats"):
                self.assertIn("p95_ms", item[operation])
                self.assertEqual(item[operation]["sample_count"], 1)
                self.assertEqual(len(item[operation]["raw_latencies_ms"]), 1)

    def test_custom_payload_size_is_exact(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "small-payload.json"
            result = self.run_script("--iterations", "1", "--skip-tests", "--payload-size", "64", "--output", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            document = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(document["metadata"]["payload_size_bytes"], 64)


if __name__ == "__main__":
    unittest.main()
