#!/usr/bin/env python3
"""
Hugging Face model manager (without huggingface_hub dependency).
Downloads or deletes GGUF models, keeping models.ini in sync.

Usage:
    python hf.py download <model_name>
    python hf.py download <user>/<model_name>
    python hf.py download <user>/<model_name> --quantization <quant>
    python hf.py download <model_name> --quantization <quant>
    python hf.py delete <model_dir> [--force]

Examples:
    python hf.py download llama-2-7b-chat
    python hf.py download microsoft/DialoGPT-medium
    python hf.py download llama-2-7b-chat --quantization Q4_K_M
    python hf.py delete llama-2-7b-chat
    python hf.py delete llama-2-7b-chat --force
"""

import argparse
import os
import sys
import time
import re
import select
import pty
import subprocess
import tempfile
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from tqdm import tqdm

HF_TOKEN = os.environ.get("HF_TOKEN")
if not HF_TOKEN:
    print("Warning: HF_TOKEN not set; downloads may be slower or fail for gated repos.")

# Files larger than this are downloaded sequentially with aria2c progress bar.
# Smaller files are downloaded in parallel with tqdm.
LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100 MB

# Where downloaded GGUF models are registered for the llama.cpp setup.
MODELS_INI_PATH = os.path.expanduser("~/dev/models/llama.cpp-setup/models.ini")
# In models.ini, paths use the container mount point /models, which on the host
# maps to this directory (llamacpp.py mounts models_path there). Override with
# the MODELS_ROOT env var if your layout differs.
MODELS_HOST_ROOT = os.path.expanduser(os.environ.get("MODELS_ROOT", "~/data/models/gguf"))
MODELS_MOUNT_POINT = "/models"


def parse_model_path(model_input, default_user="unsloth"):
    """
    Parse model input and return user/model_name format.
    
    Args:
        model_input: Either 'model_name' or 'user/model_name'
        default_user: Default user if none provided
    
    Returns:
        tuple: (user, model_name, full_repo_id)
    """
    if "/" in model_input:
        user, model_name = model_input.split("/", 1)
    else:
        user = default_user
        model_name = model_input
    
    repo_id = f"{user}/{model_name}"
    return user, model_name, repo_id


def list_repo_files(repo_id):
    """
    List all files in a repository.
    
    Args:
        repo_id: Repository ID to list files from
    
    Returns:
        list: List of file paths in the repository
    """
    try:
        url = f"https://huggingface.co/api/models/{repo_id}"
        headers = {}
        if HF_TOKEN:
            headers["Authorization"] = f"Bearer {HF_TOKEN}"
        
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"Error listing files in {repo_id}: HTTP {response.status_code} - {response.text}")
            return []
        
        repo_info = response.json()
        files = []
        for sibling in repo_info.get("siblings", []):
            files.append(sibling.get("rfilename", ""))
        return files
    except Exception as e:
        print(f"Error listing files in {repo_id}: {e}")
        return []


def get_file_sizes(repo_id, files):
    """Fetch file sizes from the Hugging Face API.

    Uses the tree listing API, which reports the true size of LFS-tracked
    files. The model-info endpoint reports `size: null` for LFS files, which
    would otherwise cause every file to be treated as "small".

    Args:
        repo_id: Repository ID
        files: List of filenames

    Returns:
        dict: {filename: size_in_bytes}
    """
    sizes = {}
    wanted = set(files)
    headers = {}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"

    def _parse_entries(entries):
        for entry in entries:
            path = entry.get("path")
            if path in wanted:
                size = entry.get("size")
                if isinstance(size, int):
                    sizes[path] = size

    try:
        # Tree listing API (paginated via cursor in the Link header).
        cursor = None
        while True:
            url = f"https://huggingface.co/api/models/{repo_id}/tree/main"
            if cursor:
                url += f"?cursor={cursor}"
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                break
            entries = response.json()
            if not isinstance(entries, list):
                break
            _parse_entries(entries)

            link = response.headers.get("Link", "")
            nxt = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    m = re.search(r"cursor=([^&>]+)", part)
                    if m:
                        nxt = m.group(1)
            if nxt and nxt != cursor:
                cursor = nxt
            else:
                break
    except Exception:
        pass

    # Fall back to the model-info endpoint for any file still missing a size.
    if len(sizes) < len(wanted):
        try:
            url = f"https://huggingface.co/api/models/{repo_id}"
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                for sibling in response.json().get("siblings", []):
                    filename = sibling.get("rfilename", "")
                    size = sibling.get("size")
                    if filename in wanted and filename not in sizes and isinstance(size, int):
                        sizes[filename] = size
        except Exception:
            pass

    return sizes


def detect_model_format(files):
    """
    Detect the model format based on file extensions.
    
    Args:
        files: List of file paths
    
    Returns:
        str: Model format ('gguf', 'openvino', 'mixed', or 'other')
    """
    has_gguf = any(f.endswith('.gguf') or '.gguf.' in f for f in files)
    has_openvino = any(f.endswith(('.xml', '.bin')) and 'openvino' in f.lower() for f in files)
    has_openvino_ir = any(f.endswith('.xml') for f in files) and any(f.endswith('.bin') for f in files)
    
    if has_openvino or has_openvino_ir:
        if has_gguf:
            return 'mixed'
        return 'openvino'
    elif has_gguf:
        return 'gguf'
    else:
        return 'other'


def categorize_gguf_files(gguf_files):
    """
    Categorize GGUF files into model files and special files (like mmproj).
    
    Args:
        gguf_files: List of .gguf files
    
    Returns:
        tuple: (model_files, special_files)
    """
    model_files = []
    special_files = []
    
    for file in gguf_files:
        # Check if it's a special file that should always be included
        if any(keyword in file.lower() for keyword in ['mmproj', 'vision', 'clip', 'dspark']):
            special_files.append(file)
        else:
            model_files.append(file)
            
    # If all GGUF files were categorized as special (e.g. repo only contains dspark/mmproj files),
    # treat them as model files instead so the user can select/quantize them.
    if not model_files and special_files:
        return special_files, []
    
    return model_files, special_files


def select_smallest_file(repo_id, files):
    """Select the smallest file from a list using Hub metadata."""
    if not files:
        return []
    sizes = get_file_sizes(repo_id, files)
    if sizes:
        smallest = min(sizes.items(), key=lambda kv: kv[1])[0]
        return [smallest]
    return [sorted(files)[0]]


def select_smallest_sharded_group(repo_id, files):
    if not files:
        return []

    shard_re = re.compile(r"^(?P<base>.*?)-\d{5}-of-\d{5}\.gguf$", re.IGNORECASE)
    groups = {}
    for f in files:
        m = shard_re.match(f)
        base = m.group("base") if m else f
        groups.setdefault(base, []).append(f)

    if len(groups) == 1:
        return sorted(next(iter(groups.values())))

    sizes = get_file_sizes(repo_id, files)

    def group_total(gfiles):
        total = 0
        missing = False
        for gf in gfiles:
            if gf in sizes:
                total += sizes[gf]
            else:
                missing = True
        return None if missing else total

    best_base = None
    best_total = None
    for base, gfiles in groups.items():
        total = group_total(gfiles)
        if total is None:
            continue
        if best_total is None or total < best_total:
            best_total = total
            best_base = base

    if best_base is not None:
        return sorted(groups[best_base])

    best_base = sorted(groups.keys())[0]
    return sorted(groups[best_base])


def find_quantized_files(files, quantization):
    """
    Find files that match the quantization pattern.
    
    Args:
        files: List of file paths
        quantization: Quantization type to search for
    
    Returns:
        list: List of matching files
    """
    # Common quantization patterns
    patterns = [
        rf".*{re.escape(quantization)}.*\.gguf$",  # Exact match with .gguf extension
        rf".*{re.escape(quantization.lower())}.*\.gguf$",  # Lowercase match
        rf".*{re.escape(quantization.upper())}.*\.gguf$",  # Uppercase match
        rf".*{re.escape(quantization.replace('_', '-'))}.*\.gguf$",  # Replace underscores with hyphens
        rf".*{re.escape(quantization.replace('-', '_'))}.*\.gguf$",  # Replace hyphens with underscores
    ]
    
    matching_files = []
    for pattern in patterns:
        for file in files:
            if re.match(pattern, file, re.IGNORECASE):
                if file not in matching_files:
                    matching_files.append(file)
    
    return matching_files


def download_specific_files(repo_id, files, local_dir, file_sizes=None):
    """
    Download specific files from a repository in two phases:
    Phase 1: Small files downloaded in parallel with tqdm progress bar.
    Phase 2: Large files downloaded sequentially with aria2c progress bar.

    Args:
        repo_id: Repository ID to download from
        files: List of files to download
        local_dir: Local directory to save files
        file_sizes: Optional dict mapping filename to size in bytes
    """
    if file_sizes is None:
        file_sizes = {}

    if not files:
        print("No files to download.")
        return

    small_files = []
    large_files = []
    for f in files:
        # GGUF files are always model weights (even when sharded into multiple
        # parts), so they must take the large-file path: a failed/missing size
        # lookup or a shard under the threshold must never push them into the
        # parallel small-file downloader.
        if f.endswith(".gguf"):
            large_files.append(f)
            continue
        size = file_sizes.get(f)
        if size is not None and size >= LARGE_FILE_THRESHOLD:
            large_files.append(f)
        else:
            small_files.append(f)

    # Phase 1: Download small files in parallel with tqdm progress
    pbar = None
    if small_files:
        print(f"Downloading {len(small_files)} small file(s) in parallel...")
        try:
            max_workers = min(len(small_files), 4)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(download_file, repo_id, f, local_dir): f for f in small_files}
                pbar = tqdm(as_completed(futures), total=len(small_files),
                            desc="Downloading", unit="file", leave=False)
                for future in pbar:
                    f = futures[future]
                    try:
                        future.result()
                    except Exception as e:
                        pbar.close()
                        print(f"\n✗ Error downloading {f}: {e}")
                        sys.exit(1)
        except Exception as e:
            if pbar is not None:
                pbar.close()
            print(f"✗ Error downloading small files: {e}")
            sys.exit(1)

    # Cleanly close the parallel progress bar so aria2c's own bar has a clean terminal.
    if pbar is not None:
        pbar.close()
    sys.stdout.flush()
    sys.stderr.flush()

    # Phase 2: Download large files sequentially with aria2c progress bar
    if large_files:
        print(f"Downloading {len(large_files)} large file(s) sequentially...")
        # Move to a fresh line so aria2c's carriage-return-based bar renders cleanly.
        sys.stdout.write("\n")
        sys.stdout.flush()
        for f in large_files:
            try:
                print(f"  → {f}")
                download_file(repo_id, f, local_dir, show_progress=True)
            except Exception as e:
                print(f"\n✗ Error downloading {f}: {e}")
                sys.exit(1)

    # Post-processing: register any downloaded GGUF models in models.ini.
    gguf_downloaded = [f for f in files if f.endswith(".gguf") or ".gguf." in f]
    if gguf_downloaded:
        register_gguf_models(local_dir, gguf_downloaded)

    print(f"✓ Successfully downloaded files to {local_dir}")


def download_file(repo_id, filename, local_dir, show_progress=False):
    """Download a single file from Hugging Face using aria2c for multi-connection speed."""
    url = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
    filepath = Path(local_dir) / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)

    options = [
        "--max-connection-per-server=4",
        "--split=4",
        "--min-split-size=1M",
        "--continue=true",
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        "--dir", str(local_dir),
        "--out", filename,
        "--summary-interval=1",
        # Render the live '#' progress bar. _run_aria2c attaches aria2c to a
        # pty with a known size so this bar is shown instead of the verbose
        # 'Download Progress Summary' fallback text.
        "--show-console-readout=true",
    ]
    if not show_progress:
        options += ["--quiet=true", "--console-log-level=error"]
    else:
        # error level keeps the live progress bar but silences the NOTICE
        # chatter ("Downloading N item(s)", netrc warnings, "Download complete").
        options += ["--console-log-level=error"]

    # Pass the auth token via a 0600 temp config file instead of argv, so the
    # secret is not exposed in the process list (`ps`).
    conf_path = None
    cmd = ["aria2c"]
    if HF_TOKEN:
        fd, conf_path = tempfile.mkstemp(prefix=".aria2-", suffix=".conf")
        os.chmod(conf_path, 0o600)
        with os.fdopen(fd, "w") as cf:
            cf.write(f"header=Authorization: Bearer {HF_TOKEN}\n")
        cmd.append(f"--conf-path={conf_path}")

    cmd += options + [url]

    # Large files (GGUF shards) transfer many GiB, so transient failures are
    # common (e.g. "Error decoding the received TLS packet"). Relaunch aria2c on
    # any error; --continue=true makes each retry resume the partial file instead
    # of starting over. The conf file (auth token) is kept across attempts and
    # cleaned up by us after the final attempt.
    max_attempts = 8
    attempt = 0
    result = None
    try:
        while attempt < max_attempts:
            attempt += 1
            is_last = attempt >= max_attempts
            result = _run_aria2c(cmd, show_progress, conf_path,
                                 cleanup_conf=is_last)
            if result == 0:
                break
            if is_last:
                break
            print(f"\n  ↺ aria2c attempt {attempt}/{max_attempts} failed (exit {result}); retrying...")
            sys.stdout.flush()
            # Small backoff so a flapping network/TLS has a moment to recover.
            time.sleep(min(2 ** (attempt - 1), 15))
    finally:
        if conf_path and os.path.exists(conf_path):
            try:
                os.remove(conf_path)
            except OSError:
                pass

    if result != 0:
        raise Exception(f"aria2c failed with exit code {result} after {max_attempts} attempts")


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# Matches aria2c's '#' progress line, e.g.
# "[#413226 13GiB/13GiB(96%) CN:4 DL:109MiB ETA:5s]"
_PROGRESS_RE = re.compile(r"\[#\S+\s+(\S+)/(\S+)\((\d+)%\)\s*(.*)")


def _render_progress(line_bytes):
    """Render a clean single-line progress bar from an aria2c output line.

    Returns True if the line was a progress line (and was rendered).
    """
    line = _ANSI_RE.sub("", line_bytes.decode("utf-8", "replace")).rstrip("\r")
    m = _PROGRESS_RE.search(line)
    if not m:
        return False
    _render_match(m)
    return True


def _render_match(m):
    cur, total, pct, extra = m.group(1), m.group(2), m.group(3), m.group(4).strip().rstrip("]")
    sys.stdout.write(f"\r\033[KDownloading: {pct}%  {cur}/{total}  {extra}")
    sys.stdout.flush()


def _run_aria2c(cmd, show_progress, conf_path=None, cleanup_conf=True):
    """Run aria2c.

    For the progress bar we run aria2c inside a pty (so its output is live and
    unbuffered) and parse its '#' progress line ourselves, rendering a single
    clean progress line. This avoids aria2c's verbose 'Download Progress
    Summary' blocks entirely. All other output (headers, separators, the final
    results table) is suppressed; on failure the relevant error lines are shown.

    The temp config file (holding the auth token) is removed only when
    ``cleanup_conf`` is True; callers that retry on failure should pass
    ``cleanup_conf=False`` on intermediate attempts and clean the file up
    themselves after the final attempt, so the auth token survives across
    retries.
    """
    try:
        if not show_progress:
            # Quiet: inherit fds, no output. Return the integer exit code.
            return subprocess.run(cmd).returncode

        try:
            pid, master = pty.fork()
        except Exception:
            return subprocess.run(cmd)

        if pid == 0:
            try:
                os.execvp(cmd[0], cmd)
            except Exception:
                os._exit(127)

        # Parent: read the pty, render a clean progress bar, collect errors.
        try:
            pending = b""
            showed_progress = False
            errbuf = []
            while True:
                try:
                    r, _, _ = select.select([master], [], [], 0.2)
                except (OSError, ValueError):
                    break
                if r:
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    pending += chunk
                    # Process all complete lines.
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        if _render_progress(line):
                            showed_progress = True
                        elif line.strip():
                            errbuf.append(line.decode("utf-8", "replace").strip())
                            if len(errbuf) > 30:
                                errbuf.pop(0)
                    # Live-bar mode updates in place via \r (no newline): render
                    # the most recent progress match from the buffered text.
                    matches = list(_PROGRESS_RE.finditer(
                        _ANSI_RE.sub("", pending.decode("utf-8", "replace"))))
                    if matches:
                        _render_match(matches[-1])
                        showed_progress = True
                elif os.waitpid(pid, os.WNOHANG)[0] != 0:
                    # Child exited: drain any remaining buffered output.
                    try:
                        while True:
                            chunk = os.read(master, 4096)
                            if not chunk:
                                break
                            pending += chunk
                    except OSError:
                        pass
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        if _render_progress(line):
                            showed_progress = True
                        elif line.strip():
                            errbuf.append(line.decode("utf-8", "replace").strip())
                            if len(errbuf) > 30:
                                errbuf.pop(0)
                    matches = list(_PROGRESS_RE.finditer(
                        _ANSI_RE.sub("", pending.decode("utf-8", "replace"))))
                    if matches:
                        _render_match(matches[-1])
                        showed_progress = True
                    break

            if showed_progress:
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()

            _, status = os.waitpid(pid, 0)
            rc = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
            if rc != 0 and errbuf:
                sys.stdout.write("\n".join(errbuf[-12:]) + "\n")
                sys.stdout.flush()
            return rc
        finally:
            try:
                os.close(master)
            except OSError:
                pass
    finally:
        if cleanup_conf and conf_path and os.path.exists(conf_path):
            os.remove(conf_path)


def _sanitize_section(name):
    """Turn an arbitrary filename into a valid, lowercase INI section key."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
    return s or "model"


# Matches sharded GGUF names like "name-00001-of-00028.gguf". Same shape as
# the regex used in select_smallest_sharded_group().
_SHARD_RE = re.compile(r"^(?P<base>.*?)-(?P<idx>\d{5})-of-\d{5}\.gguf$", re.IGNORECASE)


def _first_shard_only(gguf_files):
    """Collapse each sharded GGUF group to its first shard.

    Files matching `<base>-NNNNN-of-MMMMM.gguf` are grouped by `<base>` and
    only the shard with index 00001 is kept. Non-sharded files and groups that
    do not include the 00001 shard are returned unchanged.
    """
    if not gguf_files:
        return gguf_files

    groups = {}
    for f in gguf_files:
        m = _SHARD_RE.match(f)
        if not m:
            groups.setdefault(("__single__", f), []).append(f)
            continue
        base = m.group("base")
        groups.setdefault(("__shard__", base), []).append((int(m.group("idx")), f))

    out = []
    for key, members in groups.items():
        if key[0] == "__single__":
            out.extend(members)
            continue
        members.sort(key=lambda iv: iv[0])
        first_idx, first_name = members[0]
        if first_idx == 1:
            out.append(first_name)
        else:
            # No 00001 shard present in this group; keep the lowest-indexed
            # shard so the model is still registered.
            out.append(first_name)
    return out


def register_gguf_models(local_dir, gguf_files):
    """Register downloaded GGUF files in llama.cpp-setup/models.ini.

    Each non-mmproj GGUF becomes its own [section]; an mmproj GGUF is attached
    as an `mmproj =` line to the first model section. Paths follow the
    /models/<local_dir>/<file> convention already used throughout models.ini.
    Existing entries pointing at the same model path are left untouched, so
    re-running the download does not create duplicates.
    """
    if not gguf_files:
        return

    model_ggufs, special_ggufs = categorize_gguf_files(gguf_files)
    mmproj_files = [f for f in special_ggufs if "mmproj" in f.lower()]
    model_entries = list(model_ggufs) + [f for f in special_ggufs if "mmproj" not in f.lower()]

    # A sharded model (e.g. base-00001-of-00028.gguf ... -00028-of-00028.gguf) is
    # a single model split across many files. llama.cpp picks the rest of the
    # shards from the same directory when given the first one, so registering
    # every shard as its own [section] in models.ini creates duplicates that
    # point at the same model. Keep only the first shard of each sharded group.
    model_entries = _first_shard_only(model_entries)
    if not model_entries:
        return

    folder = os.path.basename(local_dir)
    ini_path = MODELS_INI_PATH

    existing_sections = set()
    existing_model_paths = set()
    current = None
    if os.path.exists(ini_path):
        with open(ini_path, "r") as fh:
            for line in fh:
                m = re.match(r"^\s*\[([^\]]+)\]\s*$", line)
                if m:
                    current = m.group(1).strip()
                    existing_sections.add(current)
                    continue
                mp = re.match(r"^\s*model\s*=\s*(.+?)\s*$", line)
                if mp and current:
                    existing_model_paths.add(mp.group(1).strip())

    def unique_section(base):
        base = _sanitize_section(base)
        cand = base
        i = 2
        while cand in existing_sections:
            cand = f"{base}_{i}"
            i += 1
        existing_sections.add(cand)
        return cand

    blocks = []
    attached_mmproj = False
    for gf in model_entries:
        path = f"/models/{folder}/{gf}"
        if path in existing_model_paths:
            continue
        sec = unique_section(os.path.splitext(os.path.basename(gf))[0])
        lines = [f"[{sec}]", f"model = {path}"]
        if not attached_mmproj and mmproj_files:
            lines.append(f"mmproj = /models/{folder}/{mmproj_files[0]}")
            attached_mmproj = True
        blocks.append("\n".join(lines))

    if not blocks:
        return

    os.makedirs(os.path.dirname(ini_path), exist_ok=True)
    need_nl = False
    if os.path.exists(ini_path) and os.path.getsize(ini_path) > 0:
        with open(ini_path, "rb") as fb:
            fb.seek(max(0, os.path.getsize(ini_path) - 1))
            if fb.read(1) != b"\n":
                need_nl = True

    content = ("\n" if need_nl else "") + "\n".join(blocks) + "\n"
    with open(ini_path, "a") as fh:
        fh.write(content)
    print(f"✓ Registered {len(blocks)} GGUF model(s) in {ini_path}")

    # Validate the whole file: drop sections whose GGUF is no longer on disk.
    removed = _prune_missing_models(ini_path)
    if removed:
        print(f"✗ Removed {removed} stale model entr{'y' if removed == 1 else 'ies'} "
              f"from {ini_path} (referenced GGUF missing)")


def _resolve_gguf_path(p):
    """Resolve a models.ini path (often /models/...) to an existing host file.

    Tries the literal path, then maps the /models mount point to the host
    models root, and finally to the current working directory (the download
    target when hf.py is run from the models directory).
    """
    if not p:
        return None
    candidates = [p]
    if p == MODELS_MOUNT_POINT or p.startswith(MODELS_MOUNT_POINT + "/"):
        rel = "" if p == MODELS_MOUNT_POINT else p[len(MODELS_MOUNT_POINT) + 1:]
        candidates.append(os.path.join(MODELS_HOST_ROOT, rel))
        candidates.append(os.path.join(os.getcwd(), rel))
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _prune_missing_models(ini_path):
    """Remove models.ini sections whose referenced GGUF files are absent.

    A section is dropped entirely if its `model =` file is missing. A dangling
    `mmproj =` line is removed (keeping the section) when the model is present
    but the mmproj file is gone. Returns the number of removed sections.
    """
    if not os.path.exists(ini_path):
        return 0
    with open(ini_path, "r") as fh:
        lines = fh.readlines()

    preamble = []
    sections = []  # list of (header_line, [body_lines])
    cur_header = None
    cur_body = None
    for line in lines:
        if re.match(r"^\s*\[[^\]]+\]\s*$", line):
            if cur_header is not None:
                sections.append((cur_header, cur_body))
            cur_header = line
            cur_body = []
        elif cur_header is None:
            preamble.append(line)
        else:
            cur_body.append(line)
    if cur_header is not None:
        sections.append((cur_header, cur_body))

    kept = []
    removed = 0
    for header, body in sections:
        model_path = None
        mmproj_paths = []
        for bl in body:
            mp = re.match(r"^\s*model\s*=\s*(.+?)\s*$", bl)
            if mp:
                model_path = mp.group(1).strip()
            mm = re.match(r"^\s*mmproj\s*=\s*(.+?)\s*$", bl)
            if mm:
                mmproj_paths.append(mm.group(1).strip())
        if model_path and not _resolve_gguf_path(model_path):
            removed += 1
            continue
        new_body = body
        if mmproj_paths and not all(_resolve_gguf_path(p) for p in mmproj_paths):
            new_body = [bl for bl in body if not re.match(r"^\s*mmproj\s*=", bl)]
        kept.append((header, new_body))

    rebuilt = "".join(preamble)
    for header, body in kept:
        rebuilt += header.rstrip("\n") + "\n"
        rebuilt += "".join(body)

    if rebuilt != "".join(lines):
        with open(ini_path, "w") as fh:
            fh.write(rebuilt)
    return removed



def _remove_model_sections_by_dir(ini_path, folder):
    """Remove models.ini sections whose model path points to the given folder.

    Removes every [section] whose `model = /models/<folder>/...` entry matches.
    Returns the number of removed sections.
    """
    if not os.path.exists(ini_path):
        return 0
    with open(ini_path, "r") as fh:
        lines = fh.readlines()

    preamble = []
    sections = []
    cur_header = None
    cur_body = None
    for line in lines:
        if re.match(r"^\s*\[[^\]]+\]\s*$", line):
            if cur_header is not None:
                sections.append((cur_header, cur_body))
            cur_header = line
            cur_body = []
        elif cur_header is None:
            preamble.append(line)
        else:
            cur_body.append(line)
    if cur_header is not None:
        sections.append((cur_header, cur_body))

    prefix = f"/models/{folder}/"
    kept = []
    removed = 0
    for header, body in sections:
        model_path = None
        for bl in body:
            mp = re.match(r"^\s*model\s*=\s*(.+?)\s*$", bl)
            if mp:
                model_path = mp.group(1).strip()
                break
        if model_path and model_path.startswith(prefix):
            removed += 1
            continue
        kept.append((header, body))

    rebuilt = "".join(preamble)
    for header, body in kept:
        rebuilt += header.rstrip("\n") + "\n"
        rebuilt += "".join(body)

    if rebuilt != "".join(lines):
        with open(ini_path, "w") as fh:
            fh.write(rebuilt)
    return removed


def check_repo_exists(repo_id):
    """
    Check if a repository exists on Hugging Face.
    
    Args:
        repo_id: Repository ID to check
    
    Returns:
        bool: True if repository exists
    """
    try:
        url = f"https://huggingface.co/api/models/{repo_id}"
        headers = {}
        if HF_TOKEN:
            headers["Authorization"] = f"Bearer {HF_TOKEN}"
        
        response = requests.get(url, headers=headers)
        return response.status_code == 200
    except Exception:
        return False


def download_model(repo_id, local_dir, quantization=None, exclude_quantizations=None, format_type="auto", files=None):
    """
    Download model from Hugging Face Hub.
    
    Args:
        repo_id: Repository ID to download
        local_dir: Local directory to save the model
        quantization: Quantization type to search for (if None, downloads all except excluded)
        exclude_quantizations: List of quantization types to exclude
        format_type: Model format ('auto', 'gguf', 'openvino')
        files: Pre-fetched list of files (optional, will fetch if not provided)
    """
    print(f"Analyzing repository: {repo_id}")
    
    # List all files in the repository (if not already provided)
    if files is None:
        files = list_repo_files(repo_id)
        if not files:
            print(f"✗ Could not list files in repository {repo_id}")
            sys.exit(1)

    file_sizes = get_file_sizes(repo_id, files)

    # Detect model format if auto
    if format_type == "auto":
        detected_format = detect_model_format(files)
        print(f"Detected format: {detected_format}")
    else:
        detected_format = format_type
        print(f"Using specified format: {detected_format}")
    
    # Handle OpenVINO format
    if detected_format == "openvino":
        print(f"OpenVINO format detected - downloading entire repository ({len(files)} files)...")
        try:
            # For OpenVINO, we need to download all files
            # We'll download all non-.gguf files (config, tokenizer, etc.)
            non_gguf_files = [f for f in files if not f.endswith('.gguf')]
            download_specific_files(repo_id, non_gguf_files, local_dir, file_sizes)
            print(f"✓ Successfully downloaded OpenVINO model {repo_id} to {local_dir}")
            return
        except Exception as e:
            print(f"✗ Error downloading {repo_id}: {e}")
            sys.exit(1)
    
    # Handle mixed format (both GGUF and OpenVINO)
    if detected_format == "mixed":
        print("Mixed format detected (both GGUF and OpenVINO files)")
        if format_type == "auto":
            choice = input("Download (g)guf files only, (o)penvino files only, or (a)ll files? [g/o/a]: ").lower()
            if choice == 'o':
                # Filter to OpenVINO files only
                openvino_files = [f for f in files if f.endswith(('.xml', '.bin')) or 'openvino' in f.lower()]
                non_model_files = [f for f in files if not f.endswith(('.gguf', '.xml', '.bin'))]
                files_to_download = non_model_files + openvino_files
                download_specific_files(repo_id, files_to_download, local_dir, file_sizes)
                return
            elif choice == 'a':
                # Download everything - we'll download all files
                download_specific_files(repo_id, files, local_dir, file_sizes)
                print(f"✓ Successfully downloaded all files from {repo_id} to {local_dir}")
                return
            # Default to GGUF processing (choice == 'g' or other)
    
    # Handle GGUF format (original logic)
    # Get all non-gguf files (config, tokenizer, README, etc.)
    # Also include .gguf.* (e.g., .gguf.part1of3) as GGUF files
    is_gguf = lambda f: f.endswith('.gguf') or '.gguf.' in f
    non_gguf_files = [f for f in files if not is_gguf(f)]
    gguf_files = [f for f in files if is_gguf(f)]
    
    # Categorize GGUF files into model files and special files (mmproj, etc.)
    model_gguf_files, special_gguf_files = categorize_gguf_files(gguf_files)

    mmproj_files = [f for f in special_gguf_files if 'mmproj' in f.lower()]
    dspark_files = [f for f in special_gguf_files if 'dspark' in f.lower()]
    other_special_files = [f for f in special_gguf_files if f not in mmproj_files and f not in dspark_files]
    
    if mmproj_files:
        selected_mmproj = select_smallest_file(repo_id, mmproj_files)
    else:
        selected_mmproj = []
        
    if dspark_files:
        selected_dspark = select_smallest_file(repo_id, dspark_files)
    else:
        selected_dspark = []
        
    special_gguf_files = other_special_files + selected_mmproj + selected_dspark
    
    if quantization:
        # Find model files matching the specific quantization
        matching_model_files = find_quantized_files(model_gguf_files, quantization)
        
        if not matching_model_files:
            print(f"✗ No model files found matching quantization '{quantization}'")
            print("Available model files:")
            for file in sorted(model_gguf_files):
                print(f"  - {file}")
            if special_gguf_files:
                print("Special files (always included):")
                for file in sorted(special_gguf_files):
                    print(f"  - {file}")
            sys.exit(1)
        
        if len(matching_model_files) > 1:
            print(f"Multiple model files found matching '{quantization}':")
            for i, file in enumerate(matching_model_files, 1):
                print(f"  {i}. {file}")
            
            try:
                choice = input("Select file number (or press Enter for all): ").strip()
                if choice:
                    idx = int(choice) - 1
                    if 0 <= idx < len(matching_model_files):
                        matching_model_files = [matching_model_files[idx]]
                    else:
                        print("Invalid selection")
                        sys.exit(1)
            except (ValueError, KeyboardInterrupt):
                print("Invalid input or cancelled")
                sys.exit(1)
        
        # Combine all files: non-gguf + special gguf + selected model files
        files_to_download = non_gguf_files + special_gguf_files + matching_model_files
        print(f"Downloading {len(files_to_download)} files:")
        print(f"  - {len(non_gguf_files)} config/support files")
        print(f"  - {len(special_gguf_files)} special files (mmproj, vision, etc.)")
        print(f"  - {len(matching_model_files)} quantized model file(s)")
        
    elif exclude_quantizations:
        # Download all model files except excluded quantizations, plus all special files
        excluded_files = []
        for exclude_quant in exclude_quantizations:
            excluded_files.extend(find_quantized_files(model_gguf_files, exclude_quant))
        
        # Remove duplicates
        excluded_files = list(set(excluded_files))
        included_model_files = [f for f in model_gguf_files if f not in excluded_files]
        
        # Combine all files: non-gguf + special gguf + included model files
        files_to_download = non_gguf_files + special_gguf_files + included_model_files
        print(f"Downloading {len(files_to_download)} files:")
        print(f"  - {len(non_gguf_files)} config/support files")
        print(f"  - {len(special_gguf_files)} special files (mmproj, vision, etc.)")
        print(f"  - {len(included_model_files)} model files (excluding {len(excluded_files)} files)")
        if excluded_files:
            print("Excluded files:")
            for file in sorted(excluded_files):
                print(f"  - {file}")
        
    else:
        # Download entire repository
        print(f"Downloading entire repository ({len(files)} files)...")
        try:
            download_specific_files(repo_id, files, local_dir, file_sizes)
            print(f"✓ Successfully downloaded {repo_id} to {local_dir}")
            return
        except Exception as e:
            print(f"✗ Error downloading {repo_id}: {e}")
            sys.exit(1)
    
    # Download specific files
    download_specific_files(repo_id, files_to_download, local_dir, file_sizes)


def main():
    parser = argparse.ArgumentParser(
        description="Hugging Face model manager (download/delete GGUF models with models.ini sync)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  hf.py download llama-2-7b-chat
  hf.py download microsoft/DialoGPT-medium
  hf.py download llama-2-7b-chat --quantization Q4_K_M
  hf.py download unsloth/llama-2-7b-bnb-4bit --quantization UD-Q8_0
  hf.py download llama-2-7b-chat --exclude-quantization Q2_K --exclude-quantization Q3_K_S
  hf.py download intel/llama-2-7b-chat-int4-ov --format openvino
  hf.py delete llama-2-7b-chat
  hf.py delete llama-2-7b-chat --force"""
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Download subcommand
    download_parser = subparsers.add_parser(
        "download",
        description="Download models from Hugging Face Hub",
        help="Download a model"
    )
    download_parser.add_argument("model", help="Model name or user/model_name to download")
    download_parser.add_argument("--quantization", "-q", default="UD-Q4_K_XL", help="Quantization type (default: UD-Q4_K_XL)")
    download_parser.add_argument("--user", "-u", default="unsloth", help="Default user if not specified in model name (default: unsloth)")
    download_parser.add_argument("--no-quantization", action="store_true", help="Download original model without quantization suffix")
    download_parser.add_argument("--list-files", "-l", action="store_true", help="List all .gguf files in the repository without downloading")
    download_parser.add_argument("--exclude-quantization", "-e", action="append", help="Exclude specific quantization types (can be used multiple times)")
    download_parser.add_argument("--format", "-f", choices=["auto", "gguf", "openvino"], default="auto", help="Model format to download (default: auto-detect)")

    # Delete subcommand
    delete_parser = subparsers.add_parser(
        "delete",
        description="Delete a model directory and clean models.ini",
        help="Delete a model directory and remove its models.ini entries"
    )
    delete_parser.add_argument("model_dir", help="Directory name under ~/data/models/gguf to delete (e.g., llama-2-7b-chat)")
    delete_parser.add_argument("--force", "-f", action="store_true", help="Skip confirmation prompts")

    args = parser.parse_args()

    if args.command == "download":
        # Backward-compat shim: allow old usage "hf.py <model>" without subcommand
        # (Handled by required subparsers, so this is the only path)

        # Parse the model input
        user, model_name, base_repo_id = parse_model_path(args.model, args.user)
        repo_id = base_repo_id

        # Check if repository exists
        if not check_repo_exists(repo_id):
            print(f"✗ Repository {repo_id} not found on Hugging Face Hub")
            sys.exit(1)

        # If user wants to list files, do that and exit
        if args.list_files:
            files = list_repo_files(repo_id)
            detected_format = detect_model_format(files)
            print(f"Repository format: {detected_format}")
            print(f"Total files: {len(files)}")
            gguf_files = [f for f in files if f.endswith('.gguf')]
            openvino_files = [f for f in files if f.endswith(('.xml', '.bin')) and ('openvino' in f.lower() or f.endswith('.xml'))]
            if gguf_files:
                print(f"\nGGUF files ({len(gguf_files)}):")
                for file in sorted(gguf_files):
                    print(f"  - {file}")
            if openvino_files:
                print(f"\nOpenVINO files ({len(openvino_files)}):")
                for file in sorted(openvino_files):
                    print(f"  - {file}")
            if not gguf_files and not openvino_files:
                print("\nNo GGUF or OpenVINO model files found")
                print("Other files:")
                for file in sorted(files[:10]):
                    print(f"  - {file}")
                if len(files) > 10:
                    print(f"  ... and {len(files) - 10} more files")
            sys.exit(0)

        # Detect format early to determine directory naming
        files = list_repo_files(repo_id)
        if args.format == "auto":
            detected_format = detect_model_format(files)
        else:
            detected_format = args.format

        if args.no_quantization:
            quantization = None
            exclude_quantizations = None
            local_dir = model_name
        else:
            quantization = args.quantization if not args.exclude_quantization else None
            exclude_quantizations = args.exclude_quantization
            local_dir = model_name

        if args.format == "openvino" or detected_format == "openvino":
            local_dir = model_name

        if os.path.exists(local_dir):
            response = input(f"Directory '{local_dir}' already exists. Continue? [y/N]: ")
            if response.lower() not in ['y', 'yes']:
                print("Aborted.")
                sys.exit(0)

        Path(local_dir).mkdir(exist_ok=True)
        download_model(repo_id, local_dir, quantization, exclude_quantizations, detected_format, files)

    elif args.command == "delete":
        model_dir_name = args.model_dir.rstrip("/")
        models_host_root = Path(MODELS_HOST_ROOT).expanduser()
        target_path = models_host_root / model_dir_name

        if not target_path.exists():
            print(f"✗ Directory not found: {target_path}")
            sys.exit(1)

        if not args.force:
            response = input(f"Delete directory '{target_path}' and remove models.ini entries? [y/N]: ")
            if response.lower() not in ['y', 'yes']:
                print("Aborted.")
                sys.exit(0)

        # Remove models.ini sections first
        removed_sections = _remove_model_sections_by_dir(MODELS_INI_PATH, model_dir_name)
        if removed_sections:
            print(f"✓ Removed {removed_sections} entr{'y' if removed_sections == 1 else 'ies'} from {MODELS_INI_PATH}")
        else:
            print("No entries found in models.ini for this directory")

        # Delete the directory
        shutil.rmtree(target_path)
        print(f"✓ Deleted directory {target_path}")


if __name__ == "__main__":
    main()