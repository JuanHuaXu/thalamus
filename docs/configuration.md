# Configuration Reference: Thalamus

The Thalamus middleware is configured via `config.json`. This file governs how the system interacts with LLMs, the Cognee graph, and the local reputation database.

## Configuration Keys

### Networking & API
| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `host` | `string` | `"0.0.0.0"` | Host to bind the middleware to. |
| `port` | `int` | `8080` | Port to bind the middleware to. |
| `api_key` | `string` | `null` | Optional Thalamus API key for Bearer Auth. |
| `cache_ttl_seconds` | `int` | `300` | TTL for both L1 (Memory) and L2 (Persistent) caches. |

### Cognee Backend
| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `cognee_api_url` | `string` | `"http://localhost:8000"` | URL of the running Cognee instance. |
| `cognee_api_key` | `string` | `null` | Optional Cognee API key. |

### Evolutionary Hub (Scaling)
| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `verified_dispute_threshold` | `int` | `5` | Failures before a 'verified' fact is hidden. |
| `unverified_dispute_threshold` | `int` | `2` | Failures before an 'unverified' fact is hidden. |
| `initial_dynamic_threshold` | `int` | `5` | Starting penalty threshold for node decay. |
| `ingestion_queue_max_size` | `int` | `1000` | Max entries in the background processing queue. |

### LLM & Synthesis
| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `llm_provider_url` | `string` | `null` | URL for Ollama or OpenAI compatible provider. |
| `llm_model_name` | `string` | `"llama3:8b"` | Model name to use for synthesis. |
| `llm_auto_pull` | `bool` | `true` | Automatically pull missing Ollama models. |
| `consolidation_cluster_size` | `int` | `5` | Number of nodes to merge in a synthesis pass. |

### Crawler (Seeding)
| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `crawler_timeout` | `float` | `60.0` | Timeout in seconds (per attempt). |
| `crawler_user_agent` | `string` | `"Mozilla/5.0 ... Chrome/121.0.0.0 Safari/537.36"` | Masquerade as a modern browser to bypass WAF. |
| `http1_only` | `bool` | `true` | (Internal) Fixed to true to bypass buggy H2 stacks. |

## Reloading Config
Any changes to `config.json` require a restart of the Thalamus middleware process to take effect.
