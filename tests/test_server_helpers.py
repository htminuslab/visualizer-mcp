from __future__ import annotations

import pytest

from visualizer_mcp.server import _strip_vcc_annotation, _tcl_split


class TestStripVccAnnotation:
    def test_decimal_annotation(self):
        assert _strip_vcc_annotation("4'd3") == "3"

    def test_hex_annotation(self):
        assert _strip_vcc_annotation("8'hFF") == "FF"

    def test_binary_annotation(self):
        assert _strip_vcc_annotation("4'b0101") == "0101"

    def test_unsigned_annotation(self):
        assert _strip_vcc_annotation("8'u255") == "255"

    def test_plain_value_unchanged(self):
        assert _strip_vcc_annotation("3") == "3"

    def test_plain_value_with_whitespace(self):
        assert _strip_vcc_annotation("  6  ") == "6"

    def test_zero(self):
        assert _strip_vcc_annotation("8'd0") == "0"

    def test_wide_vector(self):
        assert _strip_vcc_annotation("32'd4294967295") == "4294967295"


class TestTclSplit:
    def test_bare_words(self):
        assert _tcl_split("0 1 0 1") == ["0", "1", "0", "1"]

    def test_brace_groups(self):
        assert _tcl_split("{0 ns} {100 ns}") == ["0 ns", "100 ns"]

    def test_mixed(self):
        assert _tcl_split("{0 ns} 3 {10 ns} 6") == ["0 ns", "3", "10 ns", "6"]

    def test_annotated_values(self):
        assert _tcl_split("4'd3 4'd6 4'd3") == ["4'd3", "4'd6", "4'd3"]

    def test_empty_string(self):
        assert _tcl_split("") == []

    def test_extra_whitespace(self):
        assert _tcl_split("  1   2  ") == ["1", "2"]

    def test_nested_braces(self):
        assert _tcl_split("{a {b} c} d") == ["a {b} c", "d"]
