"""Cadastro via API: padrão oficial <SKU>_1.ext = principal, <SKU>_2.ext.. = galeria em ordem numérica. Mocks only.

No test reaches a real store: every request goes to the Store double through httpx.MockTransport.
"""
import io
import json
import zipfile

import pytest
from PIL import Image
from registration_identity_fixture import mocked_registration_identity  # noqa: F401
from test_store_registration_scope import ALL, GALLERY, MAIN, item, plan_of, publish, reseal, save, start, uploaded
from test_store_registration_zip import SKU, Store, drain, jobs, settings  # noqa: F401

from app.services.store_registration_plan import classify_by_index, image_position

pytestmark = pytest.mark.usefixtures("mocked_registration_identity")


def picture(fmt="PNG", color=(200, 30, 30)):
    stream = io.BytesIO()
    Image.new("RGB", (24, 18), color).save(stream, fmt)
    return stream.getvalue()


def folder(names, sku=SKU, docs=True):
    """Raw SKU folder (no manifest). Each image has distinct bytes so hashes never collide."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for n, name in enumerate(names):
            fmt = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP"}.get(name.rsplit(".", 1)[1].lower())
            archive.writestr(f"{sku}/{name}", picture(fmt, (10 * n % 255, 80, 160)) if fmt else b"<svg xmlns='http://www.w3.org/2000/svg'/>")
        if docs:
            archive.writestr(f"{sku}/{sku}_Datasheet.pdf", b"%PDF-1.4 gerado")
    return stream.getvalue()


def names(actions, role):
    return [a["name"] for a in actions if a["role"] == role]


# --- Classificação --------------------------------------------------------------------------------

def test_one_is_main_and_gallery_follows_the_numeric_suffix(jobs, settings):
    store = Store(images=[10], wcda=[])
    files = [f"{SKU}_10.png", f"{SKU}_3.png", f"{SKU}_1.png", f"{SKU}_2.png"]
    identifier, current = start(jobs, settings, store, ALL, folder(files))
    dry = current["dry_run"]
    assert current["state"] == "review" and not dry["main_choice_required"] and dry["main_options"] == []
    assert dry["image_rule"]["main"]["name"] == f"{SKU}_1.png"
    assert [g["name"] for g in dry["image_rule"]["gallery"]] == [f"{SKU}_2.png", f"{SKU}_3.png", f"{SKU}_10.png"]
    assert [g["position"] for g in dry["image_rule"]["gallery"]] == [2, 3, 10]  # never _10, _2, _3
    assert names(dry["images"]["actions"], "main_image") == [f"{SKU}_1.png"]
    assert [f["name"] for f in dry["images"]["final_order"]] == [f"{SKU}_1.png", "foto-antiga.jpg", f"{SKU}_2.png", f"{SKU}_3.png", f"{SKU}_10.png"]
    main = dry["images"]["main_image"]
    assert main["detected"] and main["message"].startswith(f"Principal detectada automaticamente: {SKU}_1.png.")
    assert main["current"]["name"] == "foto-antiga.jpg" and main["proposed"]["name"] == f"{SKU}_1.png" and main["previous_to_gallery"]
    publish(jobs, settings, store, identifier)
    sha = {a["name"]: a["sha256"] for a in dry["images"]["actions"]}
    linked = [store.library[i["id"]].rsplit("/", 1)[1] for i in store.product["images"]]
    assert linked == [f"prm-{sha[f'{SKU}_1.png']}.png", "foto-antiga.jpg"] + [f"prm-{sha[f'{SKU}_{n}.png']}.png" for n in (2, 3, 10)]


def test_missing_one_never_promotes_two_and_asks_for_review(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, current = start(jobs, settings, store, ALL, folder([f"{SKU}_2.png", f"{SKU}_3.png"]))
    dry = current["dry_run"]
    assert current["state"] == "awaiting_main" and current["error"] == f"Foto principal não encontrada no padrão {SKU}_1.ext."
    assert names(dry["images"]["actions"], "main_image") == [] and dry["images"]["main_image"]["action"] == "choose"
    assert names(dry["images"]["actions"], "gallery") == [f"{SKU}_2.png", f"{SKU}_3.png"]
    with pytest.raises(ValueError):
        jobs.approve(identifier, "org", "owner", [SKU])
    assert store.posts == 0


@pytest.mark.parametrize("position", [1, 2])
def test_same_position_twice_blocks_the_sku(jobs, settings, position):
    files = [f"{SKU}_1.png", f"{SKU}_2.png", f"{SKU}_3.png", f"{SKU}_{position}.jpg"]
    store = Store(images=[10], wcda=[])
    identifier, current = start(jobs, settings, store, ALL, folder(files))
    assert current["state"] == "blocked" and f"Mais de uma imagem encontrada para a posição _{position}." in current["error"]
    assert {f"{SKU}_{position}.png", f"{SKU}_{position}.jpg"} <= {i["name"] for i in current["dry_run"]["ignored"]}
    assert all(image_position(a["name"], SKU) != position for a in current["dry_run"]["images"]["actions"])
    with pytest.raises(ValueError):
        jobs.approve(identifier, "org", "owner", [SKU])
    assert store.posts == 0 and not store.puts


def test_sku_is_a_string_with_leading_zeros(jobs, settings):
    sku = "00117001000020"
    store = Store(sku=sku, images=[10], wcda=[])
    files = [f"{sku}_1.png", f"{sku}_2.png", "117001000020_3.png"]  # without the zeros it is another SKU
    identifier = jobs.create("choice", "org", "owner", None, folder(files, sku), settings, identification="folder",
                             archive_name=sku + ".zip", scope=ALL)
    drain(jobs, settings, store)
    current = item(jobs, identifier, sku)
    rule = current["dry_run"]["image_rule"]
    assert current["sku"] == sku and current["state"] == "review"
    assert rule["main"]["name"] == f"{sku}_1.png" and [g["name"] for g in rule["gallery"]] == [f"{sku}_2.png"]
    assert rule["outside"] == ["117001000020_3.png"] and rule["pattern"] == f"{sku}_<n>.ext"


def test_extension_case_is_ignored(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, current = start(jobs, settings, store, ALL, folder([f"{SKU}_1.PNG", f"{SKU}_2.JPG", f"{SKU}_3.Jpeg"]))
    rule = current["dry_run"]["image_rule"]
    assert current["state"] == "review" and rule["main"]["name"] == f"{SKU}_1.PNG"
    assert [g["name"] for g in rule["gallery"]] == [f"{SKU}_2.JPG", f"{SKU}_3.Jpeg"]


def test_files_outside_the_pattern_are_never_classified(jobs, settings):
    store = Store(images=[10], wcda=[])
    files = [f"{SKU}_1.png", "frente.png", "foto_lateral.png", "produto-final.jpg", f"{SKU}_variante.png", f"{SKU}_foto2.png"]
    identifier, current = start(jobs, settings, store, ALL, folder(files))
    dry = current["dry_run"]
    assert [a["name"] for a in dry["images"]["actions"]] == [f"{SKU}_1.png"]
    outside = [i for i in dry["ignored"] if i["label"] == "Fora do padrão"]
    assert {i["name"] for i in outside} == set(files[1:]) and "Imagem fora do padrão de nomenclatura" in outside[0]["reason"]


def test_svg_next_to_the_png_is_reported_not_counted_as_duplicate(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, current = start(jobs, settings, store, ALL, folder([f"{SKU}_1.png", f"{SKU}_1.svg", f"{SKU}_2.png"]))
    assert current["state"] == "review" and current["dry_run"]["image_rule"]["duplicates"] == []
    assert any(i["name"] == f"{SKU}_1.svg" and i["label"] == "Formato não enviado" for i in current["dry_run"]["ignored"])


def test_classification_helper_is_numeric_and_exact():
    candidates = [{"name": n, "sha256": n} for n in (f"{SKU}_10.png", f"{SKU}_2.png", f"{SKU}_0.png", f"{SKU}_01.png",
                                                      f"{SKU}_3.gif", f"X{SKU}_4.png", f"{SKU}_5.png.bak")]
    rule = classify_by_index(candidates, SKU)
    assert rule["main"]["name"] == f"{SKU}_01.png"  # position 1 written with a leading zero
    assert [c["name"] for c in rule["gallery"]] == [f"{SKU}_2.png", f"{SKU}_10.png"]
    assert {c["name"] for c in rule["outside"]} == {f"{SKU}_0.png", f"{SKU}_3.gif", f"X{SKU}_4.png", f"{SKU}_5.png.bak"}


# --- Escopo --------------------------------------------------------------------------------------

def test_without_main_scope_the_one_is_ignored(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, current = start(jobs, settings, store, GALLERY, folder([f"{SKU}_1.png", f"{SKU}_2.png", f"{SKU}_3.png"]))
    dry = current["dry_run"]
    assert [(a["name"], a["role"]) for a in dry["images"]["actions"]] == [(f"{SKU}_2.png", "gallery"), (f"{SKU}_3.png", "gallery")]
    assert any(i["name"] == f"{SKU}_1.png" and i["reason"] == "Foto principal fora do escopo selecionado." for i in dry["ignored"])
    publish(jobs, settings, store, identifier)
    assert store.product["images"][0]["id"] == 10 and len(store.product["images"]) == 3 and store.posts == 2


def test_without_gallery_scope_only_the_one_is_used(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, current = start(jobs, settings, store, MAIN, folder([f"{SKU}_1.png", f"{SKU}_2.png", f"{SKU}_3.png"]))
    assert [(a["name"], a["role"]) for a in current["dry_run"]["images"]["actions"]] == [(f"{SKU}_1.png", "main_image")]
    publish(jobs, settings, store, identifier)
    assert [i["id"] for i in store.product["images"]][1:] == [10] and store.posts == 1


def test_only_the_one_with_gallery_scope_is_not_an_error(jobs, settings):
    store = Store(images=[10], wcda=[])
    _, current = start(jobs, settings, store, GALLERY, folder([f"{SKU}_1.png"], docs=False))
    assert current["state"] == "nothing" and current["error"] == "Galeria: nenhuma imagem nova encontrada."


def test_manual_main_is_refused_when_the_one_exists(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, current = start(jobs, settings, store, ALL, folder([f"{SKU}_1.png", f"{SKU}_2.png"]))
    sha = current["dry_run"]["images"]["actions"][1]["sha256"]
    with pytest.raises(ValueError, match=f"padrão {SKU}_1.ext"):
        jobs.choose_main(identifier, "org", "owner", SKU, sha)


# --- Hash, worker e concorrência ---------------------------------------------------------------------

def approved_and_queued(jobs, settings, store, files):
    identifier, current = start(jobs, settings, store, ALL, folder(files))
    jobs.approve(identifier, "org", "owner", [SKU])
    jobs.confirm(identifier, "org", "owner", settings, [SKU], confirmed=True)
    return identifier, current


@pytest.mark.parametrize("forgery", ["swap_gallery_order", "two_as_main", "drop_gallery"])
def test_worker_revalidates_the_order_even_on_a_resealed_plan(jobs, settings, forgery):
    store = Store(images=[10], wcda=[])
    identifier, _ = approved_and_queued(jobs, settings, store, [f"{SKU}_1.png", f"{SKU}_2.png", f"{SKU}_3.png"])
    plan = plan_of(jobs)
    if forgery == "swap_gallery_order":
        plan["images"][1], plan["images"][2] = plan["images"][2], plan["images"][1]
        actions = plan["dry_run"]["images"]["actions"]; actions[1], actions[2] = actions[2], actions[1]
    elif forgery == "two_as_main":
        plan["images"][0], plan["images"][1] = {**plan["images"][1], "role": "main_image"}, {**plan["images"][0], "role": "gallery"}
    else:
        plan["images"].pop(); plan["dry_run"]["images"]["actions"].pop()
    reseal(jobs, plan)
    drain(jobs, settings, store)
    current = item(jobs, identifier)
    assert current["state"] == "error" and f"padrão {SKU}_<n>.ext" in current["error"]
    assert store.posts == 0 and not store.puts


def test_order_is_part_of_the_signed_dry_run(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, _ = approved_and_queued(jobs, settings, store, [f"{SKU}_1.png", f"{SKU}_2.png", f"{SKU}_3.png"])
    plan = plan_of(jobs)
    plan["dry_run"]["image_rule"]["gallery"].reverse()  # without resealing: hash no longer matches
    save(jobs, plan)
    drain(jobs, settings, store)
    assert item(jobs, identifier)["state"] == "error" and store.posts == 0


@pytest.mark.parametrize("change", ["rename", "add", "remove", "replace_bytes"])
def test_file_changes_after_approval_invalidate_the_execution(jobs, settings, change):
    store = Store(images=[10], wcda=[])
    identifier, _ = approved_and_queued(jobs, settings, store, [f"{SKU}_1.png", f"{SKU}_2.png", "frente.png"])
    sku_folder = jobs.root / identifier / SKU
    if change == "rename": (sku_folder / "frente.png").rename(sku_folder / f"{SKU}_3.png")
    elif change == "add": (sku_folder / f"{SKU}_4.png").write_bytes(picture())
    elif change == "remove": (sku_folder / f"{SKU}_2.png").unlink()
    else:
        target = sku_folder / f"{SKU}_2.png"
        data = picture(color=(1, 2, 3))
        target.write_bytes(data[:target.stat().st_size].ljust(target.stat().st_size, b"\0"))
    drain(jobs, settings, store)
    current = item(jobs, identifier)
    assert current["state"] == "error" and "refaça a prévia" in current["error"]
    assert store.posts == 0 and not store.puts
