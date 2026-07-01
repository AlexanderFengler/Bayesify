"""The Archive: the on-disk papers store, method-tag derivation, and the list/tag endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from bayesify.api.app import app
from bayesify.api.papers_store import (
    ArchivedPaper,
    PapersStore,
    methods_from_inventory,
)
from bayesify.core.detectors import EvidenceInventory, InventoryFamily, InventoryHit
from bayesify.core.schema import EvidenceKind

client = TestClient(app)


def _hit(detector_id: str, family: str) -> InventoryHit:
    return InventoryHit(
        detector_id=detector_id,
        family=family,
        kind=EvidenceKind.software_mention,
        section_id="s01",
        section_title="Methods",
        quote="…",
    )


def _inventory() -> EvidenceInventory:
    return EvidenceInventory(
        families=[
            InventoryFamily(family="software", found=[_hit("software.stan", "software")]),
            InventoryFamily(family="method", found=[_hit("method.mcmc", "method")]),
            # sampler is deliberately excluded from the "methods & software" facet
            InventoryFamily(family="sampler", found=[_hit("sampler.chains", "sampler")]),
        ],
        n_hits=3,
    )


def test_methods_from_inventory_maps_and_filters_families() -> None:
    labels = methods_from_inventory(_inventory())
    assert labels == ["Stan", "MCMC"]  # sampler.chains excluded; curated labels
    assert methods_from_inventory(None) == []


def test_store_upsert_preserves_manual_tags_and_falls_back_auto(tmp_path) -> None:
    store = PapersStore(tmp_path / "papers")
    # 1) an AI analysis lands with auto tags
    store.upsert(
        ArchivedPaper(
            source_sha256="ab" * 32,
            rubric_profile="synthesis",
            paper_title="A paper",
            paper_type=["data_analysis"],
            discipline=["neuroscience"],
            methods=["Stan", "MCMC"],
        )
    )
    # 2) a later human rating of the SAME paper adds manual tags but carries no inventory/discipline
    saved = store.upsert(
        ArchivedPaper(
            source_sha256="ab" * 32,
            rubric_profile="synthesis",
            paper_type=["data_analysis"],
            manual_tags=["to-read", "cool"],
        )
    )
    assert saved.manual_tags == ["to-read", "cool"]
    assert saved.discipline == ["neuroscience"]  # auto tags preserved when the upsert omits them
    assert saved.methods == ["Stan", "MCMC"]
    # one entry, keyed by sha+profile (no duplicate from the second upsert)
    assert len(store.list()) == 1


def test_store_set_tags_replaces_manual_only(tmp_path) -> None:
    store = PapersStore(tmp_path / "papers")
    p = store.upsert(
        ArchivedPaper(source_sha256="cd" * 32, methods=["Stan"], manual_tags=["old"])
    )
    updated = store.set_tags(p.key, ["fresh", "  fresh  ", ""])
    assert updated is not None
    assert updated.manual_tags == ["fresh"]  # trimmed + de-duplicated
    assert updated.methods == ["Stan"]  # auto tags untouched
    assert store.set_tags("no-such-key", ["x"]) is None


def test_list_papers_endpoint_filters_and_patches(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    store = PapersStore(tmp_path / "papers")
    store.upsert(
        ArchivedPaper(
            source_sha256="11" * 32,
            paper_title="Hierarchical DDM",
            paper_authors=["Ada Lovelace"],
            paper_type=["data_analysis"],
            discipline=["neuroscience"],
            methods=["Stan"],
        )
    )
    store.upsert(
        ArchivedPaper(
            source_sha256="22" * 32,
            paper_title="A new sampler",
            paper_type=["method_development"],
            discipline=["statistics"],
            methods=["MCMC"],
        )
    )

    # unfiltered: both, plus facet vocabularies over the whole archive
    body = client.get("/api/papers").json()
    assert body["total"] == 2 and len(body["papers"]) == 2
    assert "data_analysis" in body["facets"]["paper_type"]
    assert "neuroscience" in body["facets"]["discipline"]

    # free-text matches title/authors
    assert len(client.get("/api/papers", params={"q": "lovelace"}).json()["papers"]) == 1

    # facet AND-filter
    got = client.get("/api/papers", params={"discipline": "statistics"}).json()["papers"]
    assert [p["paper_title"] for p in got] == ["A new sampler"]

    # PATCH manual tags on one paper
    key = got[0]["key"]
    patched = client.patch(f"/api/papers/{key}/tags", json={"tags": ["important", "important"]})
    assert patched.status_code == 200
    assert patched.json()["manual_tags"] == ["important"]
    # the tag now filters
    assert len(client.get("/api/papers", params={"tag": "important"}).json()["papers"]) == 1
    # unknown key → 404
    assert client.patch("/api/papers/nope/tags", json={"tags": []}).status_code == 404
