# This makes it easy to loop through them if you add more later
from .personas.analyst import AnalystPersona
from .personas.reckless import RecklessPersona
from .personas.wise import WisePersona


COUNCIL_MEMBERS = {
    "WISE": WisePersona(),
    "RECKLESS": RecklessPersona(),
    "ANALYST": AnalystPersona()
}