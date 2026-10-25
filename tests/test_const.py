import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("const", ROOT / "custom_components/byd_battery_box/const.py")
const = importlib.util.module_from_spec(spec)
spec.loader.exec_module(const)


def test_module_capacity_default_and_limits():
    assert const.module_capacity({}) == 15.36
    assert const.module_capacity({"module_capacity": 4.0}) == 4.0
    assert const.module_capacity({"module_capacity": 0.1}) == 1.0
    assert const.module_capacity({"module_capacity": 99}) == 30.0


def test_model_name():
    assert const.model_name("LVL", 15.36) == "LVL"
    assert const.model_name("LVL", 4.0) == "LVS"
    assert const.model_name("HVS", 2.56) == "HVS"
