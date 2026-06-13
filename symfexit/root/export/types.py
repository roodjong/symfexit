from collections.abc import Sequence

type field_with_label = tuple[str, str]
type field_with_model = tuple[str, fields]
type fields = Sequence[str | field_with_label | field_with_model]
