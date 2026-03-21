import asyncio
from ..core.consolidator import ConsolidationEngine
from ..providers.cognee import CogneeProvider
from ..providers.relational import SQLiteRelationalProvider
from ..core.config import settings

async def main():
    print("[Consolidation Job] Starting nightly pass...")
    cognee = CogneeProvider()
    rdbms = SQLiteRelationalProvider()
    
    # Initialize DB with WAL mode if not already
    rdbms.db_path = "thalamus_rdbms.db" if not settings.sessions_dir else f"{settings.sessions_dir}/thalamus_rdbms.db"
    await rdbms.initialize()
    
    engine = ConsolidationEngine(cognee, rdbms)
    
    # Run against all agents
    # For now, just 'default'
    pruned = await engine.run_consolidation_pass("default")
    print(f"[Consolidation Job] Finished. Pruned/Consolidated {pruned} nodes.")

if __name__ == "__main__":
    asyncio.run(main())
