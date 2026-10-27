"""Term order is not a product change (Portwell lists categories in a different order per read). Mocks only.

Regression for "Alteração concorrente detectada durante o backup; nada removido" on Portwell product 18231,
whose two "Painel PC" categories (444 and 506) alternate order between REST responses.
"""
from copy import deepcopy

import pytest

from app.services import store_file_removal as removal
from app.services.store_publish import _legacy_protected_hash, _protected_hash, protected_matches
from test_store_file_removal import Shop, commercial, dry, execute, jobs, quick_read_back, settings  # noqa: F401

PAINEL = [{"id": 506, "name": "Painel PC", "slug": "painel-pc-painel-pc"}, {"id": 444, "name": "Painel PC", "slug": "painel-pc"}]


def product(**changes):
    base = {"name": "Painel", "regular_price": "10.00", "categories": deepcopy(PAINEL), "tags": [{"id": 1}, {"id": 2}],
            "meta_data": [{"id": 1, "key": "_yoast_wpseo_focuskw", "value": "x"}]}
    return {**base, **changes}


def test_hash_ignores_term_order_but_not_membership_or_commercial_fields():
    reordered = product(categories=list(reversed(PAINEL)), tags=[{"id": 2}, {"id": 1}])
    assert _protected_hash(product()) == _protected_hash(reordered)
    assert _protected_hash(product()) != _protected_hash(product(categories=PAINEL[:1]))  # category removed
    assert _protected_hash(product()) != _protected_hash(product(categories=PAINEL + [{"id": 7}]))  # category added
    assert _protected_hash(product()) != _protected_hash(product(regular_price="1.00"))
    assert _protected_hash(product()) != _protected_hash(product(meta_data=[{"id": 1, "key": "_yoast_wpseo_focuskw", "value": "y"}]))


def test_hashes_stored_by_previous_versions_are_still_recognized():
    stored = _legacy_protected_hash(product())  # journal written before this fix
    assert stored != _protected_hash(product())
    assert protected_matches(product(), stored)
    assert not protected_matches(product(regular_price="1.00"), stored)
    assert not protected_matches(product(), "") and not protected_matches(product(), None)


class FlippingShop(Shop):
    """Each WooCommerce product response lists the categories in the opposite order, like the Portwell API."""

    def __init__(self):
        super().__init__()
        self.products["000123"]["categories"] = deepcopy(PAINEL)
        self.flip = True
        self.responses = 0

    def wc_view(self, sku, p):
        view = super().wc_view(sku, p)
        self.responses += 1
        if self.flip and self.responses % 2:
            view["categories"] = list(reversed(view["categories"]))
        return view


def flipping_shop():
    return FlippingShop()


@pytest.mark.parametrize("mode", ["all", "gallery", "documents", "main"])
def test_removal_completes_when_the_store_reorders_categories(jobs, settings, mode):
    shop = flipping_shop()
    before = commercial(shop)
    removals, identifier, _ = dry(jobs, settings, shop, mode)
    item = execute(removals, identifier, jobs, settings, shop)["items"][0]
    assert item["state"] == "done" and item["result"]["verified"], item["error"]
    after = commercial(shop)
    assert sorted(after.pop("categories"), key=lambda c: c["id"]) == sorted(before.pop("categories"), key=lambda c: c["id"])
    assert after == before


def test_category_really_added_during_removal_still_blocks(jobs, settings):
    shop = flipping_shop()
    removals, identifier, _ = dry(jobs, settings, shop, "gallery")
    shop.products["000123"]["categories"].append({"id": 999, "name": "Nova", "slug": "nova"})  # real change after the Dry Run
    item = execute(removals, identifier, jobs, settings, shop)["items"][0]
    assert item["state"] == "error" and "concorrente" in item["error"] and not shop.writes


def test_restore_of_a_removal_journaled_with_the_legacy_hash(jobs, settings, monkeypatch):
    shop = flipping_shop()
    shop.flip = False  # stable order while the old version journals the removal
    monkeypatch.setattr(removal, "_protected_hash", _legacy_protected_hash)  # behave like the previous version
    removals, identifier, _ = dry(jobs, settings, shop, "gallery")
    assert execute(removals, identifier, jobs, settings, shop)["items"][0]["state"] == "done"
    monkeypatch.undo()
    monkeypatch.setattr(removal, "VERIFY_DELAYS", (0, 0))
    monkeypatch.setattr(removal.production, "check_approval", lambda *args: True)
    from contextlib import nullcontext
    monkeypatch.setattr(removal.production, "session", lambda: nullcontext(None))
    from test_store_file_removal import restore_via_queue
    restored = restore_via_queue(removals, identifier, jobs, settings, shop)
    assert restored["status"] == "restored" and shop.products["000123"]["gallery"] == [12, 13]
