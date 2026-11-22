"""Reviewers get the work without its author's names in the file's metadata (ADR 0028)."""

from __future__ import annotations

import io

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject

from peerview.application.artifacts import ArtifactError, HidesAuthors, anonymous_copy
from peerview.domain.calls import Artifact
from peerview.plugins.pdf import PdfArtifact
from peerview.plugins.text import TextArtifact

NAME = b"Sam Secret"


def pdf_with_names() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(200, 200)
    writer.add_metadata({"/Author": "Sam Secret", "/Title": "Essay by Sam Secret"})
    note = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Text"),
            NameObject("/Rect"): ArrayObject([]),
            NameObject("/T"): TextStringObject("Sam Secret"),
            NameObject("/Contents"): TextStringObject("check this"),
        }
    )
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(note)])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_a_pdf_loses_the_names_in_its_metadata_and_notes() -> None:
    original = Artifact("pdf", "application/pdf", pdf_with_names(), "sam-secret.pdf")
    assert NAME in original.content
    copy = anonymous_copy(PdfArtifact(), original)
    assert NAME not in copy.content and copy.filename is None
    reader = PdfReader(io.BytesIO(copy.content))
    assert len(reader.pages) == 1 and not reader.metadata


def test_types_without_metadata_pass_through_unchanged_but_nameless() -> None:
    assert not isinstance(TextArtifact(), HidesAuthors)
    text = Artifact("text", "text/plain", b"Hello", "sam.txt")
    copy = anonymous_copy(TextArtifact(), text)
    assert copy.content == b"Hello" and copy.filename is None


def test_a_pdf_that_cannot_be_read_is_not_handed_out_with_its_names() -> None:
    broken = Artifact("pdf", "application/pdf", b"%PDF-1.7 Sam Secret garbage", None)
    with pytest.raises(ArtifactError):
        anonymous_copy(PdfArtifact(), broken)
