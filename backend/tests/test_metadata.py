from cpe.ingestion import structured_metadata


def test_metadata_aliases_rejected_before_construction(tmp_path):
    path = tmp_path / "snapshot.yaml"
    path.write_text("base: &base [one, two]\nexpanded: [*base, *base, *base]\n")
    result = structured_metadata(path, ["cluster_snapshot"])
    assert "aliases" in result["structured_skipped"]
    assert "structured" not in result


def test_ordinary_metadata_remains_available(tmp_path):
    path = tmp_path / "pods.json"
    path.write_text('{"kind":"List","items":[]}')
    assert structured_metadata(path, ["cluster_snapshot"])["structured"]["kind"] == "List"
