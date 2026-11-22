# Writing an artifact type

An artifact type teaches peerview.it about one kind of content under review. The built-ins are `text` and `pdf` (`src/peerview/plugins/`). The API is not stable before v0.2.

```python
class ArtifactType(Protocol):
    key: str  # stored with every revision, e.g. "text"
    label: str  # shown when a call is created
    input_kind: Literal["text", "file"]  # a text box or a file picker
    accept: str  # file picker hint, e.g. ".pdf"
    max_bytes: int
    annotation_kind: str  # "" when comments cannot be pinned to this type of content

    def ingest(self, upload: Upload) -> Artifact: ...  # validate, normalise
    def render_html(self, artifact: Artifact, raw_url: str) -> str: ...
    def check_selector(self, artifact: Artifact, selector: Mapping[str, str]) -> dict[str, str]: ...
```

- `ingest` raises `ArtifactError("a message for the user")` for anything unacceptable. It returns an immutable `Artifact(type_key, media_type, content, filename)`.
- `render_html` returns trusted HTML. Escape everything that came from the user (`html.escape`).
- `annotation_kind` names the kind of pinned comment the type supports (`"text"` for the built-in text type, `""` for none). `check_selector` receives where the reviewer pinned a comment, as strings from the page, and returns the normalised selector or raises `ArtifactError`. It must verify the selector against the artifact itself (the text type checks that the quoted words are at the stated place). The selector is stored with the revision number, so it never drifts.
- Register it in `pyproject.toml`: `[project.entry-points."peerview.plugins"]` with `mytype = "my_package.module:MyType"`. Install the package next to peerview.it and restart.
- Plugins may import `peerview.application` and `peerview.domain`, never `peerview.adapters` (checked by `make layers`). The core never branches on a type key.
