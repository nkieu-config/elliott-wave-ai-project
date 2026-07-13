from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

from analyst.theory.chunker import Chunk, chunk_theory_file, enrich_aliases
from analyst.theory.embedder import Embedder

DEFAULT_THEORY = Path(__file__).resolve().parent / "corpus" / "elliott_wave_theory_en.md"
DEFAULT_OUT = Path(__file__).resolve().parent / "data"

META_NAME = "corpus_meta.json"


def corpus_fingerprint(chunks: list[Chunk]) -> str:
    # Hash of the exact text the embeddings encode. Lets the corpus test catch a
    # stale regen (source edited, .npy not rebuilt) instead of drifting silently.
    h = hashlib.sha256()
    for c in chunks:
        h.update(f"{c.page}\n{c.body}".encode())
        h.update(b"\x00")
    return h.hexdigest()


def build_embeddings(
    theory_path: Path,
    out_dir: Path,
    embedder=None,
) -> None:
    chunks = enrich_aliases(chunk_theory_file(theory_path))
    if not chunks:
        raise RuntimeError(f"No chunks found in {theory_path}")

    if embedder is None:
        embedder = Embedder()

    texts = [c.body for c in chunks]
    vecs = embedder.encode(texts)

    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "text_sha256": corpus_fingerprint(chunks),
        "count": len(chunks),
        "embed_dim": int(vecs.shape[1]),
        "model_name": getattr(embedder, "model_name", None),
        "revision": getattr(embedder, "revision", None),
    }
    # Temp-write then rename so no single file is left half-written (a crash
    # between the three renames is caught by the corpus fingerprint test).
    # Temp ends in .npy so np.save doesn't append a suffix.
    chunks_tmp = out_dir / "chunks.jsonl.tmp"
    embed_tmp = out_dir / "embeddings.tmp.npy"
    meta_tmp = out_dir / (META_NAME + ".tmp")
    with chunks_tmp.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    np.save(embed_tmp, vecs)
    meta_tmp.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    embed_tmp.replace(out_dir / "embeddings.npy")
    chunks_tmp.replace(out_dir / "chunks.jsonl")
    meta_tmp.replace(out_dir / META_NAME)
    print(
        f"Wrote {len(chunks)} chunks + embeddings (shape={vecs.shape}, "
        f"model={getattr(embedder, 'model_name', '?')}) to {out_dir}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    build_embeddings(theory_path=DEFAULT_THEORY, out_dir=DEFAULT_OUT)
