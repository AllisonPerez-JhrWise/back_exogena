import pytest

from app.modules.clients.nit import calculate_dv


@pytest.mark.parametrize(
    "nit, dv",
    [
        ("800197268", "4"),  # DIAN
        ("890903938", "8"),  # Bancolombia
        ("899999063", "3"),
        ("900123456", "8"),  # NIT del mockup (el mockup muestra 4, que es incorrecto)
    ],
)
def test_calculate_dv_matches_dian(nit, dv):
    assert calculate_dv(nit) == dv


@pytest.mark.parametrize("nit", ["90012345A", "900-123", "1" * 16])
def test_calculate_dv_rejects_invalid_nit(nit):
    with pytest.raises(ValueError):
        calculate_dv(nit)
