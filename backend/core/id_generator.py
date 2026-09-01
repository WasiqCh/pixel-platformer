# backend/core/id_generator.py
import aiosqlite
import re

async def _get_max_num(db: aiosqlite.Connection, query: str, params: tuple = ()) -> int:
    max_num = 0
    async with db.execute(query, params) as cursor:
        async for row in cursor:
            val = row[0]
            match = re.search(r'(\d+)$', str(val))
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
    return max_num

class IDGenerator:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def mint_channel(self) -> str:
        max_num = await _get_max_num(self.db, "SELECT id FROM channels WHERE id LIKE 'CH%'")
        return f"CH{max_num + 1:02d}"

    async def mint_project(self, channel_id: str) -> str:
        # Projects are unique per channel. We look for EP## inside this channel.
        # ID format in DB is "CH01_EP05". We extract the number after "EP".
        query = "SELECT id FROM projects WHERE channel_id = ?"
        max_num = 0
        async with self.db.execute(query, (channel_id,)) as cursor:
            async for row in cursor:
                parts = row[0].split('_')
                if len(parts) == 2 and parts[1].startswith('EP'):
                    try:
                        num = int(parts[1][2:])
                        if num > max_num: max_num = num
                    except ValueError: pass
        return f"EP{max_num + 1:02d}"

    # --- Existing methods below ---
    async def mint_character(self) -> str:
        max_num = await _get_max_num(self.db, "SELECT id FROM characters WHERE id LIKE 'C%'")
        return f"C{max_num + 1:02d}"

    async def mint_rw_or_mt(self, type_prefix: str) -> str:
        query = "SELECT id FROM world_records WHERE id LIKE 'RW%' OR id LIKE 'MT%'"
        max_num = await _get_max_num(self.db, query)
        return f"{type_prefix}{max_num + 1:02d}"

    async def mint_environment(self) -> str:
        max_num = await _get_max_num(self.db, "SELECT id FROM environments WHERE id LIKE 'E%'")
        return f"E{max_num + 1:02d}"

    async def mint_beat(self) -> str:
        max_num = await _get_max_num(self.db, "SELECT id FROM beats WHERE id LIKE 'B%'")
        return f"B{max_num + 1:03d}"

    async def mint_chunk(self) -> str:
        max_num = await _get_max_num(self.db, "SELECT DISTINCT chunk_id FROM beats WHERE chunk_id LIKE 'K%'")
        return f"K{max_num + 1:02d}"

    async def mint_library_asset(self) -> str:
        max_num = await _get_max_num(self.db, "SELECT id FROM library_assets WHERE id LIKE 'LIB%'")
        return f"LIB{max_num + 1:03d}"