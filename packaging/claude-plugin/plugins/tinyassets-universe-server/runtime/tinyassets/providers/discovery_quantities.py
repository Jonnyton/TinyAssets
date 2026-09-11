"""Finite declared billing quantities, not proof of a remote service's behavior.

Private source-contract prerequisite: no callers, grants, IO or publication.
All calculations describe one dispatch (including its declared internal work).
Retries must separately reserve before dispatch; they never reuse a reservation.
"""

from dataclasses import dataclass

from tinyassets.providers.discovery_catalogue import _document, _fields

_DIMENSIONS = ("input_tokens", "output_tokens", "requests")
_COEFFICIENTS = ("input", "output", "per_attempt", "fixed")
_UNITS = ("input_million_tokens_usd", "output_million_tokens_usd", "request_usd")
_MAX_FACT = 10**18
_MAX_COEFFICIENT = 10**6
_MAX_COST = 2**63 - 1


def _integer(value, maximum, *, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("invalid bounded quantity integer")
    return value


@dataclass(frozen=True, slots=True)
class QuantityModel:
    """Q = a*input_bound + b*output_limit + c*attempts + d per dimension.

Coefficients are nonnegative integers <= 10**6; input facts <= 10**18.
Request quantities cannot depend on token facts. Python integer arithmetic is
exact and computationally bounded; public costs must fit signed 64-bit micros.
Coverage and declared semantic trust belong to the full source compiler.
"""

    coefficients: tuple[tuple[int, int, int, int], ...]

    @classmethod
    def compile(cls, document):
        _document(document)
        _fields(document, {"version", "quantities"})
        if type(document["version"]) is not int or document["version"] != 1:
            raise ValueError("unsupported quantity model version")
        quantities = document["quantities"]
        _fields(quantities, set(_DIMENSIONS))
        coefficients = []
        for dimension in _DIMENSIONS:
            raw = quantities[dimension]
            _fields(raw, set(_COEFFICIENTS))
            values = tuple(_integer(raw[key], _MAX_COEFFICIENT) for key in _COEFFICIENTS)
            if dimension == "requests" and (values[0] or values[1]):
                raise ValueError("request quantities cannot depend on token facts")
            coefficients.append(values)
        return cls(tuple(coefficients))

    def bounds(self, input_bound, output_limit, *, attempts=1):
        facts = (_integer(input_bound, _MAX_FACT), _integer(output_limit, _MAX_FACT),
                 _integer(attempts, _MAX_FACT, minimum=1), 1)
        return tuple(sum(coefficient * fact for coefficient, fact in zip(row, facts))
                     for row in self.coefficients)

    @staticmethod
    def _prices(caps):
        if (type(caps) is not tuple or any(type(item) is not tuple or len(item) != 2
                                         for item in caps)):
            raise ValueError("invalid accepted quantity ceilings")
        prices = {}
        for component, amount in caps:
            if type(component) is not str or component in prices:
                raise ValueError("invalid accepted quantity ceiling")
            prices[component] = _integer(amount, _MAX_FACT)
        if prices.keys() != set(_UNITS):
            raise ValueError("incomplete quantity ceilings")
        return tuple(prices[unit] for unit in _UNITS)

    def _cost(self, prices, input_bound, output_limit, attempts):
        inputs, outputs, requests = self.bounds(input_bound, output_limit, attempts=attempts)
        return ((inputs * prices[0] + 999999) // 1000000
                + (outputs * prices[1] + 999999) // 1000000 + requests * prices[2])

    def cost_upper_bound(self, caps, input_bound, output_limit, *, attempts=1):
        cost = self._cost(self._prices(caps), input_bound, output_limit, attempts)
        if cost > _MAX_COST:
            raise ValueError("quantity reservation exceeds supported cost range")
        return cost

    def affordable_output(self, caps, input_bound, output_limit, remaining_cost, *, attempts=1):
        """Maximum affordable output within the executor's explicit finite limit.

Zero means no positive output is admissible, not permission to send a zero-token
request. Fixed cost can exceed budget even at zero. The dispatcher must reserve
the resulting positive output and recheck current authority before any IO.
"""
        _integer(remaining_cost, _MAX_COST)
        prices = self._prices(caps)
        # Validate even when remaining budget is zero. Do not turn malformed
        # quantities into an apparently free model or an unaffordable model.
        self.bounds(input_bound, output_limit, attempts=attempts)
        low, high = 0, output_limit
        while low < high:
            candidate = (low + high + 1) // 2
            if self._cost(prices, input_bound, candidate, attempts) <= remaining_cost:
                low = candidate
            else:
                high = candidate - 1
        return low
