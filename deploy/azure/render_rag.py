"""Renders a knowledge-service Container App definition (role: api or worker).

    python3 render_rag.py api|worker

Both roles run the same image. The API has internal ingress only (the CRM and the voice agent call
it inside the environment); the worker has none. Both mount the same Azure Files share for
uploaded source files, which the API writes and the worker reads. The API applies the database
migrations before it starts, so a fresh database needs no separate step.
"""

from __future__ import annotations

import json
import os
import sys

SECRETS = {
    "acr-password": "ACR_PASS",
    "database-url": "RAG_DATABASE_URL",
    "service-token": "RAG_SERVICE_TOKEN",
    "voice-token": "RAG_VOICE_TOKEN",
    "openai-key": "OPENAI_API_KEY",
    "groq-key": "GROQ_API_KEY",
}
SECRET_ENV = {
    "RAG_DATABASE_URL": "database-url",
    "RAG_SERVICE_TOKEN": "service-token",
    "RAG_VOICE_TOKEN": "voice-token",
    "OPENAI_API_KEY": "openai-key",
    # Reads projects and listings out of uploaded files for Projects & inventory.
    "GROQ_API_KEY": "groq-key",
}
PLAIN = {
    "PROVIDER_MODE": "live",
    "RAG_VOICE_WORKSPACE_ID": "1",
    "PARSER_PROVIDER": "openai",
    "PARSER_MODEL": "gpt-4.1-mini",
    "EMBEDDING_MODEL": "text-embedding-3-small",
    "EMBEDDING_DIM": "1536",
    # The image is built without torch; the local bge reranker is not available.
    "RERANKER": "none",
    "RERANK_BUDGET_MS": "150",
    "VOICE_EMBED_BUDGET_MS": "300",
    "REWRITE_ON_VOICE": "false",
    "RAG_STORAGE_PATH": "/data/sources",
    "EXTRACTION_MODEL": "llama-3.3-70b-versatile",
}


def main() -> None:
    role = sys.argv[1] if len(sys.argv) > 1 else ""
    if role not in ("api", "worker"):
        sys.exit("usage: render_rag.py api|worker")
    required = ["ACR_SERVER", "ACR_USER", "ACR_PASS", "TAG", "ENV_ID", "LOCATION", "RAG_DATABASE_URL",
                "RAG_SERVICE_TOKEN"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        sys.exit(f"render_rag.py needs these environment variables: {', '.join(missing)}")

    present = {name: os.environ.get(source, "") for name, source in SECRETS.items()}
    present = {name: value for name, value in present.items() if value}
    env = [{"name": key, "value": os.environ.get(key, default)} for key, default in PLAIN.items()]
    env += [{"name": key, "secretRef": secret} for key, secret in SECRET_ENV.items() if secret in present]

    container = {
        "name": f"rag-{role}",
        "image": f"{os.environ['ACR_SERVER']}/rag:{os.environ['TAG']}",
        "env": env,
        "resources": {"cpu": 0.5, "memory": "1Gi"} if role == "api" else {"cpu": 1.0, "memory": "2Gi"},
        "volumeMounts": [{"volumeName": "sources", "mountPath": "/data/sources"}],
    }
    configuration = {
        "activeRevisionsMode": "Single",
        "registries": [{"server": os.environ["ACR_SERVER"], "username": os.environ["ACR_USER"],
                        "passwordSecretRef": "acr-password"}],
        "secrets": [{"name": name, "value": value} for name, value in present.items()],
    }
    if role == "api":
        container["command"] = ["sh", "-c", "python -m rag_service migrate && exec python -m rag_service api"]
        container["probes"] = [{"type": "Liveness", "httpGet": {"path": "/healthz", "port": 8090},
                                "initialDelaySeconds": 30, "periodSeconds": 30}]
        configuration["ingress"] = {"external": False, "targetPort": 8090, "transport": "http",
                                    "allowInsecure": True}
    else:
        container["args"] = ["worker"]

    app = {
        "location": os.environ["LOCATION"],
        "properties": {
            "managedEnvironmentId": os.environ["ENV_ID"],
            "configuration": configuration,
            "template": {
                "containers": [container],
                # One API replica keeps the query-embedding cache warm; workers coordinate through
                # SKIP LOCKED jobs, so one is enough for this volume and more can be added safely.
                "scale": {"minReplicas": 1, "maxReplicas": 1},
                "volumes": [{"name": "sources", "storageType": "AzureFile", "storageName": os.environ.get("RAG_STORAGE_NAME", "ragsources"),
                             "mountOptions": "dir_mode=0777,file_mode=0777,uid=0,gid=0,mfsymlinks"}],
            },
        },
    }
    json.dump(app, sys.stdout, indent=2)  # valid YAML: az accepts JSON here


if __name__ == "__main__":
    main()
