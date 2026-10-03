"""Every Python file the bundle ships, and install.py, must run on Python 3.9.

macOS's command-line tools provide python3 3.9, so that is the oldest interpreter the bundle
meets in practice. CI and this machine run newer ones, so a 3.10-only construct passes every
test here and fails only in the field. The hook that denies sub-agent edits once did exactly
that: an `X | None` annotation raised TypeError at import on 3.9, the hook exited without a
decision, and the edit it existed to block went through.

Checked statically, since no 3.9 interpreter is assumed: the file must parse as 3.9 syntax, and
an `X | Y` annotation (evaluated when the function is defined) needs
`from __future__ import annotations`. The syntax check is ast's `feature_version`, which is
best-effort: it rejects `match`, but accepts a bracketed multi-item `with` (3.10) and anything
that is valid syntax but a 3.10+ library call. Running the shipped tests on a real 3.9 is the
only full check.
"""
import ast
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOOR = (3, 9)


def shipped_python_files():
    paths = [os.path.join(REPO, "install.py")]
    for root, _, files in os.walk(os.path.join(REPO, "payload")):
        paths += [os.path.join(root, f) for f in files if f.endswith(".py")]
    return sorted(paths)


def union_annotations(tree):
    """Line numbers of annotations that use the | operator."""
    found = []
    for node in ast.walk(tree):
        annotations = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for a in args.posonlyargs + args.args + args.kwonlyargs + [args.vararg, args.kwarg]:
                if a is not None and a.annotation is not None:
                    annotations.append(a.annotation)
            if node.returns is not None:
                annotations.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        for ann in annotations:
            if any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr)
                   for n in ast.walk(ann)):
                found.append(ann.lineno)
    return found


def has_future_annotations(tree):
    return any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
               and any(a.name == "annotations" for a in n.names)
               for n in tree.body)


class PythonFloorTest(unittest.TestCase):

    def test_there_are_files_to_check(self):
        self.assertGreater(len(shipped_python_files()), 10)

    def test_every_file_parses_as_python_3_9(self):
        for path in shipped_python_files():
            with self.subTest(path=os.path.relpath(path, REPO)):
                with open(path, encoding="utf-8") as f:
                    ast.parse(f.read(), path, feature_version=FLOOR)

    def test_union_annotations_have_the_future_import(self):
        for path in shipped_python_files():
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), path)
            if has_future_annotations(tree):
                continue
            with self.subTest(path=os.path.relpath(path, REPO)):
                self.assertEqual(union_annotations(tree), [],
                                 "X | Y annotation without from __future__ import annotations")


if __name__ == "__main__":
    unittest.main()
