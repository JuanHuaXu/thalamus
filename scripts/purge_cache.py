#!/usr/bin/env python3
# Thalamus Cache Purge Utility - v1.7
import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from thalamus.providers.relational import SQLiteRelationalProvider

async def main():
    if len(sys.argv) < 2:
        print("Usage: ./scripts/purge_cache.py <agent_id> [query_norm]")
        sys.exit(1)

    agent_id = sys.argv[1]
    query_norm = sys.argv[2] if len(sys.argv) > 2 else None

    rdbms = SQLiteRelationalProvider()
    print(f"📡 Using database: {rdbms.db_path}")
    
    if query_norm:
        print(f"🧹 Surgically purging cache for agent '{agent_id}' and query: '{query_norm}'...")
        await rdbms.delete_cached_context(agent_id, query_norm)
        print("✅ Purge complete.")
    else:
        print(f"🔥 Clearing ALL cached context for agent '{agent_id}'...")
        count = await rdbms.clear_all_cached_context(agent_id)
        print(f"✅ Purged {count} entries.")

if __name__ == "__main__":
    asyncio.run(main())
