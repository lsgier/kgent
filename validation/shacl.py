from dataclasses import dataclass, field
from pathlib import Path

import rdflib
import pyshacl


SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
SCHEMA = rdflib.Namespace("http://schema.org/")


@dataclass
class ValidationResult:
    valid: bool
    violations: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        if self.valid:
            return "SHACL validation passed"
        return "SHACL validation failed:\n" + "\n".join(f"  - {v}" for v in self.violations)


class SHACLValidator:
    def __init__(self, shapes_path: Path):
        self._shapes_graph = rdflib.Graph().parse(str(shapes_path), format="turtle")
        self._shape_cache: dict[rdflib.URIRef, rdflib.Graph] = {}

    def _extract_shape(self, target_class: rdflib.URIRef) -> rdflib.Graph:
        if target_class in self._shape_cache:
            return self._shape_cache[target_class]
        shape_node = next(self._shapes_graph.subjects(SH.targetClass, target_class))
        shape = rdflib.Graph()
        visited: set = set()
        queue = [shape_node]
        while queue:
            node = queue.pop()
            if node in visited:
                continue
            visited.add(node)
            for p, o in self._shapes_graph.predicate_objects(node):
                shape.add((node, p, o))
                if isinstance(o, (rdflib.URIRef, rdflib.BNode)):
                    queue.append(o)
        self._shape_cache[target_class] = shape
        return shape

    def _run(self, data_graph: rdflib.Graph, shapes_graph: rdflib.Graph) -> ValidationResult:
        conforms, _, report_text = pyshacl.validate(
            data_graph,
            shacl_graph=shapes_graph,
            inference="none",
            abort_on_first=False,
        )
        if conforms:
            return ValidationResult(valid=True)
        violations = [
            line.strip()
            for line in report_text.splitlines()
            if line.strip() and not line.startswith("Validation Report")
        ]
        return ValidationResult(valid=False, violations=violations)

    def validate_person(self, person) -> ValidationResult:
        return self._run(person.to_graph(), self._extract_shape(SCHEMA.Person))

    def validate_full_graph(self, data_graph: rdflib.Graph) -> ValidationResult:
        return self._run(data_graph, self._shapes_graph)
