 #!/usr/bin/env python3
"""
Cryptography Performance Test: Digital Signature Benchmarking and Correctness Evaluation
Author: Frederick Fisler
Description: Benchmarks Key Generation, Digital Signing, and Signature Verification
             across RSA-PSS, ECDSA (NIST Curves), and Ed25519 primitives. Includes
             statistical rigor, raw observation preservation, and multi-family
             security correctness tests.
"""

import argparse
import datetime
import json
import math
import platform
import random
import secrets
import statistics
import sys
import time
from typing import Dict, List, Any
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, ed25519, rsa
from cryptography import __version__ as crypto_version

# --- CONFIGURATION CONSTANTS ---
DEFAULT_ITERATIONS = 30
WARMUP_ITERATIONS = 5


def benchmark_operation(func, iterations: int) -> List[float]:
    """Runs a given operation over multiple iterations, returning raw latencies in ms."""
    for _ in range(WARMUP_ITERATIONS):
        func()

    latencies = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        duration = (time.perf_counter() - start) * 1000
        latencies.append(duration)
    return latencies


def compute_stats(latencies: List[float]) -> Dict[str, Any]:
    """Summarize measured latencies and preserve every raw observation."""
    if not latencies:
        raise ValueError("latencies cannot be empty")
    ordered = sorted(latencies)

    def percentile(p: float) -> float:
        position = (len(ordered) - 1) * p
        lower = math.floor(position)
        upper = math.ceil(position)
        weight = position - lower
        return ordered[lower] * (1 - weight) + ordered[upper] * weight

    p25 = percentile(0.25)
    p75 = percentile(0.75)
    return {
        "sample_count": len(ordered),
        "mean_ms": statistics.mean(latencies),
        "median_ms": statistics.median(latencies),
        "stdev_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0.0,
        "min_ms": ordered[0],
        "max_ms": ordered[-1],
        "p25_ms": p25,
        "p75_ms": p75,
        "p95_ms": percentile(0.95),
        "iqr_ms": p75 - p25,
        "raw_latencies_ms": latencies,
    }


def run_rsa_benchmark(key_size: int, iterations: int, payload: bytes) -> Dict[str, Any]:
    gen_latencies = benchmark_operation(
        lambda: rsa.generate_private_key(public_exponent=65537, key_size=key_size),
        iterations
    )
    priv_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    pub_key = priv_key.public_key()

    pub_bytes_pem = pub_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pub_bytes_der = pub_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    pad = padding.PSS(
        mgf=padding.MGF1(hashes.SHA256()),
        salt_length=padding.PSS.MAX_LENGTH,
    )
    signature = priv_key.sign(payload, pad, hashes.SHA256())

    sign_latencies = benchmark_operation(
        lambda: priv_key.sign(payload, pad, hashes.SHA256()),
        iterations
    )

    verify_latencies = benchmark_operation(
        lambda: pub_key.verify(signature, payload, pad, hashes.SHA256()),
        iterations
    )

    return {
        "algorithm": f"RSA-{key_size}",
        "family": "RSA",
        "key_size_pem_bytes": len(pub_bytes_pem),
        "key_size_der_bytes": len(pub_bytes_der),
        "signature_size_bytes": len(signature),
        "gen_stats": compute_stats(gen_latencies),
        "sign_stats": compute_stats(sign_latencies),
        "verify_stats": compute_stats(verify_latencies),
    }


def run_ecdsa_benchmark(name: str, curve: ec.EllipticCurve, iterations: int, payload: bytes) -> Dict[str, Any]:
    gen_latencies = benchmark_operation(
        lambda: ec.generate_private_key(curve),
        iterations
    )
    priv_key = ec.generate_private_key(curve)
    pub_key = priv_key.public_key()

    pub_bytes_pem = pub_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pub_bytes_der = pub_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    signature = priv_key.sign(payload, ec.ECDSA(hashes.SHA256()))

    sign_latencies = benchmark_operation(
        lambda: priv_key.sign(payload, ec.ECDSA(hashes.SHA256())),
        iterations
    )

    verify_latencies = benchmark_operation(
        lambda: pub_key.verify(signature, payload, ec.ECDSA(hashes.SHA256())),
        iterations
    )

    return {
        "algorithm": name,
        "family": "ECC (NIST)",
        "key_size_pem_bytes": len(pub_bytes_pem),
        "key_size_der_bytes": len(pub_bytes_der),
        "signature_size_bytes": len(signature),
        "gen_stats": compute_stats(gen_latencies),
        "sign_stats": compute_stats(sign_latencies),
        "verify_stats": compute_stats(verify_latencies),
    }


def run_ed25519_benchmark(iterations: int, payload: bytes) -> Dict[str, Any]:
    gen_latencies = benchmark_operation(
        lambda: ed25519.Ed25519PrivateKey.generate(),
        iterations
    )
    priv_key = ed25519.Ed25519PrivateKey.generate()
    pub_key = priv_key.public_key()

    pub_bytes_pem = pub_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pub_bytes_der = pub_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    signature = priv_key.sign(payload)

    sign_latencies = benchmark_operation(
        lambda: priv_key.sign(payload),
        iterations
    )

    verify_latencies = benchmark_operation(
        lambda: pub_key.verify(signature, payload),
        iterations
    )

    return {
        "algorithm": "Ed25519",
        "family": "ECC (Edwards)",
        "key_size_pem_bytes": len(pub_bytes_pem),
        "key_size_der_bytes": len(pub_bytes_der),
        "signature_size_bytes": len(signature),
        "gen_stats": compute_stats(gen_latencies),
        "sign_stats": compute_stats(sign_latencies),
        "verify_stats": compute_stats(verify_latencies),
    }


def run_security_correctness_tests():
    """Automated security correctness checks across all algorithm families (RSA, ECDSA, Ed25519)."""
    print("\n[*] Running Multi-Family Security Correctness & Tamper Tests...")

    message = b"Security Audit Test Payload"
    bad_message = b"Tampered Security Audit Payload"
    tests_passed = 0
    total_tests = 12

    # --- 1. RSA-2048 Tests ---
    rsa_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_pub = rsa_priv.public_key()
    rsa_pad = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH)
    rsa_sig = rsa_priv.sign(message, rsa_pad, hashes.SHA256())
    wrong_rsa_pub = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()

    try:
        rsa_pub.verify(rsa_sig, message, rsa_pad, hashes.SHA256())
        print("    [PASS] RSA: Valid signature verified.")
        tests_passed += 1
    except (InvalidSignature, ValueError):
        print("    [FAIL] RSA: Valid signature failed.")

    try:
        rsa_pub.verify(rsa_sig, bad_message, rsa_pad, hashes.SHA256())
        print("    [FAIL] RSA: Tampered message accepted.")
    except (InvalidSignature, ValueError):
        print("    [PASS] RSA: Tampered message rejected.")
        tests_passed += 1

    bad_rsa_sig = bytearray(rsa_sig)
    bad_rsa_sig[0] ^= 0xFF
    try:
        rsa_pub.verify(bytes(bad_rsa_sig), message, rsa_pad, hashes.SHA256())
        print("    [FAIL] RSA: Corrupted signature accepted.")
    except (InvalidSignature, ValueError):
        print("    [PASS] RSA: Corrupted signature rejected.")
        tests_passed += 1

    try:
        wrong_rsa_pub.verify(rsa_sig, message, rsa_pad, hashes.SHA256())
        print("    [FAIL] RSA: Wrong public key accepted.")
    except (InvalidSignature, ValueError):
        print("    [PASS] RSA: Wrong public key rejected.")
        tests_passed += 1

    # --- 2. ECDSA P-256 Tests ---
    ec_priv = ec.generate_private_key(ec.SECP256R1())
    ec_pub = ec_priv.public_key()
    ec_sig = ec_priv.sign(message, ec.ECDSA(hashes.SHA256()))
    wrong_ec_pub = ec.generate_private_key(ec.SECP256R1()).public_key()

    try:
        ec_pub.verify(ec_sig, message, ec.ECDSA(hashes.SHA256()))
        print("    [PASS] ECDSA: Valid signature verified.")
        tests_passed += 1
    except (InvalidSignature, ValueError):
        print("    [FAIL] ECDSA: Valid signature failed.")

    try:
        ec_pub.verify(ec_sig, bad_message, ec.ECDSA(hashes.SHA256()))
        print("    [FAIL] ECDSA: Tampered message accepted.")
    except (InvalidSignature, ValueError):
        print("    [PASS] ECDSA: Tampered message rejected.")
        tests_passed += 1

    bad_ec_sig = bytearray(ec_sig)
    bad_ec_sig[0] ^= 0xFF
    try:
        ec_pub.verify(bytes(bad_ec_sig), message, ec.ECDSA(hashes.SHA256()))
        print("    [FAIL] ECDSA: Corrupted signature accepted.")
    except (InvalidSignature, ValueError):
        print("    [PASS] ECDSA: Corrupted signature rejected.")
        tests_passed += 1

    try:
        wrong_ec_pub.verify(ec_sig, message, ec.ECDSA(hashes.SHA256()))
        print("    [FAIL] ECDSA: Wrong public key accepted.")
    except (InvalidSignature, ValueError):
        print("    [PASS] ECDSA: Wrong public key rejected.")
        tests_passed += 1

    # --- 3. Ed25519 Tests ---
    ed_priv = ed25519.Ed25519PrivateKey.generate()
    ed_pub = ed_priv.public_key()
    ed_sig = ed_priv.sign(message)
    wrong_ed_pub = ed25519.Ed25519PrivateKey.generate().public_key()

    try:
        ed_pub.verify(ed_sig, message)
        print("    [PASS] Ed25519: Valid signature verified.")
        tests_passed += 1
    except (InvalidSignature, ValueError):
        print("    [FAIL] Ed25519: Valid signature failed.")

    try:
        ed_pub.verify(ed_sig, bad_message)
        print("    [FAIL] Ed25519: Tampered message accepted.")
    except (InvalidSignature, ValueError):
        print("    [PASS] Ed25519: Tampered message rejected.")
        tests_passed += 1

    bad_ed_sig = bytearray(ed_sig)
    bad_ed_sig[0] ^= 0xFF
    try:
        ed_pub.verify(bytes(bad_ed_sig), message)
        print("    [FAIL] Ed25519: Corrupted signature accepted.")
    except (InvalidSignature, ValueError):
        print("    [PASS] Ed25519: Corrupted signature rejected.")
        tests_passed += 1

    try:
        wrong_ed_pub.verify(ed_sig, message)
        print("    [FAIL] Ed25519: Wrong public key accepted.")
    except (InvalidSignature, ValueError):
        print("    [PASS] Ed25519: Wrong public key rejected.")
        tests_passed += 1

    print(f"[*] Security Correctness Suite Complete: {tests_passed}/{total_tests} checks passed.\n")
    if tests_passed != total_tests:
        sys.exit(1)


def print_results(results: List[Dict[str, Any]]):
    print("=" * 105)
    print(" CRYPTOGRAPHIC BENCHMARK & PERFORMANCE ANALYSIS RESULTS ")
    print("=" * 105)
    header = f"{'Algorithm':<12} | {'Family':<15} | {'Serialized Public Key':<21} | {'Sig Sz':<8} | {'Gen Med(ms)':<12} | {'Sign Med(ms)':<12} | {'Verify Med(ms)':<14}"
    print(header)
    print("-" * 105)
    for r in results:
        print(
            f"{r['algorithm']:<12} | "
            f"{r['family']:<15} | "
            f"{str(r['key_size_der_bytes']) + ' B':<21} | "
            f"{str(r['signature_size_bytes']) + ' B':<8} | "
            f"{r['gen_stats']['median_ms']:<12.4f} | "
            f"{r['sign_stats']['median_ms']:<12.4f} | "
            f"{r['verify_stats']['median_ms']:<14.4f}"
        )
    print("=" * 105)

    fastest_signer = min(results, key=lambda x: x['sign_stats']['median_ms'])
    smallest_sig = min(results, key=lambda x: x['signature_size_bytes'])

    print("\nMEASURED PERFORMANCE INSIGHTS:")
    print(
        f" - Lowest Signing Latency: {fastest_signer['algorithm']} ({fastest_signer['sign_stats']['median_ms']:.4f} ms median)")
    print(f" - Most Compact Signature: {smallest_sig['algorithm']} ({smallest_sig['signature_size_bytes']} bytes)")
    print(" - Note: Results reflect empirical performance on this specific hardware environment.")
    print("   Compare latency and serialized sizes directly rather than assuming universal applicability.")
    print("=" * 105)


def main():
    parser = argparse.ArgumentParser(
        description="Cryptography Performance Test: Digital Signature Benchmarking and Correctness Evaluation")
    parser.add_argument("-i", "--iterations", type=int, default=DEFAULT_ITERATIONS,
                        help="Number of benchmark iterations (must be >= 1)")
    parser.add_argument("-o", "--output", type=str, help="Export summary results and raw observations to a JSON file")
    parser.add_argument("-m", "--message", type=str, help="Custom message string to sign and verify")
    parser.add_argument("--payload-size", type=int, default=1024,
                        help="Exact byte length for the built-in payload (must be >= 1; ignored with --message)")
    parser.add_argument("--skip-tests", action="store_true", help="Skip automated security correctness checks")
    args = parser.parse_args()

    if args.iterations < 1:
        parser.error("--iterations must be at least 1")
    if args.payload_size < 1:
        parser.error("--payload-size must be at least 1")

    if not args.skip_tests:
        run_security_correctness_tests()

    if args.message is not None:
        if args.message.strip() == "":
            parser.error("--message cannot be empty or whitespace-only")
        sample_payload = args.message.encode("utf-8")
        print(f"[*] Using custom user message for signing: '{args.message}' ({len(sample_payload)} bytes)")
    else:
        payload_pattern = b"Digital signature benchmark payload. "
        sample_payload = (payload_pattern * ((args.payload_size // len(payload_pattern)) + 1))[:args.payload_size]
        print(f"[*] Using default benchmark payload ({len(sample_payload)} bytes)...")

    print(f"[*] Starting benchmark suite across primitives ({args.iterations} trials per test)...")
    results = []

    configurations = [
        (f"RSA-{size}", lambda size=size: run_rsa_benchmark(size, args.iterations, sample_payload))
        for size in [2048, 3072, 4096]
    ]
    configurations.extend([
        (name, lambda name=name, curve=curve: run_ecdsa_benchmark(name, curve, args.iterations, sample_payload))
        for name, curve in [
            ("ECDSA P-256", ec.SECP256R1()),
            ("ECDSA P-384", ec.SECP384R1()),
            ("ECDSA P-521", ec.SECP521R1()),
        ]
    ])
    configurations.append(("Ed25519", lambda: run_ed25519_benchmark(args.iterations, sample_payload)))
    configuration_seed = secrets.randbits(32)
    random.Random(configuration_seed).shuffle(configurations)
    configuration_order = [name for name, _ in configurations]
    for name, run_configuration in configurations:
        print(f" -> Benchmarking {name}...")
        results.append(run_configuration())

    output_package = {
        "metadata": {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "iterations": args.iterations,
            "configuration_seed": configuration_seed,
            "configuration_order": configuration_order,
            "warmup_iterations_per_operation": WARMUP_ITERATIONS,
            "payload_size_bytes": len(sample_payload),
            "environment": {
                "python_version": platform.python_version(),
                "cryptography_version": crypto_version,
                "platform": platform.platform(),
                "processor": platform.processor(),
            }
        },
        "benchmarks": results
    }

    print("\n")
    print_results(results)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(output_package, f, indent=4)
        print(f"\n[+] Empirical evaluation data and metadata successfully exported to '{args.output}'")


if __name__ == "__main__":
    main()
