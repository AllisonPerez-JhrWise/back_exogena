"""Reglas del NIT colombiano."""

# Pesos oficiales de la DIAN, aplicados desde el dígito de la derecha hacia la izquierda
DV_WEIGHTS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)


def calculate_dv(nit: str) -> str:
    """Calcula el dígito de verificación de un NIT (sin DV, solo dígitos).

    Algoritmo módulo 11 de la DIAN: cada dígito se multiplica por su peso,
    se suma todo y se toma el residuo de dividir entre 11. Si el residuo es
    0 o 1, ese es el DV; si no, el DV es 11 menos el residuo.
    """
    if not nit.isdigit() or len(nit) > len(DV_WEIGHTS):
        raise ValueError("El NIT debe tener solo dígitos y máximo 15")

    total = sum(
        int(digit) * weight for digit, weight in zip(reversed(nit), DV_WEIGHTS, strict=False)
    )
    remainder = total % 11
    return str(remainder if remainder in (0, 1) else 11 - remainder)
