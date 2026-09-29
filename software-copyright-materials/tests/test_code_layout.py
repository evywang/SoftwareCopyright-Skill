from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from extract_code_material import (  # noqa: E402
    MAX_CODE_COLUMNS,
    detect_comment_style,
    display_width,
    material_code_lines,
    paginate,
    strip_code_comments,
    wrap_display_line,
)


class CodeLayoutTests(unittest.TestCase):
    def test_display_width_counts_cjk_as_two_columns(self) -> None:
        self.assertEqual(display_width("abc中文"), 7)

    def test_long_line_wrap_preserves_all_characters(self) -> None:
        source = "const value = '" + ("中" * 70) + ("x" * 80) + "';"
        wrapped = wrap_display_line(source, 100)
        self.assertGreater(len(wrapped), 1)
        self.assertEqual("".join(wrapped), source)
        self.assertTrue(all(display_width(line) <= 100 for line in wrapped))

    def test_tabs_are_expanded_before_wrapping(self) -> None:
        wrapped = wrap_display_line("a\tb", 100)
        self.assertEqual(wrapped, ["a   b"])

    def test_material_lines_drop_blanks_and_wrap(self) -> None:
        material = material_code_lines("\nshort\n" + ("x" * 101) + "\n")
        self.assertEqual(material, ["short", "x" * MAX_CODE_COLUMNS, "x" * (101 - MAX_CODE_COLUMNS)])

    def test_paginate_uses_physical_lines(self) -> None:
        pages = paginate([str(i) for i in range(101)], 50)
        self.assertEqual([len(page) for page in pages], [50, 50, 1])


class CommentStripTests(unittest.TestCase):
    def test_c_style_full_line_comments_removed(self) -> None:
        source = "// 整体注释\nint x = 1;\n  // 缩进注释\nint y = 2;\n"
        self.assertEqual(strip_code_comments(source, "c"), ["int x = 1;", "int y = 2;"])

    def test_c_style_block_comments_removed(self) -> None:
        source = "int x = 1;\n/* 单块注释 */\nint y = 2;\nint z = 3;"
        self.assertEqual(strip_code_comments(source, "c"), ["int x = 1;", "int y = 2;", "int z = 3;"])

    def test_c_style_multiline_block_comment_removed(self) -> None:
        source = "int a = 1;\n/* 第一行\n   第二行\n   第三行 */\nint b = 2;"
        self.assertEqual(strip_code_comments(source, "c"), ["int a = 1;", "int b = 2;"])

    def test_c_style_inline_comments_removed(self) -> None:
        source = "int x = 1; // 行尾注释\nint y = 2; /* 块尾 */\nint z = 3;"
        self.assertEqual(strip_code_comments(source, "c"), ["int x = 1;", "int y = 2;", "int z = 3;"])

    def test_c_style_slashes_inside_strings_preserved(self) -> None:
        source = 'char *url = "http://example.com"; // 注释\nchar *p = "a/*b";'
        self.assertEqual(strip_code_comments(source, "c"), ['char *url = "http://example.com";', 'char *p = "a/*b";'])

    def test_c_style_comment_line_between_code_kept_order(self) -> None:
        source = "line1();\n// note\nline2();\n\n\nline3();"
        self.assertEqual(strip_code_comments(source, "c"), ["line1();", "line2();", "line3();"])

    def test_hash_style_comments_removed(self) -> None:
        source = "# 注释行\ndef main():\n    x = 1  # 行尾注释\n    url = 'http://a#b'\n    return x"
        self.assertEqual(
            strip_code_comments(source, "hash"),
            ["def main():", "    x = 1", "    url = 'http://a#b'", "    return x"],
        )

    def test_dash_style_comments_removed(self) -> None:
        source = "-- 注释\nSELECT 1; -- 行尾\nSELECT 'a--b' FROM t;"
        self.assertEqual(strip_code_comments(source, "dash"), ["SELECT 1;", "SELECT 'a--b' FROM t;"])

    def test_comment_only_file_yields_empty(self) -> None:
        source = "// only comments\n/* more */\n// and more\n\n"
        self.assertEqual(strip_code_comments(source, "c"), [])

    def test_detect_comment_style_by_extension(self) -> None:
        self.assertEqual(detect_comment_style(Path("main.py")), "hash")
        self.assertEqual(detect_comment_style(Path("main.c")), "c")
        self.assertEqual(detect_comment_style(Path("main.cpp")), "c")
        self.assertEqual(detect_comment_style(Path("query.sql")), "dash")
        self.assertEqual(detect_comment_style(Path("script.gd")), "hash")
        self.assertEqual(detect_comment_style(Path("unknown.xyz")), "c")

    def test_material_lines_include_no_comments_or_file_markers(self) -> None:
        source = (
            "// File: src/main.c\n"
            "#include <stdio.h>\n"
            "int main(void) { // entry\n"
            "    /* block */\n"
            "    printf(\"hi // there\");\n"
            "    return 0;\n"
            "}\n"
        )
        material = material_code_lines(source)
        self.assertNotIn("// File: src/main.c", material)
        self.assertEqual(
            material,
            ["#include <stdio.h>", "int main(void) {", '    printf("hi // there");', "    return 0;", "}"],
        )

    def test_c_preprocessor_lines_kept_in_c_style(self) -> None:
        source = "#include <stdlib.h>\n#define N 10\n// comment\nint a = N;"
        self.assertEqual(strip_code_comments(source, "c"), ["#include <stdlib.h>", "#define N 10", "int a = N;"])

    def test_python_single_line_docstring_removed(self) -> None:
        source = "def f():\n    '''docstring 注释'''\n    return 1"
        self.assertEqual(strip_code_comments(source, "hash"), ["def f():", "    return 1"])

    def test_python_multiline_docstring_removed(self) -> None:
        source = "def f():\n    \"\"\"多行\n    文档\n    字符串\"\"\"\n    return 1\n\ndef g():\n    pass"
        self.assertEqual(strip_code_comments(source, "hash"), ["def f():", "    return 1", "def g():", "    pass"])

    def test_python_assigned_triple_quoted_string_kept(self) -> None:
        source = "TEMPLATE = \"\"\"value\nstring\"\"\"\nx = 1"
        self.assertEqual(strip_code_comments(source, "hash"), ["TEMPLATE = \"\"\"value", "string\"\"\"", "x = 1"])


if __name__ == "__main__":
    unittest.main()
