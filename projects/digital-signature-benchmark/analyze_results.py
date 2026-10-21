#!/usr/bin/env python3
"""Build clean SVG charts and a Markdown summary from benchmark JSON runs."""

import argparse
import json
import math
import random
import statistics
from pathlib import Path


COLORS = ["#2563eb", "#0f766e", "#d97706", "#7c3aed", "#dc2626", "#0891b2", "#4d7c0f"]
ALGORITHM_ORDER = ["RSA-2048", "RSA-3072", "RSA-4096", "ECDSA P-256", "ECDSA P-384", "ECDSA P-521", "Ed25519"]


def load_results(paths):
    datasets = []
    for path in paths:
        with path.open(encoding="utf-8") as file:
            datasets.append((path.stem, json.load(file)))
    algorithms = ALGORITHM_ORDER
    for path, document in datasets:
        by_algorithm = {row["algorithm"]: row for row in document["benchmarks"]}
        if set(by_algorithm) != set(algorithms):
            raise ValueError(f"Algorithm list in {path} does not match the other run files")
        document["benchmarks"] = [by_algorithm[name] for name in algorithms]
    return datasets


def bootstrap_median_ci(samples, replicates=10000, seed=20261021):
    """Percentile bootstrap CI of the median, resampling independent run medians."""
    if len(samples) < 2:
        return min(samples), max(samples)
    generator = random.Random(seed)
    estimates = sorted(statistics.median(generator.choices(samples, k=len(samples))) for _ in range(replicates))
    return estimates[math.floor(0.025 * replicates)], estimates[math.ceil(0.975 * replicates) - 1]


def svg_chart(title, subtitle, labels, series, output_path, unit="ms"):
    """Render an Excel-inspired horizontal bar chart with labels beyond CI whiskers."""
    width, left, right = 1160, 245, 190
    row_height, top = 60, 155
    chart_width = width - left - right
    highest_ci = max(high for _, values, color, intervals in series for value, (low, high) in zip(values, intervals)) or 1
    label_room = max(len(f"{value:.4g} {unit}") * 7.2 for _, values, color, intervals in series for value in values) + 22
    max_value = highest_ci * chart_width / max(1, chart_width - label_room)
    height = top + len(labels) * row_height + 70
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:Calibri,Arial,sans-serif;fill:#243247}.muted{fill:#607086}.grid{stroke:#d9e2f0;stroke-width:1}.bar{rx:2}</style>',
        f'<text x="42" y="52" font-size="28" font-weight="700">{title}</text>',
        f'<text x="42" y="82" font-size="14" class="muted">{subtitle}</text>',
        f'<rect x="{left}" y="{top - 10}" width="{chart_width}" height="{len(labels) * row_height}" fill="#fbfcfe" stroke="#d9e2f0"/>']
    ticks = 5
    for tick in range(ticks + 1):
        value = max_value * tick / ticks
        x = left + chart_width * tick / ticks
        parts.append(f'<line x1="{x:.1f}" y1="{top - 10}" x2="{x:.1f}" y2="{height - 45}" class="grid"/>')
        parts.append(f'<text x="{x:.1f}" y="{height - 22}" text-anchor="middle" font-size="12" class="muted">{value:.3g}</text>')
    group_height = row_height / max(1, len(series))
    for index, label in enumerate(labels):
        center = top + index * row_height + row_height / 2
        parts.append(f'<text x="{left - 18}" y="{center + 5:.1f}" text-anchor="end" font-size="14" font-weight="600">{label}</text>')
        for series_index, (series_name, values, color, intervals) in enumerate(series):
            value = values[index]
            low, high = intervals[index]
            y = top + index * row_height + series_index * group_height + 6
            bar_height = max(12, group_height - 12)
            bar_width = chart_width * value / max_value
            parts.append(f'<rect x="{left}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" class="bar" fill="{color}"/>')
            low_x = left + chart_width * low / max_value
            high_x = left + chart_width * high / max_value
            mid_y = y + bar_height / 2
            parts.append(f'<line x1="{low_x:.1f}" y1="{mid_y:.1f}" x2="{high_x:.1f}" y2="{mid_y:.1f}" stroke="#0f172a" stroke-width="2"/>')
            parts.append(f'<line x1="{low_x:.1f}" y1="{mid_y - 5:.1f}" x2="{low_x:.1f}" y2="{mid_y + 5:.1f}" stroke="#0f172a" stroke-width="2"/>')
            parts.append(f'<line x1="{high_x:.1f}" y1="{mid_y - 5:.1f}" x2="{high_x:.1f}" y2="{mid_y + 5:.1f}" stroke="#0f172a" stroke-width="2"/>')
            label_x = max(left + bar_width, high_x) + 8
            parts.append(f'<text x="{label_x:.1f}" y="{y + bar_height * .70:.1f}" font-size="12" font-weight="600">{value:.4g} {unit}</text>')
    legend_y = 115
    legend_x = 42
    for name, _, color, _ in series:
        parts.append(f'<rect x="{legend_x}" y="{legend_y - 12}" width="12" height="12" rx="3" fill="{color}"/>')
        parts.append(f'<text x="{legend_x + 19}" y="{legend_y}" font-size="13" class="muted">{name}</text>')
        legend_x += 165
    parts.append(f'<text x="{left + chart_width / 2:.1f}" y="{height - 3}" text-anchor="middle" font-size="12" class="muted">{unit}</text></svg>')
    output_path.write_text("\n".join(parts), encoding="utf-8")


def make_charts(datasets, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    algorithms = [entry["algorithm"] for entry in datasets[0][1]["benchmarks"]]
    def metric(key, field):
        return [statistics.median(doc["benchmarks"][i][key][field] if isinstance(doc["benchmarks"][i][key], dict) else doc["benchmarks"][i][key] for _, doc in datasets) for i in range(len(algorithms))]

    def intervals(key, field):
        result = []
        for i in range(len(algorithms)):
            values = [doc["benchmarks"][i][key][field] if isinstance(doc["benchmarks"][i][key], dict) else doc["benchmarks"][i][key] for _, doc in datasets]
            result.append(bootstrap_median_ci(values))
        return result

    subtitle = f"Median across {len(datasets)} independent runs; black whiskers show 95% bootstrap CI of run medians"
    svg_chart("Signing and verification latency", subtitle, algorithms,
        [("Signing", metric("sign_stats", "median_ms"), "#2563eb", intervals("sign_stats", "median_ms")), ("Verification", metric("verify_stats", "median_ms"), "#0f766e", intervals("verify_stats", "median_ms"))], output_dir / "latency_sign_verify.svg")
    svg_chart("Key generation latency", subtitle, algorithms,
        [("Key generation", metric("gen_stats", "median_ms"), "#7c3aed", intervals("gen_stats", "median_ms"))], output_dir / "latency_key_generation.svg")
    svg_chart("Encoded signature size", f"Median encoded signature size across {len(datasets)} independent run(s); whiskers show 95% bootstrap CI", algorithms,
        [("Signature", metric("signature_size_bytes", ""), "#d97706", intervals("signature_size_bytes", ""))], output_dir / "signature_size.svg", "bytes")
    svg_chart("Serialized public key size", f"Median DER SubjectPublicKeyInfo size across {len(datasets)} independent run(s); whiskers show 95% bootstrap CI", algorithms,
        [("Public key DER", metric("key_size_der_bytes", ""), "#0891b2", intervals("key_size_der_bytes", ""))], output_dir / "public_key_size.svg", "bytes")


def write_summary(datasets, output_path):
    algorithms = [entry["algorithm"] for entry in datasets[0][1]["benchmarks"]]
    lines = ["# Measured results", "", f"Summary of {len(datasets)} independent benchmark run(s). Timing cells show the median of per-run medians with a 95% percentile-bootstrap confidence interval (10,000 resamples of independent run medians; deterministic seed 20261021). With only five runs, intervals are descriptive and should be interpreted cautiously. See the raw JSON files for observations and environment metadata.", "", "| Algorithm | Key generation (ms), median [95% CI] | Signing (ms), median [95% CI] | Verification (ms), median [95% CI] | Signature (B) | Public key DER (B) |", "|---|---:|---:|---:|---:|---:|"]
    for i, algorithm in enumerate(algorithms):
        vals = [doc["benchmarks"][i] for _, doc in datasets]
        def fmt(key):
            samples = [v[key]["median_ms"] for v in vals]
            low, high = bootstrap_median_ci(samples)
            return f"{statistics.median(samples):.4f} [{low:.4f}, {high:.4f}]"
        lines.append(f"| {algorithm} | {fmt('gen_stats')} | {fmt('sign_stats')} | {fmt('verify_stats')} | {statistics.median([v['signature_size_bytes'] for v in vals]):.0f} | {statistics.median([v['key_size_der_bytes'] for v in vals]):.0f} |")
    metadata = datasets[0][1]["metadata"]
    orders = [", ".join(doc["metadata"].get("configuration_order", [])) for _, doc in datasets]
    lines.extend(["", f"Runs: {len(datasets)} · Trials per operation per run: {metadata['iterations']} · Warm-ups: {metadata.get('warmup_iterations_per_operation', 'not recorded')} · Payload: {metadata['payload_size_bytes']} bytes · Python: {metadata['environment']['python_version']} · cryptography: {metadata['environment']['cryptography_version']}", "", "Configuration order was shuffled between runs. Recorded seeds and orders are in each JSON file.", ""])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", nargs="+", type=Path, help="Benchmark JSON files, one per independent run")
    parser.add_argument("--output-dir", type=Path, default=Path("assets"))
    parser.add_argument("--summary", type=Path, default=Path("results/summary.md"))
    args = parser.parse_args()
    datasets = load_results(args.results)
    make_charts(datasets, args.output_dir)
    write_summary(datasets, args.summary)
    print(f"Wrote four charts to {args.output_dir} and summary to {args.summary}.")


if __name__ == "__main__":
    main()
