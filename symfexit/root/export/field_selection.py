from dataclasses import dataclass
from dataclasses import field as dc_field

from django.core.exceptions import FieldDoesNotExist
from django.db import models

from symfexit.root.export.databuilder import get_model_field
from symfexit.root.export.types import fields as export_fields_type


@dataclass
class FieldNode:
    name: str
    label: str
    kind: str  # 'field' or 'relation'
    sub_nodes: list[FieldNode] = dc_field(default_factory=list)


def export_fields_to_nodes(
    model: type[models.Model], export_fields: export_fields_type
) -> list[FieldNode]:
    """Expand an export_fields config into a tree of FieldNodes for template rendering."""
    nodes = []
    for f in export_fields:
        if isinstance(f, str):
            nodes.append(FieldNode(name=f, label=get_model_field(model, f), kind="field"))
        elif isinstance(f, tuple) and isinstance(
            f[1], list
        ):  # related model field with nested export fields
            attr, config = f[0], f[1]
            label = get_model_field(model, attr).title()
            try:
                sub_model = model._meta.get_field(attr).related_model
                sub_nodes = export_fields_to_nodes(sub_model, config)
            except FieldDoesNotExist, AttributeError:
                sub_nodes = []
            nodes.append(FieldNode(name=attr, label=label, kind="relation", sub_nodes=sub_nodes))
        else:
            nodes.append(FieldNode(name=f[0], label=str(f[1]), kind="field"))
    return nodes


def nodes_to_export_fields(
    export_fields: export_fields_type, selected_paths: list[str]
) -> export_fields_type:
    """Return the subset of export_fields matching the selected node paths, preserving custom labels."""
    direct: list[str] = []
    relations: dict[str, list[str]] = {}
    for path in selected_paths:
        if "." in path:
            head, rest = path.split(".", 1)
            relations.setdefault(head, []).append(rest)
        else:
            direct.append(path)

    result = []
    for f in export_fields:
        if isinstance(f, str):
            if f in direct:
                result.append(f)
        elif isinstance(f, tuple) and isinstance(f[1], list):
            attr, config = f[0], f[1]
            if attr in relations:
                sub_fields = nodes_to_export_fields(config, relations[attr])
                if sub_fields:
                    result.append((attr, sub_fields))
        else:
            attr = f[0]
            if attr in direct:
                result.append(f)  # preserves original (attr, label) tuple
    return result
