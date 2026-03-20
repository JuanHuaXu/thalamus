import pytest
from unittest.mock import MagicMock, patch
from thalamus.main import get_context
from thalamus.api.schemas import SearchResult

@pytest.mark.asyncio
async def test_lsa_surgical_success():
    """Test that it finds agent-specific data first."""
    with patch("thalamus.providers.cognee.CogneeProvider.search") as mock_search:
        mock_search.return_value = [SearchResult(path="local_node", snippet="Agent Specific Info", score=1.0)]
        
        # We need to mock rdbms too since get_context calls it
        with patch("thalamus.providers.relational.SQLiteRelationalProvider.get_fact_reputations", return_value={}):
            with patch("thalamus.providers.relational.SQLiteRelationalProvider.get_tool_stats", return_value=[]):
                response = await get_context(q="test query", agent_id="agent1")
                
                assert "<relevant-memories>" in response.context
                assert "Agent Specific Info" in response.context
                assert "<latent-abstraction>" not in response.context
                assert mock_search.call_count == 1
                # Check that it tried surgical first
                assert mock_search.call_args[1]["dataset_name"] == "agent_agent1"

@pytest.mark.asyncio
async def test_lsa_broad_fallback():
    """Test that it falls back to global search if surgical fails."""
    with patch("thalamus.providers.cognee.CogneeProvider.search") as mock_search:
        # 1st call (surgical) returns nothing
        # 2nd call (broad) returns data
        mock_search.side_effect = [
            [], # Surgical
            [SearchResult(path="global_node", snippet="Global Shared Info", score=0.8)] # Broad
        ]
        
        with patch("thalamus.providers.relational.SQLiteRelationalProvider.get_fact_reputations", return_value={}):
            with patch("thalamus.providers.relational.SQLiteRelationalProvider.get_tool_stats", return_value=[]):
                # Unique query to avoid cache hit
                response = await get_context(q="fallback query", agent_id="agent1")
                
                assert "<latent-abstraction>" in response.context
                assert "Global Shared Info" in response.context
                assert mock_search.call_count == 2
                assert response.metadata["lsa_triggered"] is True

@pytest.mark.asyncio
async def test_lsa_analogous_expansion():
    """Test that it mutates query if broad search also fails."""
    with patch("thalamus.providers.cognee.CogneeProvider.search") as mock_search:
        # 1. Surgical -> Fail
        # 2. Broad -> Fail
        # 3. Analogous (Mutated) -> Success
        mock_search.side_effect = [
            [], # Surgical
            [], # Broad
            [SearchResult(path="analog_node", snippet="Version Independent Info", score=0.7)] # Analogous
        ]
        
        with patch("thalamus.providers.relational.SQLiteRelationalProvider.get_fact_reputations", return_value={}):
            with patch("thalamus.providers.relational.SQLiteRelationalProvider.get_tool_stats", return_value=[]):
                # Query with a version number that will be stripped
                response = await get_context(q="Mutation CLI v3.0 commands", agent_id="agent1")
                
                assert "<latent-abstraction>" in response.context
                assert "Version Independent Info" in response.context
                assert mock_search.call_count == 3
                # Verify mutation happened
                last_query = mock_search.call_args_list[2][0][0]
                assert "v3.0" not in last_query
