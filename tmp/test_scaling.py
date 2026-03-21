from fastapi.testclient import TestClient
from thalamus.main import app

client = TestClient(app)

def test_async_ingest():
    # Test non-blocking ingest queue
    payload = {
        "agent_id": "test_agent_async",
        "messages": [
            {"role": "user", "content": "Is this fast?"},
            {"role": "assistant", "content": "Success, exit code 0."}
        ],
        "is_verified": True
    }
    response = client.post("/v1/ingest", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    print("Async Ingest Queue Verified: OK")

def test_dispute_endpoint():
    # Test reject_analogy mapping
    payload = {
        "agent_id": "test_agent_async",
        "node_id": "fake_analogy_id_123"
    }
    response = client.post("/v1/context/dispute", json=payload)
    if response.status_code != 200:
        print("Dispute Error:", response.json())
    assert response.status_code == 200
    assert response.json()["action"] == "DISPUTED"
    print("Reject Analogy / Dispute Endpoint Verified: OK")

if __name__ == "__main__":
    with client:  # triggers lifespan
        test_async_ingest()
        test_dispute_endpoint()
