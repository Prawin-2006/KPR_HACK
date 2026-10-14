from types import SimpleNamespace

from app.asv_scope import is_supported_batch, is_supported_product


def test_supported_product_requires_exact_canonical_identity():
    canonical = SimpleNamespace(
        id=1,
        identifier="ASV-POLY-001",
        name="Polyvalent Anti-Snake Venom",
        category="Anti-snake venom",
        unit="vial",
        active=True,
    )
    assert is_supported_product(canonical) is True

    for changes in (
        {"identifier": "LEGACY-AMOXICILLIN"},
        {"name": "Amoxicillin"},
        {"category": "Antibiotic"},
        {"unit": "tablet"},
        {"active": False},
    ):
        product = SimpleNamespace(**{**canonical.__dict__, **changes})
        assert is_supported_product(product) is False


def test_supported_batch_requires_active_supported_product():
    product = SimpleNamespace(
        id=1,
        identifier="ASV-POLY-001",
        name="Polyvalent Anti-Snake Venom",
        category="Anti-snake venom",
        unit="vial",
        active=True,
    )
    batch = SimpleNamespace(product_id=1, product="Polyvalent Anti-Snake Venom")
    assert is_supported_batch(batch, product) is True

    batch.product_id = 2
    assert is_supported_batch(batch, product) is False
    batch.product_id = 1
    product.active = False
    assert is_supported_batch(batch, product) is False
