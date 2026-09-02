# backend/core/sharding.py
from backend.core.llm_client import dispatch

async def sharded_extract(job_type, schema, base_context, script_text, merge_fn,
                          threshold=4000, overlap=300, project_id=None, channel_id=None):
    """Long scripts get split into overlapping shards, extracted, then merged."""
    words = script_text.split()
    if len(words) <= threshold:
        res = await dispatch(job_type, {**base_context, "script": script_text},
                             schema=schema, project_id=project_id, channel_id=channel_id)
        return (res["parsed"], res) if res["ok"] else (None, res)

    step = max(threshold - overlap, 500)
    shards = [" ".join(words[i:i + threshold]) for i in range(0, len(words), step)]
    merged, last = None, None
    for idx, shard in enumerate(shards):
        res = await dispatch(job_type,
                             {**base_context, "script": shard,
                              "shard_note": f"part {idx + 1} of {len(shards)}"},
                             schema=schema, project_id=project_id, channel_id=channel_id)
        last = res
        if res["ok"]:
            merged = res["parsed"] if merged is None else merge_fn(merged, res["parsed"])
    if merged is None:
        return None, last or {"ok": False, "error": "all shards failed"}
    return merged, {"ok": True}