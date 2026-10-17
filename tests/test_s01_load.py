import pytest

from pipeline import s01_load as s01


@pytest.mark.network
def test_gamla_stan_fixture_cleans_to_one_row_per_building(gamla_stan_lod1):
    b = s01.clean(gamla_stan_lod1, log=lambda *_: None)
    assert 480 <= len(b) <= len(gamla_stan_lod1) <= 530        # 519 -> 519 on 2026-10-14
    assert b["gid"].tolist() == list(range(len(b)))
    assert not b["oid"].duplicated().any()
    assert (b["height"] > 0).all() and (b["area"] >= s01.SLIVER_M2).all()
    assert (b["uuid"] == "").any()                              # the cut exercises empty UUIDs (21 of them)
    church = b[(b["fastighet"] == "GRÅMUNKEHOLMEN 3") & (b["kategori"] == "Ospec. samfundsbyggnad")]
    assert church["height"].tolist() == pytest.approx([15.1], abs=1e-4)   # Riddarholmskyrkan without its 89.7 m spire
    palace = b[(b["fastighet"] == "TRE KRONOR 1") & (b["area"] > 9000)]
    assert palace["height"].tolist() == pytest.approx([35.0], abs=1e-4)   # BYGG_H 39.1 reaches TAKMAX_Z
    assert b.crs.to_epsg() == 3011
