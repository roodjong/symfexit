from collections.abc import Sequence

type field_with_label = tuple[str, str]
type fields = Sequence[str | field_with_label]
