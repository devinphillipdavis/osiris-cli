#!/usr/bin/env python3
"""
OSIRIS Governed 1,000-Interaction Block Runner (SYS-021)
======================================================
Executes a chunked block of the 1,000-interaction advanced curriculum
using fast O(1) incremental tail verification and Gemini-2.5-Flash burst.
"""

import hashlib
import json
import os
import sys
import time

# Ensure high token limit and cloud burst provider
if "OSIRIS_MODEL_PROVIDER" not in os.environ:
    os.environ["OSIRIS_MODEL_PROVIDER"] = "gemini"
if "OSIRIS_VOICE" not in os.environ:
    os.environ["OSIRIS_VOICE"] = "gemini-2.5-flash"
if "OSIRIS_MENTOR_MAX_TOKENS" not in os.environ:
    os.environ["OSIRIS_MENTOR_MAX_TOKENS"] = "2048"


def load_curriculum(dataset_path):
    if not os.path.exists(dataset_path):
        raise FileNotFoundError(f"Curriculum dataset not found at {dataset_path}")
    with open(dataset_path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_curriculum_block(curriculum_path, block_idx=1, block_size=100, living_home="/home/enki/.osiris/living"):
    curriculum = load_curriculum(curriculum_path)
    total_prompts = len(curriculum)

    start_offset = (block_idx - 1) * block_size
    end_offset = min(start_offset + block_size, total_prompts)
    block_prompts = curriculum[start_offset:end_offset]

    print("=== OSIRIS GOVERNED 1,000-INTERACTION BLOCK RUNNER ===", flush=True)
    print(f"Total Curriculum: {total_prompts} prompts", flush=True)
    print(f"Block Index:      {block_idx} / {(total_prompts + block_size - 1) // block_size}", flush=True)
    print(f"Prompt Range:     {start_offset + 1:04d} to {end_offset:04d} ({len(block_prompts)} prompts)", flush=True)
    print(f"Living Home:      {living_home}", flush=True)

    # Import OSIRIS engine
    from osiris_cli.osiris_repl import get_living
    from osiris_cli.probes import verify_chain, verify_chain_tail

    log_path = os.path.join(living_home, "exchanges.jsonl")

    # Step 0: Pre-flight check (Full Merkle audit)
    pre_chain = verify_chain(log_path)
    print(f"\n[Pre-flight] Ledger entries: {pre_chain['entries']}, Intact: {pre_chain['intact']}, Head: {pre_chain['head']}", flush=True)
    if not pre_chain["intact"]:
        print(f"[FATAL] Pre-flight ledger verification failed: {pre_chain}", flush=True)
        sys.exit(1)

    initial_count = pre_chain["entries"]
    living = get_living()

    start_time = time.time()
    successful = 0

    print("\n[Execution] Starting sequential interactions...\n", flush=True)

    for i, item in enumerate(block_prompts):
        global_idx = start_offset + i + 1
        prompt = item["prompt"]
        domain = item.get("domain_name", item.get("domain_id", "Domain"))
        subtrack = item.get("subtrack", "")

        t0 = time.time()
        print(f"[{global_idx:04d}/{total_prompts:04d}] [{item.get('domain_id')}: {subtrack[:30]}] Prompt: {prompt[:65]}...", flush=True)

        try:
            reply = living.converse(prompt, learnable=True, input_transport="typed")
            dt = time.time() - t0
            char_len = len(reply) if reply else 0
            successful += 1
            print(f"       -> Done in {dt:.1f}s | Reply: {char_len} chars", flush=True)
        except Exception as e:
            print(f"       -> [ERROR] Failed turn {global_idx}: {type(e).__name__}: {e}", flush=True)
            break

        # Fast O(1) tail verification every 10 turns
        if (i + 1) % 10 == 0:
            tail_check = verify_chain_tail(log_path, tail_lines=20)
            print(f"--- [Checkpoint {global_idx:04d}] Tail verified: {tail_check['intact']} | Head: {tail_check['head']} ---", flush=True)
            if not tail_check["intact"]:
                print(f"[FATAL] Ledger integrity violated at prompt {global_idx}!", flush=True)
                break

    total_time = time.time() - start_time
    # Post-flight full Merkle audit
    final_chain = verify_chain(log_path)

    print("\n=== BLOCK EXECUTION COMPLETE ===", flush=True)
    print(f"Total time:       {total_time:.1f}s ({total_time/60:.2f} min)", flush=True)
    print(f"Interactions:     {successful} / {len(block_prompts)}", flush=True)
    print(f"Initial entries:  {initial_count}", flush=True)
    print(f"Final entries:    {final_chain['entries']}", flush=True)
    print(f"Delta exchanges:  {final_chain['entries'] - initial_count}", flush=True)
    print(f"Ledger intact:    {final_chain['intact']}", flush=True)
    print(f"Final tail hash:  {final_chain['head']}", flush=True)
    print(f"Historical forks: {len(final_chain.get('forks', []))}", flush=True)


if __name__ == "__main__":
    c_path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/c/Users/Ron/.gemini/antigravity-cli/brain/033a20bd-a81c-4167-b142-1a12bf3b9da6/scratch/curriculum_1000.json"
    blk = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    sz = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    run_curriculum_block(c_path, block_idx=blk, block_size=sz)
