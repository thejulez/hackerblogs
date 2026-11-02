"""Phase 00: download the open-index/hacker-news monthly Parquet files (ODC-BY)."""

from common import HF_REPO, RAW, args, log
from huggingface_hub import snapshot_download

a = args("download HN dump")
lg = log("p00")

pattern = f"data/{a.sample[:4]}/{a.sample}.parquet" if a.sample else "data/**/*.parquet"
lg.info("downloading %s %s -> %s", HF_REPO, pattern, RAW)
snapshot_download(
    repo_id=HF_REPO,
    repo_type="dataset",
    allow_patterns=[pattern],
    local_dir=RAW,
    max_workers=16,
)
n = len(list((RAW / "data").rglob("*.parquet")))
lg.info("done, %d monthly files on disk", n)
