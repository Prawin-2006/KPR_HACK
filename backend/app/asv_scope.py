"""Canonical identity and eligibility rules for VenoTrack's ASV-only domain."""

ASV_PRODUCT_IDENTIFIER = "ASV-POLY-001"
ASV_PRODUCT_NAME = "Polyvalent Anti-Snake Venom"
ASV_CATEGORY = "Anti-snake venom"
ASV_UNIT = "vial"


def is_supported_product(product) -> bool:
    return bool(
        product
        and product.active
        and product.identifier == ASV_PRODUCT_IDENTIFIER
        and product.name == ASV_PRODUCT_NAME
        and product.category == ASV_CATEGORY
        and product.unit == ASV_UNIT
    )


def is_supported_batch(batch, product) -> bool:
    return bool(
        batch
        and is_supported_product(product)
        and batch.product_id == product.id
        and batch.product == ASV_PRODUCT_NAME
    )
