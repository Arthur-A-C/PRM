"""Casos concretos do lote e limite do que a regra pode afirmar."""

from app.services.catalog_semantics import analyze_technical, assess_pair, normalize_cpu


def test_cpu_aliases_preserve_suffixes():
    variants = ("Intel® Core™ i7-1265UE", "Intel Core i7-1265UE", "ntel Core i7-1265UE", "lntel i7-1265UE")
    assert {normalize_cpu(value) for value in variants} == {"Intel Core i7-1265UE"}
    assert normalize_cpu("Intel Core i7-1265U") == "Intel Core i7-1265U"
    assert normalize_cpu("INTEL PROCESSADOR CORE I7-13700TE") == "Intel Core i7-13700TE"
    assert normalize_cpu("Intel Core i7-13700T") != normalize_cpu("Intel Core i7-13700TE")
    assert normalize_cpu("lntel aleatório") is None


def test_portwell_box_pc_storage_ports_and_scope():
    result = analyze_technical(
        name="WEBS-DS1402I7G - COMPUTADOR INDUSTRIAL BOX PC FANLESS",
        application='INTEL PROCESSADOR CORE I7-13700TE 35W, 32GB DDR5 SODIMM, 2X1TB SSD SATA 2,5" INDUSTRIAL -40~85°C, 6XUSB 3.2, 2XUSB 2.0, 2XCOM RS232/422/485 DB9',
    )
    assert (result.family, result.form_factor) == ("industrial_computer", "box_pc")
    assert "Intel Core i7-13700TE" in result.values("cpu.model")
    assert {"quantity": 2, "capacity": "1", "unit": "TB", "interface": "SATA", "form_factor_in": "2.5"} in result.values("storage.devices")
    assert result.values("ports.usb") == [{"quantity": 6, "version": "3.2"}, {"quantity": 2, "version": "2.0"}]
    assert result.values("ports.com") == [{"quantity": 2, "protocols": ["RS232", "RS422", "RS485"]}]
    assert not result.values("display.diagonal_in")
    assert not result.values("equipment.temperature_c")
    assert not result.values("equipment.power_w")


def test_portwell_ram_and_power_are_separate():
    result = analyze_technical(
        name="WEBS-2414 - COMPUTADOR INDUSTRIAL BOX PC",
        application="16GB SODIMM, 1TB SSD NVME, DC-IN 9~36, FONTE ALIMENTAÇÃO 12V",
    )
    assert 16 in result.values("memory.capacity_gb", "installed_configuration")
    assert not result.values("memory.generation")
    assert [9, 36] in result.values("power.input_range_vdc", "equipment_input")
    assert 12 in result.values("power.supply_nominal_v", "included_supply")


def test_maximum_ram_does_not_replace_installed_configuration():
    result = analyze_technical(
        name="PANEL PC ASUS 16GB DDR4 256GB SSD",
        description="Memória até 32GB; 2 slots disponíveis",
    )
    assert result.values("memory.capacity_gb", "installed_configuration") == [16]
    assert result.values("memory.capacity_gb", "platform_maximum") == [32]
    assert result.form_factor == "panel_pc"


def test_accessory_kit_and_conflicting_erp_group():
    accessory = analyze_technical(name="BLOCO DE CONTATO PARA CONTATOR")
    assert accessory.item_role == "accessory"
    assert accessory.family != "contactor"
    kit = analyze_technical(name="KIT UMG801 para 1 PDU/RPP de 192 polos", application="TOTALIZANDO 192 POLOS/FASES")
    assert kit.item_role == "kit"
    assert kit.values("coverage.monitored_poles")
    assert not kit.values("contactor.power_poles")
    contator = analyze_technical(name="CONTATOR CWM25-10-30C03", application="BOBINA 24VCC, 25A EM AC-3", category="Sensores Tradicionais")
    assert contator.family == "contactor"
    assert "conflito_categoria_comercial" in contator.issues
    assert {"value": 25, "utilization": "AC-3"} in contator.values("current.rating_a")
    assert {"value": 24, "kind": "CC"} in contator.values("coil.voltage")


def test_critical_pairs_never_auto_approve():
    eco_supply = analyze_technical(name="FONTE TRIFÁSICA 400/500VCA 24VCC 20A")
    choice_ups = analyze_technical(name="FONTE DE ALIMENTACAO UPS", application="ENTRADA: 24 Vcc, SAIDA: 24 Vcc, 25 A")
    assert assess_pair(eco_supply, choice_ups)["status"] == "incompativel"
    eco_contactor = analyze_technical(name="CONTATOR TRIPOLAR 38A DILM38-10(RDC24)")
    choice_contactor = analyze_technical(name="CONTATOR CWM25-10-30C03", application="25A EM AC-3")
    assert assess_pair(eco_contactor, choice_contactor)["status"] == "dados_insuficientes"


def test_generic_computer_has_unknown_format_and_monitor_is_not_pc():
    generic = analyze_technical(name="COMPUTADOR INDUSTRIAL")
    monitor = analyze_technical(name="MONITOR INDUSTRIAL 15 POLEGADAS")
    assert generic.family == "industrial_computer" and generic.form_factor is None
    assert monitor.family != "industrial_computer"
