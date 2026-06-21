#!/usr/bin/env python3
"""Injeta a camada BACKBONE de infraestrutura no super-grafo fundido.

Aditivo e schema-compatível (networkx node-link). Cria:
  - 1 no raiz da infraestrutura
  - 1 no por subsistema (repo) presente no grafo
  - arestas semanticas que contam a historia da infra (deploy, captura, etc.)
  - ligacao de cada no-subsistema aos representantes de CADA componente conexo
    do seu repo -> garante UM unico componente conexo final.
"""
import json
import sys
from collections import defaultdict, Counter, deque

MERGED = r"C:\Users\Windows\Desktop\Roleta Cloud\super_graph\graphify-out\graph.json"

# Rotulos humanos + historia da infra por repo de origem
SUBSYS = {
    "Roleta Cloud": {
        "node_id": "_INFRA_::roleta_cloud",
        "label": "💻 Roleta Cloud — App (LOCAL dev + legado Extrator)",
        "desc": "Backend Python/WebSocket: server/, state/, strategies/, database/. "
                "Inclui o grafo legado 'Extrator beat novo' (subconjunto estrito).",
    },
    "server_snapshot": {
        "node_id": "_INFRA_::debian",
        "label": "🖥️ Servidor Debian — PRODUÇÃO (187.45.181.75)",
        "desc": "Host Debian que executa o app em Docker. Snapshot de sistema, "
                "docker-compose, systemd, deploy-timer, prometheus.",
    },
    "android": {
        "node_id": "_INFRA_::android",
        "label": "📱 Extensão Android/Chrome — Captura de spins",
        "desc": "Extensão (content/background) + skills handshake/bootstrap que "
                "capturam resultados da roleta e alimentam o servidor.",
    },
    "Genesis azure": {
        "node_id": "_INFRA_::genesis_azure",
        "label": "☁️ Genesis Azure — Deploy alternativo (cloud)",
        "desc": "Provisionamento Azure (VM, PG Flexible, btrfs/swap) como caminho "
                "de deploy alternativo da infraestrutura.",
    },
    "Testando Grafiphy": {
        "node_id": "_INFRA_::testando",
        "label": "🧪 Testando Graphify — Sandbox de análise",
        "desc": "Documentos de análise/pensamento usados para validar o próprio "
                "pipeline graphify.",
    },
}

# Arestas semanticas da infra (a historia real). (origem_repo, destino_repo, relacao)
INFRA_STORY = [
    ("server_snapshot", "Roleta Cloud", "hospeda_executa"),      # Debian roda o app
    ("android", "server_snapshot", "envia_spins_para"),          # extensao -> servidor
    ("Genesis azure", "Roleta Cloud", "deploy_alternativo_de"),  # azure = deploy alt
    ("Testando Grafiphy", "Roleta Cloud", "valida_pipeline_de"), # sandbox valida
]

ROOT_ID = "_INFRA_::root"
ROOT_LABEL = "🌐 INFRAESTRUTURA ROLETA — Super-Grafo (toda a stack)"


def main():
    d = json.load(open(MERGED, encoding="utf-8"))
    nodes = d["nodes"]
    links = d["links"]
    by_id = {n["id"]: n for n in nodes}
    repo_of = {n["id"]: n.get("repo") for n in nodes}

    # grau de entrada + adjacencia (nao-direcionada) por repo
    indeg = Counter()
    for l in links:
        indeg[l["target"]] += 1
    adj = defaultdict(set)
    for l in links:
        adj[l["source"]].add(l["target"])
        adj[l["target"]].add(l["source"])

    repos = [r for r in SUBSYS if any(repo_of.get(n["id"]) == r for n in nodes)]
    print("Subsistemas presentes:", repos)

    # comunidade nova reservada p/ backbone
    max_comm = max((n.get("community", 0) or 0) for n in nodes)
    infra_comm = max_comm + 1

    new_nodes = []
    new_links = []

    def mknode(nid, label, desc, repo="_INFRA_", ftype="infra"):
        return {
            "label": label,
            "file_type": ftype,
            "source_file": "_INFRA_BACKBONE_",
            "source_location": "L0",
            "community": infra_comm,
            "norm_label": label.lower(),
            "repo": repo,
            "local_id": nid.split("::", 1)[-1],
            "id": nid,
            "metadata": {"backbone": True, "desc": desc},
        }

    def mkedge(s, t, rel, ctx=""):
        return {
            "relation": rel,
            "confidence": "INFERRED",
            "confidence_score": 0.9,
            "source_file": "_INFRA_BACKBONE_",
            "source_location": "L0",
            "weight": 3.0,
            "source": s,
            "target": t,
            "context": ctx or rel,
        }

    # 1) no raiz
    new_nodes.append(mknode(ROOT_ID, ROOT_LABEL,
                            "Raiz unica do super-grafo: funde app local, servidor "
                            "Debian de producao, extensao Android, deploy Azure e "
                            "sandbox de testes."))

    # 2) nos-subsistema + raiz->subsistema
    for r in repos:
        s = SUBSYS[r]
        new_nodes.append(mknode(s["node_id"], s["label"], s["desc"]))
        new_links.append(mkedge(ROOT_ID, s["node_id"], "infra_comprises",
                                 f"infra inclui {r}"))

    # 3) historia semantica da infra
    for src_r, dst_r, rel in INFRA_STORY:
        if src_r in repos and dst_r in repos:
            new_links.append(mkedge(SUBSYS[src_r]["node_id"],
                                    SUBSYS[dst_r]["node_id"], rel))

    # 4) ligar cada subsistema aos representantes de CADA componente conexo do repo
    #    -> garante 1 unico componente conexo final
    bridges = 0
    for r in repos:
        rnodes = [n["id"] for n in nodes if repo_of.get(n["id"]) == r]
        rset = set(rnodes)
        seen = set()
        comps = []
        for nid in rnodes:
            if nid in seen:
                continue
            q = deque([nid]); seen.add(nid); comp = []
            while q:
                x = q.popleft(); comp.append(x)
                for y in adj[x]:
                    if y in rset and y not in seen:
                        seen.add(y); q.append(y)
            comps.append(comp)
        # representante de cada componente: menor in-degree (raiz), desempate por maior grau
        for comp in comps:
            rep = min(comp, key=lambda x: (indeg[x], -len(adj[x])))
            new_links.append(mkedge(SUBSYS[r]["node_id"], rep, "infra_contains",
                                     f"{r} contem componente ({len(comp)} nos)"))
            bridges += 1

    d["nodes"] = nodes + new_nodes
    d["links"] = links + new_links
    # metadados do super-grafo
    d["graph"] = {
        "super_graph": True,
        "title": "Super-Grafo da Infraestrutura Roleta",
        "built": "2026-06-14",
        "subsystems": repos,
        "fused_from": [
            "Roleta Cloud (local 4fda6ff)", "server_snapshot Debian (b1875a0)",
            "android", "Extrator beat novo/Roleta (98c7d7f, ⊂ local)",
            "Genesis azure (565bd30)", "Testando Grafiphy",
        ],
        "backbone_community": infra_comm,
    }

    json.dump(d, open(MERGED, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Backbone: +{len(new_nodes)} nos, +{len(new_links)} arestas "
          f"({bridges} pontes p/ componentes).")
    print(f"TOTAL: {len(d['nodes'])} nos, {len(d['links'])} arestas. "
          f"comunidade backbone={infra_comm}")


if __name__ == "__main__":
    main()
