import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT / "bin" / "delivery_compiler.exe"


def compile_source(source: str) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".dsl", delete=False, encoding="utf-8") as file:
        file.write(source)
        path = Path(file.name)
    try:
        completed = subprocess.run(
            [str(COMPILER), str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return json.loads(completed.stdout)
    finally:
        path.unlink(missing_ok=True)


class CompilerAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not COMPILER.exists():
            raise unittest.SkipTest("Compila primero con build.ps1")

    def test_valid_program_exposes_tree_and_attributes(self):
        source = (ROOT / "examples" / "pedido_basico.dsl").read_text(encoding="utf-8")
        result = compile_source(source)

        self.assertTrue(result["success"])
        self.assertEqual(result["syntax"]["tree"]["symbol"], "Programa")
        self.assertGreater(len(result["syntax"]["tree"]["children"]), 0)
        self.assertEqual(len(result["semantic"]["symbols"]), 6)
        self.assertGreater(len(result["semantic"]["attributes"]), 0)

    def test_false_branch_is_parsed_but_not_executed(self):
        result = compile_source(
            "PEDIDO { total: 10 }\n"
            "SI total > 50 {\n"
            "  ASIGNAR prioridad\n"
            "}\n"
            "FINALIZAR pedido\n"
        )

        conditional = result["syntax"]["tree"]["children"][1]
        block = conditional["children"][1]
        self.assertEqual(block["lexeme"], "falso")
        self.assertEqual(len(block["children"]), 1)
        self.assertNotIn("ASIGNAR -> prioridad", result["logs"])
        self.assertIn("FINALIZAR -> pedido", result["logs"])

    def test_semantic_error_keeps_partial_analysis(self):
        source = (ROOT / "examples" / "error_semantico.dsl").read_text(encoding="utf-8")
        result = compile_source(source)

        self.assertFalse(result["success"])
        self.assertTrue(any("stock" in error for error in result["errors"]))
        self.assertIsNotNone(result["syntax"]["tree"])
        self.assertGreater(len(result["semantic"]["symbols"]), 0)

    def test_inherited_and_synthesized_attributes_are_present(self):
        result = compile_source("PEDIDO { total: 25 }\nVALIDAR total\n")
        attributes = result["semantic"]["attributes"]

        self.assertTrue(all("scope" in item["inherited"] for item in attributes))
        self.assertTrue(all("type" in item["synthesized"] for item in attributes))
        total = next(item for item in attributes if item["node"] == "Propiedad")
        self.assertEqual(total["synthesized"]["type"], "numero")
        self.assertEqual(total["synthesized"]["value"], "25")


if __name__ == "__main__":
    unittest.main(verbosity=2)
